"""Deterministic financial math (appendix §3). Exact compound formulas WITH boundary guards
(build-plan fix D). Used by the wrapper and asserted by V-FIN-06 at parameter boundaries.

Audit-2026-06-14 (Q2 — move the trust boundary): these functions are now WIRED into the live report
(`run.finalize` injects a deterministic "Your Numbers" block) instead of being a tested-but-orphaned
reference impl that the LLM nodes silently shadowed. `to_monthly` supplies the previously-missing
frequency normalization ("everything to monthly").
"""
from __future__ import annotations

import math

INFLATION = 0.03

# Default index nominal/real used for the deterministic projection block (appendix §2; cited as
# "(estimated)" in the report — never presented as a guarantee).
DEFAULT_NOMINAL = 0.10
DEFAULT_REAL = 0.07

# Frequency → monthly multiplier (appendix §3 "everything to monthly"). 52 weeks / 12 months and
# 26 biweekly periods / 12 are the canonical factors; annual ÷12; quarterly ÷3; semimonthly ×2.
FREQ_TO_MONTHLY = {
    "monthly": 1.0, "month": 1.0, "mo": 1.0,
    "weekly": 52.0 / 12.0, "week": 52.0 / 12.0, "wk": 52.0 / 12.0,
    "biweekly": 26.0 / 12.0, "fortnightly": 26.0 / 12.0, "every two weeks": 26.0 / 12.0,
    "semimonthly": 2.0, "twice a month": 2.0, "bimonthly": 0.5,
    "quarterly": 1.0 / 3.0, "quarter": 1.0 / 3.0,
    "annual": 1.0 / 12.0, "annually": 1.0 / 12.0, "yearly": 1.0 / 12.0, "year": 1.0 / 12.0,
    "daily": 365.0 / 12.0, "day": 365.0 / 12.0,
}


def to_monthly(amount: float, frequency: str | None) -> float:
    """Normalize any cadence to a monthly amount (appendix §3). Unknown/blank frequency is assumed
    already-monthly (the schema's stored default), never a silent ×/÷ guess."""
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(amt):
        return 0.0
    factor = FREQ_TO_MONTHLY.get((frequency or "monthly").strip().lower(), 1.0)
    return amt * factor


def _sum_monthly(items: list[dict], amount_key: str, freq_key: str = "frequency") -> float:
    total = 0.0
    for it in items or []:
        if it.get("is_active", 1) in (0, False, "0", "false"):
            continue
        total += to_monthly(it.get(amount_key), it.get(freq_key))
    return round(total, 2)


def monthly_numbers(fstate: dict) -> dict:
    """Deterministic monthly income / expenses / surplus from the saved state, with every cadence
    normalized to monthly. The single source of truth for the figures shown to the user (Q2)."""
    income = _sum_monthly((fstate or {}).get("income_sources") or [], "amount_per_period")
    expenses_items = (fstate or {}).get("expenses") or []
    expenses = _sum_monthly(expenses_items, "amount")
    by_cat: dict[str, float] = {}
    for e in expenses_items:
        cat = e.get("category") or "other"
        by_cat[cat] = round(by_cat.get(cat, 0.0) + to_monthly(e.get("amount"), e.get("frequency")), 2)
    return {"monthly_income": income, "monthly_expenses": expenses,
            "monthly_surplus": round(income - expenses, 2), "expenses_by_category": by_cat}


def compound(pmt: float, annual_rate: float, years: float, principal: float = 0.0) -> float:
    """Future value with monthly compounding + monthly contributions.

    A = P(1+r/12)^(12t) + PMT·[(1+r/12)^(12t) − 1]/(r/12)

    Boundary guards (fix D):
      - r == 0  -> A = P + PMT·12·t           (the limit; avoids /0)
      - t == 0  -> A = P
    """
    if years <= 0:
        return float(principal)
    n = 12 * years
    if annual_rate == 0:
        return float(principal + pmt * n)
    r = annual_rate / 12.0
    growth = (1 + r) ** n
    return float(principal * growth + pmt * (growth - 1) / r)


def real_value(nominal: float, years: float, inflation: float = INFLATION) -> float:
    """Inflation-adjusted (real) value: nominal ÷ (1+infl)^t."""
    if years <= 0:
        return float(nominal)
    return float(nominal / (1 + inflation) ** years)


def projection_table(pmt: float, annual_rate: float, principal: float = 0.0,
                     horizons=(1, 5, 10, 20, 30)) -> list[dict]:
    """Per-horizon {years, nominal, real} rows for the compound-growth chart + report."""
    out = []
    for t in horizons:
        nom = compound(pmt, annual_rate, t, principal)
        out.append({"years": t, "nominal": round(nom, 2), "real": round(real_value(nom, t), 2)})
    return out


def investable_surplus(income: float, survival: float, fixed: float, debt_min: float,
                       emergency_contrib: float, goal_savings: float) -> float:
    """Monthly dollars free to invest — never negative (appendix §3)."""
    return max(0.0, income - survival - fixed - debt_min - emergency_contrib - goal_savings)


def _valid_price(p) -> bool:
    """A usable quote: a finite, strictly-positive number. Rejects None, NaN/inf, and 0/negative —
    a 0 or NaN return from a quote source is BAD DATA, not a real $0 valuation (audit F7 / NaN)."""
    return isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) and p > 0


def portfolio_valuation(holdings: list[dict], prices: dict[str, dict]) -> dict:
    """Live valuation: per-holding current_value = shares × live_price; gains = current_value −
    cost_basis (DC-13 / APU-027). `prices` is quote_data['prices']. Holdings with no usable live
    price fall back to last_known_price (flagged `used_fallback`); holdings with NO usable price at
    all are EXCLUDED from both totals (so total_gain is never over/understated) and counted in
    `excluded_count` so the caller can warn. Returns {holdings[], total_value, total_cost,
    total_gain, fallback_count, excluded_count}."""
    rows, total_v, total_c = [], 0.0, 0.0
    fallback_count = excluded_count = 0
    for h in holdings:
        t = h.get("ticker")
        q = prices.get(t) or {}
        price = q.get("price")
        used_fallback = not _valid_price(price)
        if used_fallback:
            price = h.get("last_known_price")
        usable = _valid_price(price)
        shares = float(h.get("shares") or 0)
        cost = float(h.get("cost_basis") or 0)
        cur = round(shares * price, 2) if usable else None
        if usable and used_fallback:
            fallback_count += 1
        if not usable:
            excluded_count += 1
        rows.append({"ticker": t, "shares": shares, "price": (price if usable else None),
                     "current_value": cur, "cost_basis": cost,
                     "gain_loss": (round(cur - cost, 2) if cur is not None else None),
                     "source_ts": q.get("source_ts"), "fetch_ts": q.get("fetch_ts"),
                     "stale": q.get("stale", False),
                     "price_unavailable": cur is None, "used_fallback": usable and used_fallback})
        if cur is not None:
            total_v += cur
            total_c += cost
    return {"holdings": rows, "total_value": round(total_v, 2), "total_cost": round(total_c, 2),
            "total_gain": round(total_v - total_c, 2),
            "fallback_count": fallback_count, "excluded_count": excluded_count}


def projection_from_surplus(monthly_surplus: float, *, nominal: float = DEFAULT_NOMINAL,
                            horizons=(1, 5, 10, 20, 30)) -> list[dict]:
    """Deterministic projection of investing the monthly SURPLUS (>0 only) at an estimated index
    rate — the wrapper-computed figures that replace the LLM's prior guesses (Q2)."""
    pmt = max(0.0, float(monthly_surplus or 0))
    return projection_table(pmt, nominal, principal=0.0, horizons=horizons)


def normalize_allocation(split: dict[str, float]) -> dict[str, float]:
    """Round to 1 decimal and force the parts to sum to 100 ± rounding (V-FIN-05). An all-zero (or
    empty) input returns zeros — never a fabricated "100% to the first bucket" (audit F5)."""
    if not split:
        return {}
    total = sum(split.values())
    if total == 0:
        return {k: 0.0 for k in split}
    scaled = {k: round(v / total * 100, 1) for k, v in split.items()}
    drift = round(100.0 - sum(scaled.values()), 1)
    if scaled and abs(drift) >= 0.1:
        first = next(iter(scaled))
        scaled[first] = round(scaled[first] + drift, 1)
    return scaled
