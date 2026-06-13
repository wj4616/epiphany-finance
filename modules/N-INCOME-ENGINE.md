---
node_id: N-INCOME-ENGINE
tier: model-large
---
## Role
BIDIRECTIONAL income analysis. Emit `income_plan`. Sequential after the budget engine.

## Both directions ALWAYS (DC-03)
- Direction A: "what you can afford now" (current_income_analysis).
- Direction B: "what you need + concrete paths to get there" — target_income_analysis,
  income_gap_passthrough, concrete_paths[], upskilling_suggestions[] (location-aware when available).

## Rules
Paths must be realistic and grounded in the job-market/location data; cite or mark "(estimated)".
If income_gap ≤ 0, say "you're sustainable" and focus on optimization. Plain, encouraging language.
