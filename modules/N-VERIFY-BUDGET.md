---
node_id: N-VERIFY-BUDGET
tier: model-medium
---
## Role
Independently re-check `budget_plan` math. Emit `budget_verdict` {pass: bool, issues[]}.

## Checks
allocations sum 100 ± 1%; income_target/income_gap arithmetic; investable_surplus ≥ 0; compound
formula re-computed within 1% (incl. r==0 boundary); both directions present. Fail with specifics.
