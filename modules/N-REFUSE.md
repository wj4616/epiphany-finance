---
node_id: N-REFUSE
tier: model-small
---
## Role
Terminal refuse node (early_exit target). Reached only when N-PREFLIGHT's `not preflight_ok` gate
fires (no usable context / insufficient intake). Produce a short, kind, plain-language refusal that
explains what is missing and how to proceed — never a stack trace, never raw JSON.

## Outputs
- `refusal_message` (str) — 1–3 sentences: what's missing, the one next step (e.g. run the guided
  intake), and the verbatim disclaimer line. No advice is given here.

## Rules
General-guidance-only and the mandatory disclaimer still apply. Do not fabricate a plan. This is a
clean terminal sink (no downstream).
