# epiphany-finance — Build Brief

> **Historical (v1).** This is the original v1.1.0 build brief (22-node graph). The **deployed skill
> is v2.0.0 — a 36-node graph**; see `BUILD-REPORT-v2.md` and `SKILL.md` for current capability.
> Kept for domain reference; topology numbers below describe v1.

**Skill:** `epiphany-finance` — personal financial advisor. Serves any wealth level (destitute →
ultra-HNW): bidirectional budget + income, compound projections, live-quote portfolio valuation,
adversarial verification, professional Markdown/PDF report with charts + verbatim disclaimer.

**Substrate:** goatcs-harness native graph (`dialect: native`, `schema_version:
epiphany-harness.ir.v1`). 22 nodes, GoT-full (≥7 waves, 3 AND-joins, ≥1 back-edge). Domain constants
in `appendix.md`. Charts + final PDF are **wrapper-rendered** (graph emits specs only).

## Topology (22 nodes)

| Wave | Node | type/tier | Emits (signals) |
|---|---|---|---|
| 0 | N-PREFLIGHT | gate / no-llm | mode_flags ok; REFUSE if no context |
| 1a | N-CONTEXT-INGEST | io→llm | parsed_context |
| 1b | N-CLASSIFY | llm-medium | wealth_bracket, situation_class, has_investment_flag, location_available_flag, priority_flags |
| 2 | N-RESEARCH-ECO | llm (network) | economic_digest (always) |
| 2 | N-RESEARCH-LOC | llm (network) | location_digest (gated: location_available_flag) |
| 2 | N-RESEARCH-MKT | llm (network) | market_digest (gated: has_investment_flag) |
| 3 | N-RESEARCH-AGG | agg AND | research_digest; **re-emits** location_digest, market_digest |
| 3 | N-SITUATION-ANALYZE | llm-large | situation_analysis |
| 4 | N-BUDGET-ENGINE | llm-large | budget_plan (both directions + investable_surplus + compound_projections) |
| 4 | N-QUOTE-FETCHER | io / no-llm (wrapper-fed) | quote_data (fetch_ts, per-ticker price+source_ts+staleness, offline_flag) — gated has_investment_flag |
| 4 | N-PORTFOLIO-ENGINE | llm-large | portfolio_plan (live valuation, gains/losses, broad rebalancing) — gated has_investment_flag |
| 5 | N-INCOME-ENGINE | llm-large | income_plan (both directions + concrete_paths) — seq after Wave 4 |
| 6 | N-VERIFY-BUDGET | llm-medium | budget_verdict |
| 6 | N-VERIFY-INCOME | llm-medium | income_verdict — seq after Wave 5 |
| 6 | N-ADVERSARIAL | llm-large | challenge_list (incl. Q5 safety challenges) |
| 7 | N-SYNTHESIS-AGG | agg AND | verified_advice (4 inputs incl. portfolio-slot bypass) |
| 8 | N-CHART-SPEC | llm-medium | chart_specs (7 types, Q4 skip flags, Q2 timestamps in titles) |
| 8 | N-DISCLAIMER | llm-small | compliance_wrap (bracket additions; base is wrapper constant) |
| 9 | N-REPORT | agg AND / llm-large | report_markdown (Glossary + "What this means for you", Data Freshness, exact-timestamped prices) |
| 9 | N-QUALITY-GATE | gate / llm-medium | quality_verdict (+ readability + Q5 safety scoring) |
| 10 | N-EMIT-MD | io / no-llm | tool_call fs.write_text (PASS ∧ markdown_flag) |
| 10 | N-EMIT-PDF | io / no-llm | tool_call pdf.render (PASS ∧ pdf_flag) |

## Gating + edges (canonical)
- Sequential `required`: INGEST→CLASSIFY (1a→1b), BUDGET→INCOME (4→5), INCOME→VERIFY-INCOME (5→6).
- Gated `gate-open` (fire on flag true): CLASSIFY→RESEARCH-LOC, CLASSIFY→RESEARCH-MKT,
  CONTEXT-INGEST→QUOTE-FETCHER, CLASSIFY→PORTFOLIO-ENGINE; QUOTE-FETCHER→PORTFOLIO-ENGINE `required`.
- AND-join slots (share `and_join_group`): RESEARCH-AGG {eco-slot, loc-slot, mkt-slot};
  SYNTHESIS-AGG {verify×3, portfolio-slot}; REPORT {report-inputs: verified_advice, chart_specs,
  compliance_wrap}.
- **Bypass** (forward-conditional, **same and_join_group**, condition = flag false): CLASSIFY→
  RESEARCH-AGG(loc-slot) when location_available_flag==false; CLASSIFY→RESEARCH-AGG(mkt-slot) and
  CLASSIFY→SYNTHESIS-AGG(portfolio-slot) when has_investment_flag==false.
- **Back-edge:** QUALITY-GATE→REPORT, `back-edge`, retry_cap 2, gate `quality_verdict == FAIL`.
- **Emit:** QUALITY-GATE→EMIT-MD `forward-conditional` `quality_verdict == 'PASS' AND markdown_flag == true`;
  →EMIT-PDF `... AND pdf_flag == true`.

## Verifier compliance (fix A)
Every node reading a conditionally-produced signal marks that input `required:false`:
- RESEARCH-AGG: loc-slot, mkt-slot inputs `required:false`.
- INCOME-ENGINE / SITUATION-ANALYZE: `location_digest` `required:false`.
- PORTFOLIO-ENGINE: `market_digest` `required:false`; `quote_data` `required` (its gate guarantees it).
- SYNTHESIS-AGG: `portfolio_plan` `required:false`.
- Every forward-conditional edge has a `gate_condition`. Flag signals (markdown_flag, pdf_flag, mode)
  are **top-level seed signals** (fix F).

## Special requirements (fold into node contracts)
- **Q5 safety** at PORTFOLIO/ADVERSARIAL/QUALITY-GATE (no stock-vs-stock / specific picks).
- **Q1/Q2/Q3 quotes:** QUOTE-FETCHER carries exact ISO8601 fetch_ts + market source_ts; OFFLINE/STALE.
- **Q4 chart-skip** at CHART-SPEC for OFFLINE/STALE price-dependent charts.
- **Q7 plain-language** at REPORT (Glossary, "What this means for you", expand acronyms, kind tone).
- **Disclaimer** base text is a wrapper constant (fix C); DISCLAIMER node adds bracket clauses only.

## V-battery
V-FIN-01..27 — criteria listed in `appendix.md` §8. Binary ship-gate; all must PASS on the 3 personas
(destitute, middle, ultra-HNW).
