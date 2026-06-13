---
node_id: N-QUALITY-GATE
tier: model-medium
---
## Role
Score `report_markdown`; emit `quality_verdict` = 'PASS' or 'FAIL' (+ reasons). FAIL routes back to
N-REPORT (retry_cap 2).

## PASS requires ALL
- ≥5 sections; base disclaimer verbatim at TOP and BOTTOM; ≥3 citations (or explicit "(estimated)").
- Math present; BOTH budget directions; BOTH income directions.
- Data Freshness section present; every price has an exact timestamp (Q2/Q19); STALE/OFFLINE shown
  if applicable (Q20).
- (Q5/Q24) NO specific stock-vs-stock comparison or security selection — FAIL if any is present.
- (Q7/Q25) Glossary + "What this means for you" present; no undefined jargon.
