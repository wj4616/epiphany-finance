"""Live stock/ETF quotes via yfinance, with caching + offline fallback (Q1/Q2/Q3, fix E).

- Always seek FRESH: refresh a ticker when its cached quote is older than QUOTE_TTL (5 min). The
  5-min TTL also satisfies the ≤1-request/60s/ticker rate-limit floor (DC-16).
- Every price carries the EXACT ISO8601 fetch time AND the market data source_ts (Yahoo data may
  be delayed — we keep both so the user can trace it).
- On yfinance failure / empty data: fall back to the cached price with offline_flag + a very
  explicit warning. >24h old => STALE.

The yfinance call and the clock are injectable so the whole module is deterministically testable
offline (no network needed in CI).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

QUOTE_TTL = 300          # seconds: refresh if cached quote is older than this (also the 60s floor)
STALE_SECONDS = 24 * 3600


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _yf_fetch(ticker: str) -> tuple[float, str]:
    """Default live fetcher: returns (price, market_source_ts_iso). Raises on any failure."""
    import yfinance as yf  # lazy import
    hist = yf.Ticker(ticker).history(period="1d")
    if hist is None or len(hist) == 0:
        raise RuntimeError(f"no data for {ticker}")
    price = float(hist["Close"].iloc[-1])
    ts = hist.index[-1].to_pydatetime().astimezone(timezone.utc)
    return price, _iso(ts)


def _hc1_wrap(fetcher: Callable[[str], tuple], *, retries: int = 2):
    """HC-1 (finv2 S11): wrap the per-ticker network fetcher in the harness tool retry+cache
    primitive — a TRANSIENT failure retries before the OFFLINE fallback, and a repeat same-ticker
    fetch this call serves from cache. Graceful: if the primitive isn't importable (skill run
    off-harness), the raw fetcher is returned unchanged."""
    try:
        from goatcs_harness.tool_retry_cache import ToolRetryCache, DEFAULT_RETRYABLE
    except Exception:                              # noqa: BLE001 — off-harness: no-op
        return fetcher
    # N1: the real fetcher is yfinance/requests. requests.exceptions.* already subclass OSError
    # (in DEFAULT_RETRYABLE), but yfinance can leak the underlying urllib3 transient classes, which
    # do NOT — so a connection-reset / connect-or-read timeout would otherwise skip retry and drop
    # straight to OFFLINE. Widen retry_on to those two (TimeoutError covers Connect/Read/NewConnection
    # timeouts); deliberately NOT the HTTPError base (catches non-transient SSL/decode) or MaxRetryError
    # (can wrap a permanent failure). Import-guarded: urllib3 absent → the harness default stands.
    retry_on = DEFAULT_RETRYABLE
    try:
        from urllib3.exceptions import ProtocolError as _U3Proto, TimeoutError as _U3Timeout
        retry_on = DEFAULT_RETRYABLE + (_U3Proto, _U3Timeout)
    except Exception:                              # noqa: BLE001 — urllib3 absent: default stands
        pass
    trc = ToolRetryCache(retries=retries, backoff_s=0.0, retry_on=retry_on)
    wrapped = trc.wrap("quote.fetch", lambda args, _policy: {"r": fetcher(args["ticker"])})

    def _fetch(ticker):
        return wrapped({"ticker": ticker}, None)["r"]
    _fetch._hc1 = trc                              # expose for tests/observability
    return _fetch


def fetch_quotes(tickers, state, *, now: datetime | None = None,
                 fetcher: Callable[[str], tuple[float, str]] | None = None) -> dict:
    """Return a `quote_data` dict for the graph (and the report). Pure given `now`+`fetcher`.

    quote_data = {quote_fetch_ts, prices{ticker:{price, source_ts, fetch_ts, staleness_minutes,
                  stale, from_cache}}, fetch_success, offline_flag, warnings[]}.
    """
    now = now or datetime.now(timezone.utc)
    fetcher = _hc1_wrap(fetcher or _yf_fetch)      # HC-1 retry+cache on the real network fetch
    cache = state.read_quote_cache() if state is not None else {}
    prices: dict[str, dict] = {}
    warnings: list[str] = []
    any_offline = False
    all_success = True

    for ticker in dict.fromkeys(tickers):          # de-dup, order-preserving
        cached = cache.get(ticker)
        cached_fetch = _parse_iso(cached["fetch_ts"]) if cached else None
        fresh_enough = bool(cached_fetch and (now - cached_fetch).total_seconds() < QUOTE_TTL
                            and cached.get("price") is not None)
        if fresh_enough:
            price, source_ts, fetch_ts, from_cache = (
                cached["price"], cached.get("source_ts"), cached["fetch_ts"], True)
        else:
            try:
                price, source_ts = fetcher(ticker)
                fetch_ts = _iso(now)
                from_cache = False
                if state is not None:
                    state.write_quote_cache(ticker, price, fetch_ts, source_ts, True, 0)
            except Exception as ex:                # network/API failure -> offline fallback
                all_success = False
                if cached and cached.get("price") is not None:
                    price, source_ts, fetch_ts, from_cache = (
                        cached["price"], cached.get("source_ts"), cached["fetch_ts"], True)
                    any_offline = True
                    warnings.append(
                        f"OFFLINE: could not reach Yahoo Finance for {ticker} ({type(ex).__name__}); "
                        f"using the last saved price from {fetch_ts}. Please verify before acting.")
                else:
                    prices[ticker] = {"price": None, "source_ts": None, "fetch_ts": _iso(now),
                                      "staleness_minutes": None, "stale": True, "from_cache": False,
                                      "unavailable": True}
                    warnings.append(f"OFFLINE: no price available for {ticker} (no cached value).")
                    continue

        src = _parse_iso(source_ts) or _parse_iso(fetch_ts) or now
        age_s = max(0.0, (now - src).total_seconds())     # clamp: a clock-ahead EOD stamp -> 0, not negative
        staleness_min = int(age_s // 60)
        stale = age_s > STALE_SECONDS
        if stale:
            warnings.append(f"STALE: {ticker} price is over 24h old (market data {source_ts}). "
                            f"It may not reflect current market conditions.")
        prices[ticker] = {"price": price, "source_ts": source_ts, "fetch_ts": fetch_ts,
                          "staleness_minutes": staleness_min, "stale": stale, "from_cache": from_cache}

    return {
        "quote_fetch_ts": _iso(now),
        "prices": prices,
        "fetch_success": all_success,
        "offline_flag": any_offline or not all_success,
        "warnings": warnings,
    }


def data_freshness_section(quote_data: dict | None) -> str:
    """The mandatory 'Data Freshness' report section (Q19/Q20/DC-14). Deterministic — the wrapper
    guarantees it regardless of the LLM, with exact timestamps + explicit STALE/OFFLINE warnings."""
    lines = ["## Data Freshness", ""]
    if not quote_data or not (quote_data.get("prices")):
        lines.append("No investment prices were needed for this report.")
        return "\n".join(lines) + "\n"
    lines.append(f"Investment prices are from Yahoo Finance. Quotes fetched at "
                 f"**{quote_data.get('quote_fetch_ts')}** (exact, UTC). Yahoo data may be delayed.")
    if quote_data.get("offline_flag"):
        lines.append("\n> ⚠️ **OFFLINE:** Yahoo Finance could not be reached. The prices below are "
                     "cached from an earlier fetch and **may be outdated — please verify before "
                     "acting.**")
    any_stale = any(p.get("stale") for p in quote_data["prices"].values())
    if any_stale:
        lines.append("\n> ⚠️ **STALE:** one or more prices are over 24 hours old and may not "
                     "reflect current market conditions.")
    lines.append("")
    for t, q in quote_data["prices"].items():
        lines.append(f"- {format_price(t, q)}")
    for w in quote_data.get("warnings", []):
        lines.append(f"- _{w}_")
    return "\n".join(lines) + "\n"


def format_price(ticker: str, q: dict) -> str:
    """Human, fully-traceable price string (Q2). Used in the report and tests."""
    if q.get("price") is None:
        return f"{ticker}: price unavailable (OFFLINE)"
    tag = " — STALE" if q.get("stale") else (" — OFFLINE/cached" if q.get("from_cache") else "")
    return (f"{ticker}: ${q['price']:.2f} (market data {q.get('source_ts')}, "
            f"fetched {q.get('fetch_ts')}, {q.get('staleness_minutes')} min old){tag}")
