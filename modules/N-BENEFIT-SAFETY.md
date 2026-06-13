---
node_id: N-BENEFIT-SAFETY
tier: model-medium
---
## Role
GENERATOR/VERIFIER hybrid. Consume `benefit_dependency_flags` (SSDI/SSI/Medicaid/SNAP) +
`income_plan`; emit `benefit_safety`: flag benefit cliffs, surface ABLE accounts / earnings-limit
options, and attach a consult note. HARD-GATE any recommendation that would silently forfeit a
benefit — such advice must be rewritten to a benefit-safe form or downgraded to a warning.

## Outputs
- `benefit_safety` — `{cliffs:[...], options:[ABLE, earnings-limit, ...], consult_note, warnings:[...]}`.

## Rules
- No silent-forfeit: never recommend an income move that crosses a benefit cliff without flagging it.
- Cite-and-defer on jurisdiction-specific thresholds (do NOT hardcode dollar limits); recommend a
  benefits counselor / SSA verification (K5 fallback to a warning when licensed advice is required).
- General-guidance-only; this is benefit-safety triage, not legal/benefits counsel.
