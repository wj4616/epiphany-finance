"""v2 V-battery (the 10 NEW checks). The carried V-FIN-01..27 live in test_v_battery.py; these add
V-ENS, V-ROUTE, V-COMPILER, V-BACKEDGE, V-TOOL, V-FANOUT, V-BENEFIT, V-UX, V-INTENT, V-HARNESS-REG.
Each is a structural/behavioral assertion over the SHIPPED graph + wrapper + the merged compiler.
"""
import json
import os
import subprocess
import sys

import pytest

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

from goatcs_harness.loader import load                              # noqa: E402
from goatcs_harness import route                                   # noqa: E402
from goatcs_harness.generator.routing_intent import validate_intent, deserialize_intent  # noqa: E402
from build_graph import lower_intent_to_native                     # noqa: E402


@pytest.fixture(scope="module")
def g():
    return load(os.path.join(BUILD, "graph.json"), validate=False)


def _intent():
    return json.load(open(os.path.join(BUILD, "intent.json")))


# ---- V-INTENT: intent.json valid against the closed taxonomy + lowers to the shipped graph ----
def test_v_intent(g):
    intents = deserialize_intent(_intent())
    for nid, intent in intents.items():
        assert validate_intent(intent).ok, nid
    base = json.load(open(os.path.join(BUILD, "graph.v2-base.json")))
    lowered, errs = lower_intent_to_native(base, _intent())
    assert errs == []
    shipped = json.load(open(os.path.join(BUILD, "graph.json")))
    sig = lambda gg: sorted((e["src"], e["dst"], e.get("kind")) for e in gg["edges"])
    assert sig(lowered) == sig(shipped)


# ---- V-COMPILER: deterministic byte-identical lowering + verify --strict-wiring exit 0 ----
def test_v_compiler_determinism():
    base = json.load(open(os.path.join(BUILD, "graph.v2-base.json")))
    g1, _ = lower_intent_to_native(base, _intent())
    payload = _intent()
    payload["intents"] = dict(reversed(list(payload["intents"].items())))
    g2, _ = lower_intent_to_native(base, payload)
    assert [e for e in g1["edges"]] == [e for e in g2["edges"]]


def test_v_compiler_verify_exit0():
    env = dict(os.environ, PYTHONPATH=HARNESS_WT)
    r = subprocess.run([sys.executable, "-m", "goatcs_harness.cli", "verify", "--strict-wiring",
                        os.path.join(BUILD, "graph.json")], cwd=HARNESS_WT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-600:]


# ---- V-ROUTE: bracket routing is a compiler-lowered EDGE, not a Python conditional ----
def test_v_route_bracket_is_compiler_lowered(g):
    # ACTUAL classifier bracket values (the frame ids 'survival'/'hnw' are NOT bracket values; a
    # gate that compared them was permanently dead -> every user got the standard frame).
    for st, expect in [({"wealth_bracket": "destitute"}, "N-FRAME-SURVIVAL"),
                       ({"wealth_bracket": "working-poor"}, "N-FRAME-SURVIVAL"),
                       ({"wealth_bracket": "middle", "benefit_dependent": True}, "N-FRAME-SURVIVAL"),
                       ({"wealth_bracket": "middle"}, "N-FRAME-STANDARD"),
                       ({"wealth_bracket": "ultra-HNW"}, "N-FRAME-HNW")]:
        r = route.choose_successor(g, "N-FRAME-SELECT", st)
        assert r.status == "ok" and r.target == expect, (st, r.target)
    # the routing edges exist and are compiler-emitted (RI__ prefix), not hand-wired
    out_edges = [e for e in g.edges if e.src == "N-FRAME-SELECT"]
    assert all(e.id.startswith("RI__") for e in out_edges), [e.id for e in out_edges]


def test_v_route_not_wrapper_self_gating():
    # the bracket/investment/freshness ROUTING decision must not be a Python conditional in run.py
    run_py = open(os.path.join(BUILD, "wrapper", "run.py")).read()
    # no bracket-name routing conditionals choosing a graph path in the wrapper
    assert "N-FRAME-SURVIVAL" not in run_py and "N-FRAME-HNW" not in run_py


# ---- S17 de-wrapper: E27 is the SOLE quality-retry authority (no duplicate post-graph retry) ----
def test_s17_no_duplicate_wrapper_quality_retry():
    run_py = open(os.path.join(BUILD, "wrapper", "run.py")).read()
    # Q1 (audit-2026-06-14): the wrapper now runs the FULL deterministic compliance battery as a
    # LIVE, LOG-ONLY backstop (was disclaimer-only — glossary/plain-summary/no-stock-pick had no
    # backstop under the inline-collapsing LLM gate). "Warn-loud, still ship": it emits ⚠ warnings
    # but must NOT re-drive the graph / drive a second quality retry (E27 is the sole in-graph
    # retry authority).
    assert "run_report_checks" in run_py, "wrapper must run the live compliance backstop"
    assert "⚠ compliance" in run_py, "the backstop must be LOG-ONLY (warn), not a routing authority"
    # finalize() itself must never re-drive the graph (no harness run() call inside it).
    fin = run_py[run_py.index("def finalize("):run_py.index("def prepare(")]
    assert "_run(" not in fin and "import run as" not in fin, "finalize must not re-drive the graph"
    assert "finalize" in run_py and "disclaimer" in run_py.lower()


# ---- V-FANOUT: strategy fan-out is a compiler-lowered parallel_merge; single-candidate graceful ----
def test_v_fanout_parallel_merge(g):
    r = route.choose_successor(g, "N-STRATEGY-FANOUT", {})
    assert r.status == "fan_out"
    assert {e.dst for e in r.fired} == {"N-STRAT-CAND-BUDGET", "N-STRAT-CAND-INCOME",
                                        "N-STRAT-CAND-PORTFOLIO"}
    # the merge AND-join gates on all three candidates
    assert route.join_ready(g, "N-STRATEGY-MERGE", {"cand_budget": 1})[0] is False
    assert route.join_ready(g, "N-STRATEGY-MERGE",
                            {"cand_budget": 1, "cand_income": 1, "cand_portfolio": 1})[0] is True


# ---- V-BACKEDGE: E27 quality back-edge is the sole quality-retry; cap 2 ----
def test_v_backedge_quality_retry(g):
    e27 = next(e for e in g.edges if e.id == "E27")
    assert e27.kind == "back-edge" and e27.src == "N-QUALITY-GATE" and e27.dst == "N-REPORT"
    assert e27.retry_cap == 2


# ---- V-TOOL: quote path is HC-1 retry+cache-backed + HC-4 typed output schema ----
def test_v_tool_quote_hc1_hc4(g):
    q = g.nodes["N-QUOTE-FETCHER"]
    assert (q.tool_call or {}).get("retry_cache") is True       # HC-1 opt-in
    assert q.output_schema.get("quote_data", {}).get("type") == "dict"   # HC-4 typed output


def test_v_tool_hc1_retry_and_cache_in_quote_fetch(tmp_path):
    from wrapper import quote
    from wrapper.state import FinanceState
    calls = {"n": 0}

    def flaky(ticker):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient")     # first attempt fails -> HC-1 should retry
        return (100.0, "2026-06-13T20:00:00Z")

    db = FinanceState(":memory:")
    qd = quote.fetch_quotes(["VTI"], db, fetcher=flaky)
    # transient failure was retried (not an immediate OFFLINE) -> a real price came through
    assert calls["n"] >= 2
    assert qd["prices"]["VTI"]["price"] == 100.0
    assert qd.get("offline_flag") in (False, None)


# ---- V-TOOL (behavioral, audit N1): a urllib3 transient (which does NOT subclass OSError, so the
# harness DEFAULT_RETRYABLE alone would NOT catch it) must now retry in the live wrapper — proving
# the widened retry_on actually engages on the yfinance/urllib3 failure surface, not just requests. ----
def test_v_tool_hc1_retries_urllib3_transient(tmp_path):
    pytest.importorskip("urllib3")
    from urllib3.exceptions import ProtocolError
    from wrapper import quote
    from wrapper.state import FinanceState
    calls = {"n": 0}

    def flaky(ticker):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProtocolError("Connection aborted")   # urllib3 transient -> must retry, not OFFLINE
        return (100.0, "2026-06-13T20:00:00Z")

    db = FinanceState(":memory:")
    qd = quote.fetch_quotes(["VTI"], db, fetcher=flaky)
    assert calls["n"] >= 2                               # the urllib3 transient WAS retried
    assert qd["prices"]["VTI"]["price"] == 100.0
    assert qd.get("offline_flag") in (False, None)


# ---- V-ENS: N-ADVERSARIAL is an ensemble quorum (not 1-of-1), downshiftable ----
def test_v_ens_quorum(g):
    n = g.nodes["N-ADVERSARIAL"]
    assert n.ensemble is not None
    assert n.ensemble.mode == "quorum"
    assert n.ensemble.jury_size == 3 and n.ensemble.k == 2
    assert n.downshiftable is True            # collapses to J=1 on the $0 hot path (C8)


# ---- V-ENS (behavioral, audit N2): when N-ADVERSARIAL downshifts to J=1 on the $0 hot path, a
# lone juror that FLAGS a planted-bad figure must route its UNCERTAIN verdict through (not be
# swallowed by a vanished majority), and a juror that returns no valid output must degrade
# gracefully — never divide-by-zero on the empty jury. Drives the real harness quorum at J=1
# rather than asserting the static spec, closing the FIRING-UNPROVEN gap (W-05). ----
def test_v_ens_j1_bad_figure_routes_uncertain():
    from goatcs_harness.quorum import run_quorum
    from goatcs_harness.providers import Cast

    cast = Cast(provider="inline", model="reasoner", tier="model-large", role="worker")

    def invoke(prompt, *, cast, node, attempt):
        return "RAW"

    # J=1 — the single juror detects a planted-bad figure and returns the UNCERTAIN verdict.
    def parse_bad(_raw):
        return ({"verdict": "UNCERTAIN", "reason": "planted figure $9,999 unverifiable"}, "UNCERTAIN")

    r = run_quorum([cast], "audit the figures", invoke=invoke, parse=parse_bad)
    assert r.k_satisfied is True                       # k = 1//2+1 = 1, satisfied by the lone juror
    assert r.next_choice == "UNCERTAIN"                # the bad-figure verdict ROUTES, not swallowed
    assert r.winner_output["verdict"] == "UNCERTAIN"

    # J=1 with an INVALID juror (parse yields no output) — the empty valid-set must short-circuit
    # at the `len(valid) < k` guard, never reaching the `len(valid)`-denominator dissent math.
    def parse_invalid(_raw):
        return (None, None)

    r2 = run_quorum([cast], "audit", invoke=invoke, parse=parse_invalid)   # must not raise
    assert r2.k_satisfied is False
    assert "quorum not met" in r2.note


# ---- V-BENEFIT: benefit-safety node consumes flags + income, emits benefit_safety ----
def test_v_benefit(g):
    n = g.nodes["N-BENEFIT-SAFETY"]
    ins = {p.signal for p in n.inputs}
    assert "benefit_dependency_flags" in ins and "income_plan" in ins
    assert "benefit_safety" in n.write_keys
    # N-CLASSIFY emits the dependency flags (S9)
    assert "benefit_dependency_flags" in g.nodes["N-CLASSIFY"].write_keys


# ---- V-UX: exactly one HITL (plan-approval), single exit-11 pause; intake stays wrapper-level ----
def test_v_ux_single_hitl(g):
    hitl = [n for n in g.nodes if g.nodes[n].hitl]
    assert hitl == ["N-HITL-APPROVE"]


# ---- V-HARNESS-REG: the additive harness primitives are present + importable (0-NEW asserted in CI) ----
def test_v_harness_reg_primitives_present():
    import goatcs_harness.tool_retry_cache as trc
    import goatcs_harness.node_output_schema as nos
    from goatcs_harness import driver
    from goatcs_harness import run as run_fn   # eagerly-bound function, not the submodule
    assert hasattr(trc, "ToolRetryCache") and hasattr(trc, "maybe_wrap")
    assert hasattr(nos, "validate_output_schema")
    import inspect
    assert "on_progress" in inspect.signature(run_fn).parameters
    assert "on_progress" in inspect.signature(driver.drive_node).parameters
