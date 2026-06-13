---
node_id: N-CHART-SPEC
tier: model-medium
---
## Role
Emit `chart_specs` (list of JSON specs the WRAPPER renders — never render here).

## Charts (appendix §7)
budget allocation pie; income gap bar; budget-at-target pie (if income_gap>0); investment split
pie; compound growth line (nominal + real); portfolio breakdown bar (if investments); goal progress.

## Each spec
{type, title, labels, values, x?, y?, series?, format:"png", path, skip?:bool, skip_reason?}.

## Rules
- (Q2) Price-dependent chart titles include the exact quote timestamp.
- (Q4) If quote_data.offline_flag or staleness>24h: set skip:true + skip_reason on price-dependent
  charts (portfolio breakdown; live-seeded growth) — do not present misleading data.
