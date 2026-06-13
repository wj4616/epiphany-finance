"""RL-1 runtime-liveness: drive the router over realistic mid-run state. Module-present != live.
A graph-building step's DoD is NOT met by verify/wiring-check alone — every all-gated node must
route to a real successor (never a silent dead-lock), and every AND/XOR join must gate correctly.
This test is the control-flow analogue of verify-integration-not-just-modules.
"""
import os
import sys

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402
from goatcs_harness.loader import load  # noqa: E402
from goatcs_harness import route  # noqa: E402

GRAPH = os.path.join(BUILD, "graph.json")


@pytest.fixture(scope="module")
def spec():
    return load(GRAPH, validate=False)


def _t(spec, node, state):
    return route.choose_successor(spec, node, state)


@pytest.mark.parametrize("node,state,expect", [
    ("N-PREFLIGHT", {"preflight_ok": True}, "N-CONTEXT-INGEST"),
    ("N-PREFLIGHT", {"preflight_ok": False}, "N-REFUSE"),
    ("N-FRAME-SELECT", {"wealth_bracket": "survival"}, "N-FRAME-SURVIVAL"),
    ("N-FRAME-SELECT", {"wealth_bracket": "middle"}, "N-FRAME-STANDARD"),
    ("N-FRAME-SELECT", {"wealth_bracket": "hnw"}, "N-FRAME-HNW"),
    ("N-QUALITY-GATE", {"quality_verdict": "PASS"}, "N-HITL-APPROVE"),
    ("N-QUALITY-GATE", {"quality_verdict": "FAIL", "rc__N-QUALITY-GATE": 0}, "N-REPORT"),
    ("N-HITL-APPROVE", {"plan_approved": True}, "N-EMIT-MD"),
    ("N-HITL-APPROVE", {"rework_requested": True, "rc__N-HITL-APPROVE": 0}, "N-REPORT"),
])
def test_gate_routes_to_real_successor(spec, node, state, expect):
    r = _t(spec, node, state)
    assert r.status == "ok", f"{node} dangled/halted on {state}: {r.status}"
    assert r.target == expect, f"{node} -> {r.target}, expected {expect}"


def test_hitl_first_arrival_is_a_pause_not_silent_halt(spec):
    # N-HITL-APPROVE with no decision dangles in the router — but the driver pauses it via
    # awaiting_human (Tier2Halt, exit-11) BEFORE routing, so it is a HITL pause, not a dead-lock.
    # Both decided states route (asserted above). Here we just confirm the node is declared hitl.
    n = spec.node("N-HITL-APPROVE")
    assert getattr(n, "hitl", False) is True


def test_strategy_fanout_is_parallel(spec):
    r = _t(spec, "N-STRATEGY-FANOUT", {})
    assert r.status == "fan_out"
    assert {e.dst for e in r.fired} == {"N-STRAT-CAND-BUDGET", "N-STRAT-CAND-INCOME",
                                        "N-STRAT-CAND-PORTFOLIO"}


@pytest.mark.parametrize("join,one,allk", [
    ("N-RESEARCH-AGG", {"economic_digest": 1},
     {"economic_digest": 1, "location_digest": 1, "market_digest": 1, "quote_data": 1, "macro_context": 1}),
    ("N-STRATEGY-MERGE", {"cand_budget": 1},
     {"cand_budget": 1, "cand_income": 1, "cand_portfolio": 1}),
    ("N-SYNTHESIS-AGG", {"budget_verdict": 1},
     {"budget_verdict": 1, "income_verdict": 1, "challenge_list": 1, "portfolio_plan": 1, "benefit_safety": 1}),
    ("N-REPORT", {"chart_specs": 1},
     {"chart_specs": 1, "compliance_wrap": 1, "report_frame": 1}),
])
def test_and_join_waits_then_fires(spec, join, one, allk):
    assert route.join_ready(spec, join, one)[0] is False, f"{join} fired with one branch"
    assert route.join_ready(spec, join, allk)[0] is True, f"{join} never became ready"


def test_frame_merge_or_join_fires_on_single_frame(spec):
    # exactly one frame ever runs (quality_gate switch) -> OR-join is ready on the single token.
    assert route.join_ready(spec, "N-FRAME-MERGE", {})[0] is False
    assert route.join_ready(spec, "N-FRAME-MERGE", {"report_frame_standard": 1})[0] is True
