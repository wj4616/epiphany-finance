---
node_id: N-BUDGET-ENGINE
tier: model-large
---
## Role
Compute the BIDIRECTIONAL budget + investment allocation. Emit `budget_plan`.

## Both directions ALWAYS (DC-02)
- Direction A: income → allocation breakdown using the bracket method (appendix §1).
- Direction B: expenses + goals → `income_target`, `income_gap`.

## Investment sub-engine
- `investable_surplus = max(0, income − survival − fixed − debt_min − emergency_contrib − goal_savings)`.
- `suggested_allocation_split` by bracket + risk_tolerance (appendix §1), summing to 100 ± 1%.
- `compound_projections` for 1/5/10/20/30 yrs, monthly compounding (appendix §3 formulas).
  Use the r==0 / t==0 boundary guards. Provide BOTH nominal and real (÷1.03^t).

## Output `budget_plan`
{allocation_at_current_income, income_target, income_gap, investable_surplus,
 investment_allocation_monthly, suggested_allocation_split, compound_projections}.

## Rules
Cite or mark "(estimated)" every rate. Never negative surplus. Show the formula inputs so
N-VERIFY-BUDGET can re-check the math.
