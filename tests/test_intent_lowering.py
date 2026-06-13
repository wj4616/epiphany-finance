"""S4 — v2 intent.json validates against the closed taxonomy and lowers (via the real compiler)
to v2's shipped graph deterministically + verify-clean (V-INTENT, V-COMPILER).

Also asserts the lean-hybrid routing contract: refuse/bracket/strategy are compiler-lowered; the
signal-driven routes (has_investment_flag, data_freshness_regime) are deliberately NOT in intent.json.
"""
import json
import os
import subprocess
import sys

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_graph import lower_intent_to_native  # noqa: E402
from goatcs_harness.generator.routing_intent import validate_intent, deserialize_intent  # noqa: E402

INTENT = os.path.join(BUILD, "intent.json")
BASE = os.path.join(BUILD, "graph.v2-base.json")


def _intent():
    return json.load(open(INTENT))


def test_intent_validates_against_closed_taxonomy():
    intents = deserialize_intent(_intent())
    for nid, intent in intents.items():
        v = validate_intent(intent)
        assert v.ok, f"{nid}: {v.errors}"
        assert not v.unclassifiable, f"{nid} is out-of-taxonomy"
    # exactly the 3 lean-hybrid compiler-lowered routes; signal-driven routes are NOT declared
    assert set(intents) == {"N-PREFLIGHT", "N-FRAME-SELECT", "N-STRATEGY-FANOUT"}
    assert intents["N-PREFLIGHT"]["kind"] == "early_exit"
    assert intents["N-FRAME-SELECT"]["kind"] == "quality_gate"
    assert intents["N-STRATEGY-FANOUT"]["kind"] == "parallel_merge"


def test_signal_driven_routes_absent_from_intent():
    intents = deserialize_intent(_intent())
    # has_investment_flag / data_freshness_regime are carried SIGNALS, not topology (DD-2)
    blob = json.dumps(intents)
    assert "has_investment_flag" not in blob
    assert "data_freshness_regime" not in blob


def _sig(g):
    return [(e["src"], e["dst"], e.get("kind"), e.get("gate_condition"),
             e.get("and_join_group"), e.get("split_from")) for e in g["edges"]]


def test_lowering_is_deterministic_byte_identical():
    base = json.load(open(BASE))
    g1, e1 = lower_intent_to_native(base, _intent())
    assert e1 == []
    # perturb intent dict insertion order; compiler sorts node ids -> identical edges
    payload = _intent()
    payload["intents"] = dict(reversed(list(payload["intents"].items())))
    g2, e2 = lower_intent_to_native(base, payload)
    assert e2 == []
    assert _sig(g1) == _sig(g2), "lowering must be order-independent (V-COMPILER determinism)"


def test_lowered_graph_is_the_shipped_graph_and_verifies(tmp_path):
    base = json.load(open(BASE))
    g, errors = lower_intent_to_native(base, _intent())
    assert errors == [], errors
    shipped = json.load(open(os.path.join(BUILD, "graph.json")))
    assert _sig(g) == _sig(shipped), "intent.json must lower to the shipped graph.json (V-INTENT)"
    env = dict(os.environ, PYTHONPATH=HARNESS_WT)
    r = subprocess.run([sys.executable, "-m", "goatcs_harness.cli", "verify", "--strict-wiring",
                        os.path.join(BUILD, "graph.json")], cwd=HARNESS_WT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"verify exit {r.returncode}: {r.stdout[-800:]}"
