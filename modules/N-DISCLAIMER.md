---
node_id: N-DISCLAIMER
tier: model-small
---
## Role
Select the BRACKET-SPECIFIC disclaimer additions. Emit `compliance_wrap`.

## Rules (fix C)
The BASE disclaimer is a verbatim constant injected by the wrapper — do NOT rewrite or paraphrase
it. Here, only choose additions (appendix §4): destitute/homeless → emergency-resources line;
ultra-HNW → legal-tax-only line. Output {bracket_additions[]}.
