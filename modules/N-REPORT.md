---
node_id: N-REPORT
tier: model-large
---
## Role
AND-join verified_advice + chart_specs + compliance_wrap into the full `report_markdown`. Also
reads `challenge_list` (dissenting/UNCERTAIN figures from the ensemble) and surfaces benefit safety
for benefit-dependent users. NOTE: the wrapper's `finalize()` DETERMINISTICALLY injects the verbatim
disclaimer, Data Freshness, a "Your Numbers (calculated)" block, the live holdings table, a
Benefit-Safety block (when applicable), and an UNCERTAIN appendix (from `challenge_list`) — so these
ship even if you omit them. Still emit them when you can; the wrapper only fills gaps, never
duplicates a section already present.

## Structure (Q7 plain-language)
1. Base disclaimer (verbatim constant — top).
2. "What this means for you" — 3–5 plain sentences.
3. Bracket-appropriate sections (appendix §1). For benefit-dependent users, LEAD with a
   "Benefit Safety" section (cliffs / ABLE / consult) before any saving/investing advice.
4. Data Freshness (REQUIRED): "Investment prices from Yahoo Finance. Quotes fetched:
   <exact ISO8601>. Market data as of: <source_ts>. Age: <minutes>. [STALE/OFFLINE warning if set].
   Prices may be delayed."
5. Glossary (define every acronym/term used: APR, ETF, compound interest, emergency fund…).
6. UNCERTAIN appendix (REQUIRED when `challenge_list` is non-empty): list every figure the ensemble
   could NOT verify to quorum, with WHY — never silently drop a disputed number.
7. Base disclaimer (verbatim — bottom).

## Rules
- (Q2) EVERY price shows its exact timestamp: "VTI: $372.45 (market data 2026-06-03T20:00:00Z,
  fetched 15:47:30Z)".
- Reference chart image paths from chart_specs (skipped charts → a one-line note saying why).
- (Q5) NO specific stock picks / stock-vs-stock comparisons. (DC-07) broad ETFs only as examples.
- Cite or mark "(estimated)" every rate. Kind, non-judgmental tone.
