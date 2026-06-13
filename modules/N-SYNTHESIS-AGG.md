---
node_id: N-SYNTHESIS-AGG
tier: model-large
---
## Role
AND-join verifiers (budget, income, adversarial) + the portfolio slot (bypass when no investments).
Reconcile and apply challenges. Emit `verified_advice`.

## Rules
Remove or fix everything in challenge_list before passing it on — especially Q5 safety violations.
If a verifier failed, incorporate its fix or downgrade the affected claim. `portfolio_plan` may be
null (no investments) — that is fine.
