---
node_id: N-QUOTE-FETCHER
tier: no-llm
---
## Role
Expose live equity/ETF quotes to the graph. v2 upgrade (S11): the quote PATH is HC-1-backed
(`wrapper/quote.py` wraps the network fetch in the harness tool retry+cache — transient failures
retry before the OFFLINE fallback; a repeat same-ticker fetch this call serves from cache) and the
node declares an HC-4 typed `output_schema` on `quote_data`. The `tool_call` carries `retry_cache`.

## Outputs
- `quote_data` (dict) — `{quote_fetch_ts, prices:{ticker:{price, source_ts, fetch_ts,
  staleness_minutes, stale, from_cache}}, fetch_success, offline_flag, warnings[]}`.

## Freshness semantics (carried verbatim from v1.2.0)
Every price shows the ISO-8601 fetch + market timestamp + age. >5 min → refresh; yfinance down →
cached price with a loud OFFLINE warning; >24h → STALE. Regimes: FRESH/CACHED/STALE/OFFLINE.

## Rules
General-guidance-only: quotes are for valuation + broad rebalancing, never specific stock picks.
