"""Wrapper-level conversational intake (IC-04 / APU-014 — NOT a HITL graph node). Plain-language,
one question at a time, forgiving free-text parsing, sensible defaults (Q7). Reusable by the CLI
and the Claude-Code agent. `run_intake` is fully injectable (input_fn/output_fn/scripted) so it is
deterministically testable, incl. V-FIN-26 (complete a report from minimal input).
"""
from __future__ import annotations

import re

_NUM = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m)?", re.I)


def extract_amount(text: str) -> float | None:
    """Pull the first dollar-ish amount from free text. '4k' -> 4000, '1,500' -> 1500."""
    if not text:
        return None
    m = _NUM.search(text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    suf = (m.group(2) or "").lower()
    return val * {"k": 1_000, "m": 1_000_000}.get(suf, 1)


def parse_holdings(text: str) -> list[dict]:
    """'VTI 60 shares, BND 50' -> [{ticker, shares}, ...]. Forgiving; skips junk."""
    out = []
    for chunk in re.split(r"[,;]| and ", text or ""):
        m = re.search(r"\b([A-Za-z]{1,5})\b.*?([\d,.]+)", chunk)
        if m:
            try:
                out.append({"ticker": m.group(1).upper(), "asset_class": "etf",
                            "shares": float(m.group(2).replace(",", "")), "cost_basis": None,
                            "last_known_price": None})
            except ValueError:
                continue
    return out


_QUESTIONS = [
    ("name", "What should I call you? (a name or nickname — used only to label your saved file)",
     "e.g. 'Alex' (press Enter for 'default')"),
    ("income", "About how much money comes in each month (take-home)?",
     "e.g. 'about $4,000' or '4k'"),
    ("housing", "How much do you pay for housing (rent or mortgage) each month?",
     "e.g. '$1,500'"),
    ("other_expenses", "Roughly how much for everything else each month (food, bills, transport)?",
     "e.g. '$1,200'"),
    ("location", "What city/area do you live in? (optional — press Enter to skip)",
     "e.g. 'Austin, TX'"),
    ("risk", "How do you feel about investment risk: cautious, balanced, or bold? (optional)",
     "default: balanced"),
    ("investments", "Any investments? List them, or press Enter to skip.",
     "e.g. 'VTI 60 shares, BND 50 shares'"),
    ("goals", "Any savings goal? (optional)", "e.g. 'emergency fund 10000' or 'house'"),
]

_RISK = {"cautious": "conservative", "conservative": "conservative", "balanced": "moderate",
         "moderate": "moderate", "bold": "aggressive", "aggressive": "aggressive"}


def run_intake(*, input_fn=input, output_fn=print, scripted: dict | None = None) -> dict:
    """Drive the guided intake. `scripted` (key->answer) bypasses prompts for tests/non-interactive.
    Returns a financial_state dict ready for state.import_state()."""
    def ask(key: str, prompt: str, example: str) -> str:
        if scripted is not None:
            return str(scripted.get(key, "") or "")
        output_fn(f"\n{prompt}\n  ({example})")
        try:
            return input_fn("> ").strip()
        except EOFError:
            return ""

    ans = {k: ask(k, p, e) for k, p, e in _QUESTIONS}

    income = extract_amount(ans["income"]) or 0.0
    housing = extract_amount(ans["housing"]) or 0.0
    other = extract_amount(ans["other_expenses"]) or 0.0
    location = ans["location"].strip() or None
    risk = _RISK.get(ans["risk"].strip().lower(), "moderate")
    holdings = parse_holdings(ans["investments"]) if ans["investments"].strip() else []
    goals = []
    if ans["goals"].strip():
        amt = extract_amount(ans["goals"])
        goals.append({"goal_name": re.sub(r"[\d$,. ]+", "_", ans["goals"]).strip("_") or "goal",
                      "target_amount": amt, "current_amount": 0, "priority": 1})

    state = {
        "profile": {"name": (ans["name"].strip() or "default"), "location": location,
                    "risk_tolerance": risk},
        "income_sources": ([{"source_name": "income", "amount_per_period": income,
                             "frequency": "monthly", "is_active": 1}] if income else []),
        "expenses": [e for e in [
            {"category": "housing", "amount": housing, "frequency": "monthly", "is_recurring": 1}
            if housing else None,
            {"category": "other", "amount": other, "frequency": "monthly", "is_recurring": 1}
            if other else None] if e],
        "assets": [], "debts": [], "portfolio_holdings": holdings, "transactions": [],
        "goals": goals, "investment_allocation_targets": [],
    }

    if scripted is None:                # plain-words confirmation (Q7)
        output_fn("\nGot it — here's what I heard:")
        output_fn(f"  • Income: ${income:,.0f}/mo")
        output_fn(f"  • Housing: ${housing:,.0f}/mo   • Other: ${other:,.0f}/mo")
        if location:
            output_fn(f"  • Location: {location}")
        if holdings:
            output_fn("  • Investments: " + ", ".join(f"{h['ticker']} {h['shares']:g}" for h in holdings))
        output_fn("I'll use sensible defaults for anything you skipped.\n")
    return state
