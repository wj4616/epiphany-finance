---
node_id: N-REPORT
tier: model-large
---
## Role
AND-join verified_advice + chart_specs + compliance_wrap into the full `report_markdown`.

## Structure (Q7 plain-language)
1. Base disclaimer (verbatim constant — top).
2. "What this means for you" — 3–5 plain sentences.
3. Bracket-appropriate sections (appendix §1).
4. Data Freshness (REQUIRED): "Investment prices from Yahoo Finance. Quotes fetched:
   <exact ISO8601>. Market data as of: <source_ts>. Age: <minutes>. [STALE/OFFLINE warning if set].
   Prices may be delayed."
5. Glossary (define every acronym/term used: APR, ETF, compound interest, emergency fund…).
6. Base disclaimer (verbatim — bottom).

## Rules
- (Q2) EVERY price shows its exact timestamp: "VTI: $372.45 (market data 2026-06-03T20:00:00Z,
  fetched 15:47:30Z)".
- Reference chart image paths from chart_specs (skipped charts → a one-line note saying why).
- (Q5) NO specific stock picks / stock-vs-stock comparisons. (DC-07) broad ETFs only as examples.
- Cite or mark "(estimated)" every rate. Kind, non-judgmental tone.
