"""Deterministic financial math (appendix §3). Exact compound formulas WITH boundary guards
(build-plan fix D). Used by the wrapper and asserted by V-FIN-06 at parameter boundaries.
"""
from __future__ import annotations

INFLATION = 0.03


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


def portfolio_valuation(holdings: list[dict], prices: dict[str, dict]) -> dict:
    """Live valuation: per-holding current_value = shares × live_price; gains = current_value −
    cost_basis (DC-13 / APU-027). `prices` is quote_data['prices']. Holdings with no live price
    fall back to last_known_price and are flagged. Returns {holdings[], total_value, total_cost,
    total_gain}."""
    rows, total_v, total_c = [], 0.0, 0.0
    for h in holdings:
        t = h.get("ticker")
        q = prices.get(t) or {}
        price = q.get("price")
        used_fallback = price is None
        if used_fallback:
            price = h.get("last_known_price")
        shares = float(h.get("shares") or 0)
        cost = float(h.get("cost_basis") or 0)
        cur = round(shares * price, 2) if price is not None else None
        rows.append({"ticker": t, "shares": shares, "price": price, "current_value": cur,
                     "cost_basis": cost, "gain_loss": (round(cur - cost, 2) if cur is not None else None),
                     "source_ts": q.get("source_ts"), "fetch_ts": q.get("fetch_ts"),
                     "stale": q.get("stale", False), "price_unavailable": used_fallback})
        if cur is not None:
            total_v += cur
            total_c += cost
    return {"holdings": rows, "total_value": round(total_v, 2), "total_cost": round(total_c, 2),
            "total_gain": round(total_v - total_c, 2)}


def normalize_allocation(split: dict[str, float]) -> dict[str, float]:
    """Round to 1 decimal and force the parts to sum to 100 ± rounding (V-FIN-05)."""
    total = sum(split.values()) or 1.0
    scaled = {k: round(v / total * 100, 1) for k, v in split.items()}
    drift = round(100.0 - sum(scaled.values()), 1)
    if scaled and abs(drift) >= 0.1:
        first = next(iter(scaled))
        scaled[first] = round(scaled[first] + drift, 1)
    return scaled
