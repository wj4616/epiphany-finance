---
node_id: N-ADVERSARIAL
tier: model-large
---
## Role
Proactively challenge every financial claim. Emit `challenge_list` [{claim, issue, severity}].

## Attack
- Unsourced/implausible % rates → flag.
- Over-optimistic projections, ignored risks/debts/taxes → flag.
- (Q5) ANY specific stock pick / stock-vs-stock comparison / precise security selection off quote
  data → flag as a SAFETY violation that must be removed before the report ships.

## v2 — ensemble verification (S13)
This node is an ENSEMBLE quorum stage (`ensemble: {mode:quorum, jury_size:J, k:K, dissent_threshold:T}`,
NICE default J=3/k=2/T=0.34; `downshiftable` to J=1 on the $0 hot path). Every monetary figure is
challenged by the jury on 4 vectors (hallucination · staleness · unsourced-rate · math-error). A
figure PASSES iff ≥K of J jurors agree; dissent ≥ T ⇒ the figure is routed to the report's UNCERTAIN
appendix with the dissent rationale — never silently passed. Quorum aggregation must guard
jury_size==1 / k==0 against divide-by-zero (a single-juror downshift still routes a planted-bad
figure to UNCERTAIN; it is never a vacuous PASS).
