"""Deterministic acceptance checks — the machine backing for N-QUALITY-GATE and the V-battery.
Each returns (ok: bool, detail: str). The wrapper can run these post-graph as a final guard; the
tests assert them directly. Honest scope: these catch structural/safety/usability regressions that
do not need an LLM to detect.
"""
from __future__ import annotations

import re

from .disclaimer import BASE_DISCLAIMER

ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
PRICE = re.compile(r"\$\s?\d[\d,]*\.\d{2}")
# Imperative security-selection language off quote data (Q5/DC-07). Broad ETFs are allowed.
_ALLOWED_TICKERS = {"VTI", "VXUS", "BND", "VOO", "VT", "VTV", "SCHB", "ITOT", "AGG", "VNQ"}
# Common ALL-CAPS words/acronyms that look like tickers but aren't — so "sell your CAR", "CASH vs
# DEBT", "RENT versus OWN" don't false-positive (the LLM gate is the primary screen; this is a net).
_NOT_TICKERS = {
    "CASH", "DEBT", "CAR", "RENT", "OWN", "BUY", "SELL", "HYSA", "ETF", "ETFS", "ABLE", "SSI",
    "SSDI", "SNAP", "SSA", "IRA", "ROTH", "HSA", "CD", "CDS", "APR", "APY", "FDIC", "AI", "PDF",
    "ID", "OK", "DIY", "TBD", "FAQ", "CFP", "CPA", "LLC", "EU", "UK", "USA", "US", "VS", "AND",
    "OR", "THE", "YOU", "NOW", "ALL", "ANY", "REIT", "ESG", "TIPS", "HOUSE", "HOME", "FOOD",
    "BILLS", "LOAN", "AUTO", "GAS", "PAY", "JOB",
}
# Verb match is case-insensitive (catches sentence-initial "Dump GME"); the TICKER stays UPPERCASE
# (a scoped (?i:) flag on the verb only) so case-insensitivity doesn't itself add false positives.
_STOCK_PICK = re.compile(
    r"\b(?i:buy|sell|short|overweight|underweight|pick|dump|load up on|go long|go short)\b"
    r"[^.\n]{0,40}?\b([A-Z]{2,5})\b")
_VS = re.compile(r"\b([A-Z]{2,5})\b\s*(?:vs\.?|versus|over|instead of)\s*\b([A-Z]{2,5})\b")


def disclaimer_top_and_bottom(md: str) -> tuple[bool, str]:
    d = BASE_DISCLAIMER.strip()
    # window must fit BASE (~1081) + up to TWO appended additions (bracket + benefit, ~500) at the
    # bottom, or the base overflows the window and a present disclaimer reads as missing.
    head = md[:2400]
    tail = md[-2400:]
    ok = d in head and d in tail
    return ok, "verbatim disclaimer present at top and bottom" if ok else "disclaimer missing/altered at top or bottom"


def data_freshness_present(md: str) -> tuple[bool, str]:
    ok = "## Data Freshness" in md
    return ok, "Data Freshness section present" if ok else "missing Data Freshness section"


def every_price_has_timestamp(md: str) -> tuple[bool, str]:
    """Every $-price line must have an ISO timestamp nearby (Q2/Q22). Checks per line."""
    bad = []
    for ln in md.splitlines():
        if PRICE.search(ln) and not re.search(ISO, ln):
            # only enforce on lines that actually name a security (a ticker token) — aggregate
            # dollar figures in budget prose / totals are not per-quote prices and need no timestamp.
            if re.search(r"\b[A-Z]{2,5}\b", ln):
                bad.append(ln.strip()[:80])
    ok = not bad
    return ok, "all quote prices carry an exact timestamp" if ok else f"prices without timestamp: {bad[:3]}"


def stale_or_offline_flagged(md: str, quote_data: dict | None) -> tuple[bool, str]:
    if not quote_data:
        return True, "no quotes"
    needs = quote_data.get("offline_flag") or any(
        p.get("stale") for p in (quote_data.get("prices") or {}).values())
    if not needs:
        return True, "quotes fresh"
    ok = ("STALE" in md) or ("OFFLINE" in md)
    return ok, "STALE/OFFLINE warning shown" if ok else "stale/offline quotes not warned in report"


def no_individual_stock_picks(md: str) -> tuple[bool, str]:
    """Q5/DC-07/V-FIN-24: no imperative buy/sell of a specific (non-broad-ETF) ticker, and no
    stock-vs-stock comparison."""
    for m in _STOCK_PICK.finditer(md):
        tick = m.group(1)
        if tick not in _ALLOWED_TICKERS and tick not in _NOT_TICKERS and tick.isupper() and len(tick) >= 2:
            return False, f"specific security-selection language: '{m.group(0).strip()}'"
    for vs in _VS.finditer(md):
        pair = {vs.group(1), vs.group(2)}
        if pair <= _ALLOWED_TICKERS or pair & _NOT_TICKERS:
            continue
        return False, f"stock-vs-stock comparison: '{vs.group(0).strip()}'"
    return True, "no individual stock picks / comparisons"


def has_glossary(md: str) -> tuple[bool, str]:
    ok = bool(re.search(r"#+\s*Glossary", md, re.I))
    return ok, "glossary present" if ok else "missing Glossary section"


def has_what_this_means(md: str) -> tuple[bool, str]:
    ok = "what this means for you" in md.lower()
    return ok, "plain-language summary present" if ok else "missing 'What this means for you'"


def both_budget_directions(budget_plan: dict | None) -> tuple[bool, str]:
    bp = budget_plan or {}
    a = "allocation_at_current_income" in bp
    b = "income_target" in bp and "income_gap" in bp
    return (a and b), "both budget directions present" if (a and b) else "budget missing a direction"


def both_income_directions(income_plan: dict | None) -> tuple[bool, str]:
    ip = income_plan or {}
    a = "current_income_analysis" in ip
    b = "target_income_analysis" in ip and "concrete_paths" in ip
    return (a and b), "both income directions present" if (a and b) else "income missing a direction"


REPORT_CHECKS = [disclaimer_top_and_bottom, data_freshness_present, every_price_has_timestamp,
                 no_individual_stock_picks, has_glossary, has_what_this_means]


def run_report_checks(md: str, quote_data: dict | None = None) -> list[tuple[str, bool, str]]:
    out = [(c.__name__, *c(md)) for c in REPORT_CHECKS]
    out.append(("stale_or_offline_flagged", *stale_or_offline_flagged(md, quote_data)))
    return out
