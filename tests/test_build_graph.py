"""S3 — HC-3 compiler-integration build path (the first production-skill consumer).

Proves `build_graph.lower_intent_to_native` lowers an authored intent.json through the REAL merged
co-evolution compiler (`compiler.compile_graph` + `emit_intent.render_compiled_edge`) into the skill's
native graph.json dialect, deterministically and fail-closed, and that the result passes
`verify --strict-wiring` exit 0.

The full real intent.json on the real v2 graph is exercised by S4 (test_intent_lowering.py); this
isolates the integration *mechanism* on a small synthetic native graph.
"""
import json
import os
import subprocess
import sys

import pytest

BUILD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD_DIR, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_graph import lower_intent_to_native  # noqa: E402


def _node(nid, typ="GENERATOR", out=None):
    return {"id": nid, "name": nid, "type": typ, "tier": "model-small", "exec_type": "inline",
            "hat": "", "wave": "0", "conditional": typ == "GATE", "inputs": [], "outputs": out or [],
            "raises_signals": [], "join_policy": None, "aggregation_policy": None,
            "module_file": f"modules/{nid}.md", "scale_gates": {}, "rationale": "", "tool_call": None}


def _base_graph():
    return {"schema_version": "1.0", "dialect": "native", "skill_name": "probe",
            "skill_version": "0.0.1", "determinism_class": "non-deterministic",
            "entrypoints": ["N-START"],
            "nodes": {
                "N-START": _node("N-START", "GATE",
                                 out=[{"name": "refuse_flag", "type": "flag",
                                       "signal_field": "refuse_flag", "required": True}]),
                "N-MID": _node("N-MID"),
                "N-DONE": _node("N-DONE"),
                "N-REFUSE": _node("N-REFUSE"),
            },
            "edges": [
                {"id": "E1", "src": "N-START", "dst": "N-MID", "kind": "required"},
                {"id": "E2", "src": "N-MID", "dst": "N-DONE", "kind": "required"},
            ]}


def _early_exit_intent():
    return {"schema_version": "intent.v1",
            "intents": {"N-START": {"kind": "early_exit", "pred": "refuse_flag",
                                    "terminal": "N-REFUSE"}}}


def test_lowers_minimal_intent_through_real_compiler():
    g, errors = lower_intent_to_native(_base_graph(), _early_exit_intent())
    assert errors == [], errors
    by_src = {}
    for e in g["edges"]:
        by_src.setdefault(e["src"], []).append(e)
    start_edges = by_src["N-START"]
    kinds = {e["kind"] for e in start_edges}
    # early_exit -> a conditional exit edge (gate=pred -> terminal) + a required fall-through
    assert "forward-conditional" in kinds and "required" in kinds, start_edges
    exit_edge = next(e for e in start_edges if e["kind"] == "forward-conditional")
    assert exit_edge["dst"] == "N-REFUSE" and exit_edge["gate_condition"] == "refuse_flag"
    # the legacy hand-wired N-START->N-MID edge (E1) is replaced by the compiled fall-through
    assert not any(e.get("id") == "E1" for e in g["edges"])
    # non-intent edges (E2) are preserved (mixed-graph contract)
    assert any(e.get("id") == "E2" for e in g["edges"])


def _sig(g):
    return [(e["src"], e["dst"], e.get("kind"), e.get("gate_condition")) for e in g["edges"]]


def test_lowering_is_deterministic():
    # build with a second intent-map whose dict has an extra (later) key removed/re-added to vary
    # insertion order; compile_graph sorts node ids so the output must be byte-identical.
    base = _base_graph()
    g1, _ = lower_intent_to_native(base, _early_exit_intent())
    # add then drop a same-node intent to perturb construction order, then lower again
    payload2 = {"schema_version": "intent.v1", "intents": {}}
    payload2["intents"]["N-START"] = {"kind": "early_exit", "pred": "refuse_flag",
                                      "terminal": "N-REFUSE"}
    g2, _ = lower_intent_to_native(base, payload2)
    assert _sig(g1) == _sig(g2)
    assert json.dumps(g1["edges"], sort_keys=True) == json.dumps(g2["edges"], sort_keys=True)


def test_fail_closed_on_compiler_abstention():
    # an early_exit whose terminal node is absent from the graph -> compiler UNCERTAIN -> surfaced.
    bad = {"schema_version": "intent.v1",
           "intents": {"N-START": {"kind": "early_exit", "pred": "refuse_flag",
                                   "terminal": "N-NONEXISTENT"}}}
    g, errors = lower_intent_to_native(_base_graph(), bad)
    assert errors, "fail-closed: an unresolved-target abstention must surface as a non-empty error list"
    assert any("N-START" in e for e in errors)


def test_lowered_graph_passes_verify_strict_wiring(tmp_path):
    g, errors = lower_intent_to_native(_base_graph(), _early_exit_intent())
    assert errors == []
    out = tmp_path / "lowered.json"
    out.write_text(json.dumps(g))
    env = dict(os.environ, PYTHONPATH=HARNESS_WT)
    r = subprocess.run([sys.executable, "-m", "goatcs_harness.cli", "verify", "--strict-wiring",
                        str(out)], cwd=HARNESS_WT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"verify --strict-wiring exit {r.returncode}\n{r.stdout}\n{r.stderr}"
