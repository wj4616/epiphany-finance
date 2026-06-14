"""Behavioral battery for the 2026-06-14 deep-audit remediation. Every test pins a fix to an
OBSERVABLE behaviour (a driven figure, an injected section, a route), not a module's static shape —
the audit's recurring finding was 'capability present but not fired on the live path'.
"""
import math
import os
import sys
import tempfile

import pytest

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_WT = "/home/myuser/projects/goatcs-harness"
for p in (BUILD, HARNESS_WT):
    if p not in sys.path:
        sys.path.insert(0, p)

from goatcs_harness import route                                   # noqa: E402
from goatcs_harness.loader import load                             # noqa: E402
from wrapper import checks, finance, intake, quote, run            # noqa: E402

GRAPH = os.path.join(BUILD, "graph.json")


def _tmp():
    return tempfile.mkdtemp()


def _finalize(state, *, bracket="middle", fstate=None, qd=None):
    out = run.finalize(state, out_dir=_tmp(), quote_data=(qd or {"prices": {}}), bracket=bracket,
                       fstate=(fstate or {}), db=None, markdown=True, pdf_flag=False, out=lambda *a: None)
    return open(out["markdown_path"]).read()


# ---- F1: frequency normalization (was entirely missing) ----
@pytest.mark.parametrize("amt,freq,expect", [
    (1800, "biweekly", 1800 * 26 / 12), (100, "weekly", 100 * 52 / 12), (1200, "annual", 100.0),
    (300, "quarterly", 100.0), (500, "semimonthly", 1000.0), (1000, None, 1000.0),
    (1000, "monthly", 1000.0), ("garbage", "weekly", 0.0)])
def test_to_monthly_normalizes_every_cadence(amt, freq, expect):
    assert finance.to_monthly(amt, freq) == pytest.approx(expect)


def test_monthly_numbers_normalizes_mixed_cadence():
    st = {"income_sources": [{"amount_per_period": 1000, "frequency": "biweekly", "is_active": 1},
                             {"amount_per_period": 50, "frequency": "monthly", "is_active": 0}],
          "expenses": [{"category": "food", "amount": 100, "frequency": "weekly"}]}
    n = finance.monthly_numbers(st)
    assert n["monthly_income"] == round(1000 * 26 / 12, 2)              # inactive source excluded
    assert n["monthly_expenses"] == round(100 * 52 / 12, 2)


# ---- F3/F5/F7 + NaN: portfolio valuation correctness ----
def test_portfolio_valuation_handles_bad_prices():
    v = finance.portfolio_valuation(
        [{"ticker": "VTI", "shares": 10, "cost_basis": 100},          # live
         {"ticker": "ZERO", "shares": 5, "cost_basis": 50},           # price 0 -> bad data, no fallback
         {"ticker": "NAN", "shares": 5, "cost_basis": 50},            # NaN -> bad data, no fallback
         {"ticker": "FB", "shares": 5, "cost_basis": 50, "last_known_price": 10}],  # fallback
        {"VTI": {"price": 372.45}, "ZERO": {"price": 0}, "NAN": {"price": float("nan")},
         "FB": {"price": None}})
    assert v["excluded_count"] == 2 and v["fallback_count"] == 1
    # excluded holdings are dropped from BOTH totals (gain never over/understated), not silently
    assert math.isfinite(v["total_value"]) and math.isfinite(v["total_gain"])
    assert v["total_value"] == pytest.approx(372.45 * 10 + 10 * 5)


def test_normalize_allocation_all_zero_returns_zeros():
    assert finance.normalize_allocation({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}
    assert finance.normalize_allocation({}) == {}


# ---- Q2: the deterministic figures actually reach the report ----
def test_your_numbers_block_is_injected_and_computed():
    fstate = {"income_sources": [{"amount_per_period": 5200, "frequency": "monthly", "is_active": 1}],
              "expenses": [{"category": "rent", "amount": 1800, "frequency": "monthly"}]}
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n"},
                   fstate=fstate)
    assert "## Your Numbers (calculated)" in md
    assert "$5,200.00" in md and "$1,800.00" in md          # income + expense, grouped
    assert "$3,400.00" in md                                # surplus = 5200 - 1800


def test_your_numbers_shows_shortfall_for_deficit():
    fstate = {"income_sources": [{"amount_per_period": 997, "frequency": "monthly", "is_active": 1}],
              "expenses": [{"category": "rent", "amount": 1200, "frequency": "monthly"}]}
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n"},
                   bracket="destitute", fstate=fstate)
    assert "shortfall" in md.lower() and "$203.00" in md


# ---- benefit#1: benefit-safety is GUARANTEED in a benefit-dependent report ----
def test_benefit_safety_block_injected_even_when_llm_omits_it():
    fstate = {"income_sources": [{"source_name": "SSI", "amount_per_period": 997,
                                  "frequency": "monthly", "is_active": 1}],
              "profile": {"wealth_bracket": "destitute"}}
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n"},
                   bracket="destitute", fstate=fstate)
    assert "Benefit Safety" in md and "ABLE" in md and "asset limit" in md.lower()
    assert "benefits counselor" in md                        # benefit-specific disclaimer addition


def test_surplus_projection_is_benefit_aware():
    # benefit-dependent user with a surplus must NOT get a rosy "invest it -> $X" projection; instead
    # a benefit-safe note pointing at Benefit Safety / ABLE (audit-2026-06-14 F-1).
    fstate = {"income_sources": [{"source_name": "SSDI", "amount_per_period": 1500,
                                  "frequency": "monthly", "is_active": 1}],
              "expenses": [{"category": "rent", "amount": 1000, "frequency": "monthly"}],
              "profile": {"wealth_bracket": "lower"}}
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n"},
                   bracket="lower", fstate=fstate)
    assert "could grow to" not in md                         # no rosy compound projection
    assert "means-tested benefits" in md and "ABLE" in md    # benefit-safe note instead
    # a NON-benefit user with the same surplus DOES get the projection
    md2 = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n"},
                    bracket="middle",
                    fstate={"income_sources": [{"amount_per_period": 1500, "frequency": "monthly",
                                                "is_active": 1}],
                            "expenses": [{"category": "rent", "amount": 1000, "frequency": "monthly"}]})
    assert "could grow to" in md2


def test_benefit_dependent_detection_paths():
    assert run.is_benefit_dependent({"benefit_dependent": True}, {})
    assert run.is_benefit_dependent({"benefit_dependency_flags": {"ssdi": True}}, {})
    assert run.is_benefit_dependent({}, {"income_sources": [{"source_name": "Social Security Disability"}]})
    assert not run.is_benefit_dependent({}, {"income_sources": [{"source_name": "salary"}]})


# ---- B2: ensemble dissent surfaces in an UNCERTAIN appendix (was a dead pipe) ----
def test_uncertain_appendix_surfaces_dissent():
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n",
                    "challenge_list": [{"figure": "$6,000 target", "issue": "jury split 1-of-3"}]})
    assert "Appendix: Uncertain Figures" in md and "$6,000 target" in md and "jury split" in md


def test_uncertain_appendix_absent_when_no_dissent():
    md = _finalize({"report_markdown": "## What this means for you\nHi.\n## Glossary\nETF: x.\n",
                    "challenge_list": []})
    assert "Appendix: Uncertain Figures" not in md


# ---- Q1: the deterministic compliance battery runs LIVE (warn-loud) ----
def test_compliance_battery_runs_live_and_warns(capsys):
    # a report missing the glossary must emit a ⚠ compliance warning from finalize (not silent)
    warned = []
    run.finalize({"report_markdown": "## What this means for you\nHi.\n"},   # no glossary
                 out_dir=_tmp(), quote_data={"prices": {}}, bracket="middle", fstate={},
                 db=None, markdown=True, pdf_flag=False, out=lambda m: warned.append(m))
    assert any("compliance" in w and "glossary" in w.lower() for w in warned)


# ---- charts: title-less spec must not crash the whole report ----
def test_charts_render_specs_no_crash_on_titleless_spec():
    from wrapper import charts
    res = charts.render_specs([{"type": "bar", "labels": ["a"], "values": [1]}], _tmp())
    assert "rendered" in res and "skipped" in res           # no KeyError


# ---- quote: a NaN/0 price is treated as unavailable, never propagated ----
def test_quote_rejects_nonfinite_price():
    from wrapper.state import FinanceState
    import datetime
    db = FinanceState(":memory:")
    now = datetime.datetime(2026, 6, 3, 20, 5, tzinfo=datetime.timezone.utc)
    qd = quote.fetch_quotes(["BAD"], db, now=now, fetcher=lambda t: (float("nan"), "2026-06-03T20:00:00Z"))
    assert qd["prices"]["BAD"]["price"] is None and qd["prices"]["BAD"].get("unavailable")
    assert qd["prices"]["BAD"]["stale"] is False             # unavailable != stale (no false STALE banner)
    assert qd["offline_flag"]


# ---- checks: stock-pick screen catches sentence-initial imperatives, not common ALL-CAPS prose ----
def test_stock_pick_screen_case_insensitive_low_false_positive():
    assert not checks.no_individual_stock_picks("Dump GME immediately.")[0]   # caught (case-insensitive)
    assert checks.no_individual_stock_picks("Build an emergency fund first.")[0]
    assert checks.no_individual_stock_picks("CASH vs DEBT: pay high-interest debt first.")[0]  # not flagged
    assert checks.no_individual_stock_picks("Decide whether to RENT versus OWN.")[0]


# ---- intake: signed/worded amounts parse correctly ----
@pytest.mark.parametrize("text,expect", [
    ("-200", -200.0), ("about 3 thousand", 3000.0), ("4k", 4000.0), ("$1,500", 1500.0),
    ("2 million", 2_000_000.0)])
def test_extract_amount_sign_and_magnitude(text, expect):
    assert intake.extract_amount(text) == pytest.approx(expect)


# ---- topology F1/F5/F2: degrade-and-ship + durable emit (no exit-6 route-halt) ----
def test_degrade_and_ship_routing():
    g = load(GRAPH)
    def tgt(node, st):
        return route.choose_successor(g, node, st).target
    assert tgt("N-QUALITY-GATE", {"quality_verdict": "FAIL", "rc__E27": 2}) == "N-HITL-APPROVE"
    assert tgt("N-HITL-APPROVE", {"rework_requested": True, "rc__E42": 2}) == "N-EMIT-MD"
    assert tgt("N-HITL-APPROVE", {"plan_approved": False, "rework_requested": False}) == "N-EMIT-MD"


def test_emit_md_binds_durable_writer():
    g = load(GRAPH)
    assert g.nodes["N-EMIT-MD"].tool_call["tool"] == "fs.write_output"
    from goatcs_harness.tool_registry import REGISTRY
    assert REGISTRY["fs.write_output"].capability == "fs-output"   # durable, not scratch


# ---- Q4: a non-interactive run auto-approves (the gate never blocks headless/tests) ----
def test_approval_gate_auto_approves_noninteractive():
    assert run._approval_gate({"report_markdown": "x"}, yes=False) is True   # not a tty in CI
    assert run._approval_gate({"report_markdown": "x"}, yes=True) is True
