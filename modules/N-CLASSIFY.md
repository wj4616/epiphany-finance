---
node_id: N-CLASSIFY
tier: model-medium
---
## Role
Classify the user and set routing flags.

## Outputs
- `wealth_bracket` ∈ {destitute, homeless, working-poor, lower, lower-middle, middle,
  upper-middle, wealthy, ultra-HNW} (see appendix §1).
- `situation_class` ∈ {employed, unemployed, entrepreneur, retired, student, other}.
- `has_investment_flag` (bool) — true iff parsed_context.portfolio_holdings is non-empty.
- `location_available_flag` (bool) — true iff a usable location is present.
- `priority_flags` — e.g. {emergency: bool, debt_crisis: bool, housing_risk: bool}.

## Rules
Base the bracket on net worth + income + stability, not income alone. When borderline, choose the
LOWER bracket (more conservative, more protective guidance).

## v2 additions (S9)
Additionally emit:
- `benefit_dependency_flags` — `{ssdi, ssi, medicaid, snap}` (bools) detected from intake; drives the
  benefit-safety node (N-BENEFIT-SAFETY) and the survival report frame.
- `data_freshness_regime` seed — `FRESH|CACHED|STALE|OFFLINE` plumbing carried forward and consumed
  by N-CHART-SPEC to skip price charts on STALE/OFFLINE (signal-driven, not a routing edge).
