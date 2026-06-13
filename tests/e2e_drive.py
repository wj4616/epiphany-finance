#!/usr/bin/env python3
"""Full inline E2E (build-plan fix G): drive the 22-node graph to a PASS report by reasoning each
node (realistic, spec-compliant outputs), then run the wrapper finalize. Proves the inline loop +
produces a real report.md/report.pdf + a recorded_state fixture. Heavy/manual — not part of CI.

Usage: python tests/e2e_drive.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BUILD)
from goatcs_harness import cli  # noqa: E402
from wrapper import quote, run  # noqa: E402
from wrapper.state import FinanceState  # noqa: E402

PAUSED = 11
GRAPH = os.path.join(BUILD, "graph.json")


def _cli(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(list(args))
    out = buf.getvalue()
    return code, (json.loads(out) if out.strip() else {})


def _submit(session, node, outputs, tmp):
    f = os.path.join(tmp, f"out_{node}.json")
    with open(f, "w") as fh:
        json.dump(outputs, fh)
    return _cli("submit", "--session", session, node, "--outputs", f, "--inline")[0]


REPORT_MD = """\
## What this means for you
You earn more than you spend, which is great. Put your extra money toward a fuller emergency fund
first, then steady investing in broad, low-cost funds. Keep debt payments on track.

## Budget
Your monthly take-home is $5,200. A 50/30/20 split suggests ~$2,600 needs, ~$1,560 wants,
~$1,040 to savings + investing. (estimated)

## Income
Direction A: at your current income you can comfortably cover essentials. Direction B: to reach
your house goal faster you'd need about $800/mo more — see concrete paths below.

## Investing
Consider a diversified mix of broad index funds and bonds (for example a total-market fund plus a
bond fund). We do not recommend specific stocks or compare one stock against another.

## Glossary
- ETF: a low-cost fund that holds many investments at once.
- Emergency fund: 3–6 months of expenses kept in cash for surprises.
- Compound interest: earning returns on your past returns over time.
"""


def outputs_for(node):
    return {
        "N-PREFLIGHT": {"preflight_ok": True},
        "N-CONTEXT-INGEST": {"parsed_context": {"income": 5200, "holdings": ["VTI", "BND"],
                                                "location": "Austin, TX", "risk": "moderate"}},
        "N-CLASSIFY": {"wealth_bracket": "middle", "situation_class": "employed",
                       "has_investment_flag": True, "location_available_flag": True,
                       "priority_flags": {}},
        "N-RESEARCH-ECO": {"economic_digest": {"inflation": "3% (estimated)", "hysa": "4% (estimated)"}},
        "N-RESEARCH-LOC": {"location_digest": {"city": "Austin, TX", "median_rent": "$1700 (estimated)"}},
        "N-RESEARCH-MKT": {"market_digest": {"equities": "broad market context (estimated)"}},
        "N-RESEARCH-AGG": {"research_digest": {"ok": True},
                           "location_digest": {"city": "Austin, TX"},
                           "market_digest": {"equities": "context"},
                           "quote_data": {"prices": {"VTI": {"price": 372.45}}}},
        "N-SITUATION-ANALYZE": {"situation_analysis": {"levers": ["grow emergency fund", "invest surplus"]}},
        "N-BUDGET-ENGINE": {"budget_plan": {"allocation_at_current_income": {"needs": 50, "wants": 30, "save": 20},
                                            "income_target": 6000, "income_gap": 800,
                                            "investable_surplus": 1040,
                                            "suggested_allocation_split": {"index": 70, "bonds": 20, "hysa": 10},
                                            "compound_projections": [{"years": 10, "nominal": 180000}]}},
        "N-PORTFOLIO-ENGINE": {"portfolio_plan": {"current_holdings_analysis": "valued at live prices",
                                                  "rebalancing_suggestions": "shift toward target broad mix",
                                                  "quote_freshness_statement": "prices timestamped"}},
        "N-INCOME-ENGINE": {"income_plan": {"current_income_analysis": "sustainable",
                                            "target_income_analysis": "reach $6000/mo",
                                            "income_gap_passthrough": 800,
                                            "concrete_paths": ["upskill", "negotiate raise"],
                                            "upskilling_suggestions": ["certification"]}},
        "N-VERIFY-BUDGET": {"budget_verdict": {"pass": True, "issues": []}},
        "N-VERIFY-INCOME": {"income_verdict": {"pass": True, "issues": []}},
        "N-ADVERSARIAL": {"challenge_list": []},
        "N-SYNTHESIS-AGG": {"verified_advice": {"ok": True}},
        "N-CHART-SPEC": {"chart_specs": [
            {"type": "pie", "title": "Budget allocation", "labels": ["needs", "wants", "save"],
             "values": [50, 30, 20]},
            {"type": "bar", "title": "Portfolio Breakdown", "labels": ["VTI", "BND"], "values": [60, 50]}]},
        "N-DISCLAIMER": {"compliance_wrap": {"bracket_additions": []}},
        "N-REPORT": {"report_markdown": REPORT_MD},
        "N-QUALITY-GATE": {"quality_verdict": "PASS"},
    }.get(node, {})


def main():
    tmp = tempfile.mkdtemp()
    db = FinanceState(os.path.join(tmp, "state.db"))
    db.import_state(json.load(open(os.path.join(BUILD, "fixtures", "middle.json"))))
    now = __import__("datetime").datetime(2026, 6, 3, 20, 5, tzinfo=__import__("datetime").timezone.utc)
    qd = quote.fetch_quotes(db.tickers(), db, now=now,
                            fetcher=lambda t: ({"VTI": 372.45, "BND": 72.10}[t], "2026-06-03T20:00:00Z"))
    seed = run.build_seed(db.export(), qd, mode="report", markdown=True, pdf_flag=True,
                          context_text="", out_dir=tmp)
    seed_path = os.path.join(tmp, "seed.json")
    json.dump(seed, open(seed_path, "w"))

    session = os.path.join(tmp, "sess")
    os.environ["CLAUDECODE"] = "1"
    code, payload = _cli("run", GRAPH, "--seed", seed_path, "--session", session,
                         "--provider", "inline", "--allow-network")
    pauses = []
    for _ in range(40):
        if code != PAUSED:
            break
        node = payload["pause"]["node"]
        pauses.append(node)
        assert _submit(session, node, outputs_for(node), tmp) == 0, f"submit {node} failed"
        code, payload = _cli("run", GRAPH, "--resume", session, "--provider", "inline", "--allow-network")

    print("paused nodes (reasoned):", pauses)
    print("final code:", code, "verdict:", payload.get("verdict"))
    state = run.read_session_state(session)
    json.dump(state, open(os.path.join(BUILD, "fixtures", "recorded_state.json"), "w"), indent=2, default=str)
    print("report_markdown produced:", bool(state.get("report_markdown")))
    print("chart_specs produced:", len(state.get("chart_specs") or []))

    outs = run.finalize(state, out_dir=os.path.join(tmp, "report"), quote_data=qd,
                        bracket="middle", fstate=db.export(), db=db, markdown=True, pdf_flag=True)
    md = open(outs["markdown_path"]).read()
    from wrapper import checks
    results = checks.run_report_checks(md, qd)
    print("\n-- report checks --")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print("\nreport.md:", outs["markdown_path"], "| pdf:", outs.get("pdf_path"), outs.get("pdf_status"))
    # Under --provider inline, verifier/adversarial nodes collapse to UNCERTAIN (H4) — a single
    # agent cannot independently cross-verify. That is EXPECTED and honest; the report still ships.
    drive_ok = code in (0, 8)   # 0=PASS, 8=UNCERTAIN(inline verification collapse)
    print(f"\ndrive verdict={payload.get('verdict')} (inline UNCERTAIN is expected); checks_ok="
          f"{all(ok for _, ok, _ in results)}")
    return 0 if all(ok for _, ok, _ in results) and drive_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
