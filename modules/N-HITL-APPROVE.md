---
node_id: N-HITL-APPROVE
tier: model-small
hitl: true
---
## Role
Single plain-text plan-approval pause (HITL, exit-11). Present the drafted plan/report in plain
English and ask the user to approve or request rework. This is the ONLY in-graph HITL node; DATA
intake stays wrapper-level (V-FIN-14 reinterpreted). On approve → emit; on rework → back to the
report (bounded, cap 2) with a caveat emitted on exhaustion.

## Outputs
- `plan_approved` (bool) — set by the human decision (approve).
- `rework_requested` (bool) — set by the human decision (request changes).

## Rules
Plain language only — no JSON / raw harness exposure. The pause is a single approval gate, not a
data-collection turn. Bounded rework: after cap 2 reworks, emit with a visible caveat rather than
looping forever.
