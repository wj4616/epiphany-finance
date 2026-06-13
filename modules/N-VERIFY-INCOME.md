---
node_id: N-VERIFY-INCOME
tier: model-medium
---
## Role
Re-check `income_plan`. Emit `income_verdict` {pass: bool, issues[]}.

## Checks
Both directions present; concrete_paths exist and are plausible vs market data; salary figures
cited or "(estimated)"; internal consistency with income_gap. Fail with specifics.
