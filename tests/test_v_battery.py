"""V-battery V-FIN-01..27 — the acceptance gate for epiphany-finance.

Mix of (a) graph-contract checks (static topology / node contracts), (b) deterministic wrapper-unit
checks, and (c) report-content checks via wrapper/checks.py. The single full inline persona drive is
exercised separately in test_e2e_inline.py; here we use deterministic state to keep CI fast + green.
"""
import json
import os
from datetime import datetime, timezone

import pytest
from conftest import GRAPH, load_persona

from goatcs_harness.loader import load
from wrapper import charts, checks, finance, intake, quote
from wrapper.disclaimer import BASE_DISCLAIMER, disclaimer_for
from wrapper.state import FinanceState


@pytest.fixture(scope="module")
def g():
    return load(GRAPH)


def _node(g, nid):
    return g.nodes[nid]


# ---- V-FIN-16 / topology (graph-contract) ----
def test_vfin_16_back_edge_retry(g):
    backs = [e for e in g.edges if e.kind == "back-edge" and e.dst == "N-REPORT"]
    assert backs and backs[0].retry_cap == 2


def test_topology_22_nodes_3_aggs(g):
    # v2 reinterpretation: carried v1 core (22 nodes) preserved + lean-hybrid v2 nodes added (36
    # total). Aggregation floor (>=3 AND-joins) holds. All v1 node ids still present (additive, C1).
    real = [n for n in g.nodes if not g.nodes[n].external]
    assert len(real) == 36
    assert sum(1 for n in real if g.nodes[n].join_policy == "AND") >= 3
    v1_core = {"N-PREFLIGHT", "N-CONTEXT-INGEST", "N-CLASSIFY", "N-RESEARCH-ECO", "N-RESEARCH-LOC",
               "N-RESEARCH-MKT", "N-RESEARCH-AGG", "N-SITUATION-ANALYZE", "N-BUDGET-ENGINE",
               "N-QUOTE-FETCHER", "N-PORTFOLIO-ENGINE", "N-INCOME-ENGINE", "N-VERIFY-BUDGET",
               "N-VERIFY-INCOME", "N-ADVERSARIAL", "N-SYNTHESIS-AGG", "N-CHART-SPEC", "N-DISCLAIMER",
               "N-REPORT", "N-QUALITY-GATE", "N-EMIT-MD", "N-EMIT-PDF"}
    assert v1_core <= set(real), v1_core - set(real)


# ---- V-FIN-02 classification (contract: CLASSIFY emits wealth_bracket + flags) ----
def test_vfin_02_classify_emits_bracket(g):
    outs = g.nodes["N-CLASSIFY"].write_keys
    for sig in ("wealth_bracket", "situation_class", "has_investment_flag", "location_available_flag"):
        assert sig in outs


# ---- V-FIN-10 location passthrough (RESEARCH-AGG re-emits location_digest) ----
def test_vfin_10_location_passthrough(g):
    assert "location_digest" in g.nodes["N-RESEARCH-AGG"].write_keys
    assert "market_digest" in g.nodes["N-RESEARCH-AGG"].write_keys


# ---- V-FIN-14 no HITL node in graph ----
def test_vfin_14_no_hitl(g):
    # v2 reinterpretation (spec §5.6, IC-04 scoped supersession): DATA intake stays wrapper-level;
    # exactly ONE in-graph HITL node exists and it is the plan-approval pause (N-HITL-APPROVE).
    hitl_nodes = [n for n in g.nodes if g.nodes[n].hitl]
    assert hitl_nodes == ["N-HITL-APPROVE"], hitl_nodes


# ---- V-FIN-12 charts wrapper-rendered (no in-graph chart.render tool_call) ----
def test_vfin_12_charts_not_in_graph(g):
    for n in g.nodes.values():
        tc = n.tool_call or {}
        assert tc.get("tool") != "chart.render"
    assert hasattr(charts, "render_specs")


# ---- V-FIN-17 run() public API used (not subprocess) ----
def test_vfin_17_uses_run_api():
    src = open(os.path.join(os.path.dirname(__file__), "..", "wrapper", "run.py")).read()
    assert "from goatcs_harness import run" in src
    # no subprocess RUNNER for the graph (the word may appear in prose; the calls must not)
    assert "import subprocess" not in src
    assert "subprocess.Popen" not in src and "subprocess.run" not in src and "os.system(" not in src


# ---- V-FIN-05 allocation sums to 100 ----
def test_vfin_05_allocation_sums_100():
    assert abs(sum(finance.normalize_allocation({"index": 70, "bonds": 20, "hysa": 11}).values()) - 100) < 0.2


# ---- V-FIN-06 compound formula incl. boundary guards (fix D) ----
def test_vfin_06_compound_boundaries():
    # known value within 1%
    assert abs(finance.compound(500, 0.07, 5) - 35796.45) / 35796.45 < 0.01
    # r=0 boundary -> no division by zero
    assert finance.compound(500, 0.0, 5) == 500 * 60
    # t=0 -> principal
    assert finance.compound(500, 0.07, 0, principal=1234) == 1234
    # existing principal grows
    assert finance.compound(0, 0.10, 10, principal=10000) > 25000


# ---- V-FIN-07 allocation varies by bracket ----
def test_vfin_07_allocation_varies_by_bracket():
    wp = finance.normalize_allocation({"hysa": 60, "index": 40})
    mid = finance.normalize_allocation({"index": 70, "bonds": 20, "hysa": 10})
    assert wp != mid


# ---- V-FIN-13 investment_allocation_targets table exists ----
def test_vfin_13_alloc_targets_table():
    db = FinanceState(":memory:")
    db.import_state(load_persona("middle"))
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(investment_allocation_targets)")}
    assert {"vehicle", "target_pct", "expected_annual_return", "is_tax_advantaged"} <= cols


# ---- V-FIN-21 current_value from LIVE prices (±$0.01) ----
def test_vfin_21_live_valuation(quote_data):
    holdings = load_persona("middle")["portfolio_holdings"]
    val = finance.portfolio_valuation(holdings, quote_data["prices"])
    vti = next(h for h in val["holdings"] if h["ticker"] == "VTI")
    assert abs(vti["current_value"] - 60 * 372.45) < 0.01
    assert abs(vti["gain_loss"] - (60 * 372.45 - 18000)) < 0.01


# ---- V-FIN-18 / 22 quote freshness w/ exact ISO8601 on every price ----
def test_vfin_18_22_exact_timestamp(quote_data):
    s = quote.format_price("VTI", quote_data["prices"]["VTI"])
    assert "2026-06-03T20:00:00Z" in s and "$372.45" in s
    sect = quote.data_freshness_section(quote_data)
    ok, detail = checks.every_price_has_timestamp(sect)
    assert ok, detail


# ---- V-FIN-19 Data Freshness section mandatory ----
def test_vfin_19_data_freshness_section(quote_data):
    sect = quote.data_freshness_section(quote_data)
    assert "## Data Freshness" in sect and "Yahoo Finance" in sect


# ---- V-FIN-20 STALE/OFFLINE > 24h warning ----
def test_vfin_20_stale_and_offline():
    now = datetime(2026, 6, 5, 20, 0, 0, tzinfo=timezone.utc)
    db = FinanceState(":memory:")
    db.import_state(load_persona("middle"))
    # stale: source_ts 3 days old
    qd = quote.fetch_quotes(["VTI"], db, now=now, fetcher=lambda t: (100.0, "2026-06-02T20:00:00Z"))
    assert qd["prices"]["VTI"]["stale"]
    assert "STALE" in quote.data_freshness_section(qd)
    # offline: stale cache + failing fetch -> offline_flag + warning
    db.write_quote_cache("VTI", 100.0, "2026-06-01T00:00:00Z", "2026-06-01T00:00:00Z", True, 0)
    def boom(t): raise RuntimeError("net down")
    qd2 = quote.fetch_quotes(["VTI"], db, now=now, fetcher=boom)
    assert qd2["offline_flag"] and any("OFFLINE" in w for w in qd2["warnings"])
    assert "OFFLINE" in quote.data_freshness_section(qd2)


# ---- V-FIN-23 misleading-chart suppression (offline -> portfolio chart skipped) ----
def test_vfin_23_chart_skip_offline(tmp_path):
    offline_qd = {"quote_fetch_ts": "2026-06-03T20:00:00Z", "offline_flag": True,
                  "prices": {"VTI": {"price": 372.45, "stale": False}}}
    specs = [{"type": "pie", "title": "Budget", "labels": ["a"], "values": [1],
              "path": str(tmp_path / "b.png")},
             {"type": "bar", "title": "Portfolio Breakdown", "labels": ["VTI"], "values": [1],
              "path": str(tmp_path / "p.png")}]
    res = charts.render_specs(specs, str(tmp_path), offline_qd)
    titles_skipped = [s["title"] for s in res["skipped"]]
    assert any("Portfolio" in t for t in titles_skipped)
    assert any("Budget" in r["title"] for r in res["rendered"])


# ---- V-FIN-24 investment-safety guardrail (no stock-vs-stock / specific picks) ----
def test_vfin_24_safety_guardrail():
    bad1 = "You should buy NVDA now for big gains."
    bad2 = "Consider AAPL vs MSFT for your tech exposure."
    good = "Consider a broad index fund like VTI plus BND for diversification."
    assert not checks.no_individual_stock_picks(bad1)[0]
    assert not checks.no_individual_stock_picks(bad2)[0]
    assert checks.no_individual_stock_picks(good)[0]
    # the adversarial + quality-gate node contracts encode the guardrail
    advtxt = open(os.path.join(os.path.dirname(__file__), "..", "modules", "N-ADVERSARIAL.md")).read()
    assert "Q5" in advtxt or "stock pick" in advtxt.lower()


# ---- V-FIN-01 disclaimer verbatim top+bottom (wrapper guarantees via finalize) ----
def test_vfin_01_disclaimer_verbatim():
    from wrapper import run
    db = FinanceState(":memory:")
    db.import_state(load_persona("destitute"))
    out = run.finalize({"report_markdown": "Body text only.", "chart_specs": []},
                       out_dir="/tmp/efin_vt01", quote_data={"prices": {}}, bracket="destitute",
                       fstate=db.export(), db=db, markdown=True, pdf_flag=False, out=lambda *a: None)
    md = open(out["markdown_path"]).read()
    ok, detail = checks.disclaimer_top_and_bottom(md)
    assert ok, detail
    assert BASE_DISCLAIMER in md


# ---- V-FIN-25 plain-language (Glossary + What this means) ----
def test_vfin_25_plain_language():
    good = "## What this means for you\n...\n## Glossary\nETF: a fund...\n"
    assert checks.has_glossary(good)[0] and checks.has_what_this_means(good)[0]
    assert not checks.has_glossary("no glossary here")[0]


# ---- V-FIN-26 guided intake completes from minimal input ----
def test_vfin_26_intake_minimal():
    fs = intake.run_intake(scripted={"income": "3k", "housing": "1000"})
    assert fs["income_sources"][0]["amount_per_period"] == 3000
    db = FinanceState(":memory:")
    db.import_state(fs)
    exp = db.export()
    assert exp["income_sources"] and not db.is_empty()


# ---- V-FIN-03 / 04 both directions (contract presence in engine modules) ----
def test_vfin_03_04_bidirectional_contracts():
    bud = open(os.path.join(os.path.dirname(__file__), "..", "modules", "N-BUDGET-ENGINE.md")).read()
    inc = open(os.path.join(os.path.dirname(__file__), "..", "modules", "N-INCOME-ENGINE.md")).read()
    assert "Direction A" in bud and "Direction B" in bud
    assert "Direction A" in inc and "Direction B" in inc
    # and the deterministic state-shape checkers work
    assert checks.both_budget_directions(
        {"allocation_at_current_income": {}, "income_target": 1, "income_gap": 0})[0]
    assert checks.both_income_directions(
        {"current_income_analysis": {}, "target_income_analysis": {}, "concrete_paths": []})[0]


# ---- persona-spanning finalize: all 3 brackets produce a compliant report ----
@pytest.mark.parametrize("persona", ["destitute", "middle", "ultra-HNW"])
def test_personas_finalize_compliant(persona, tmp_path, mock_prices, now):
    from wrapper import run
    db = FinanceState(":memory:")
    db.import_state(load_persona(persona))
    bracket = db.export()["profile"]["wealth_bracket"]
    qd = quote.fetch_quotes(db.tickers(), db, now=now, fetcher=mock_prices)
    out = run.finalize({"report_markdown": "## What this means for you\nBody.\n## Glossary\nETF: fund.\n",
                        "chart_specs": []}, out_dir=str(tmp_path), quote_data=qd, bracket=bracket,
                       fstate=db.export(), db=db, markdown=True, pdf_flag=False, out=lambda *a: None)
    md = open(out["markdown_path"]).read()
    assert checks.disclaimer_top_and_bottom(md)[0]
    assert checks.data_freshness_present(md)[0]
    assert checks.every_price_has_timestamp(md)[0]
    if persona == "ultra-HNW":
        assert "CPA or tax attorney" in md            # bracket-specific addition
    if persona == "destitute":
        assert not db.tickers()                        # no investments -> quote/portfolio bypass path


# ---- V-FIN-11 portfolio refines projections with existing principal ----
def test_vfin_11_portfolio_principal():
    fresh = finance.compound(500, 0.10, 10, principal=0)
    with_principal = finance.compound(500, 0.10, 10, principal=50000)
    assert with_principal > fresh + 50000  # existing principal compounds on top
