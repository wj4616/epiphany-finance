"""SQLite persistence for epiphany-finance (IC-02 / APU-013 / APU-023).

8 financial tables + a quote_cache. Plain-text local DB in the user's home (a non-goal per spec:
no encryption — the wrapper discloses this to the user on first run). Atomic-ish writes via the
sqlite connection; export() produces the `financial_state` seed dict the graph reads.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

DEFAULT_DB = os.path.expanduser("~/.epiphany-finance/state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY, created_at TEXT, name TEXT, location TEXT,
    wealth_bracket TEXT, risk_tolerance TEXT);
CREATE TABLE IF NOT EXISTS income_sources (
    id INTEGER PRIMARY KEY, source_name TEXT, amount_per_period REAL,
    frequency TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY, category TEXT, description TEXT, amount REAL,
    frequency TEXT, is_recurring INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY, asset_type TEXT, description TEXT, estimated_value REAL);
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY, debt_type TEXT, description TEXT, balance REAL,
    interest_rate REAL, min_payment REAL);
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id INTEGER PRIMARY KEY, ticker TEXT, asset_class TEXT, shares REAL, cost_basis REAL,
    last_known_price REAL, last_updated TEXT,
    last_quote_fetch_ts TEXT, last_quote_price REAL, quote_staleness_warning INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY, recorded_at TEXT, description TEXT, amount REAL,
    direction TEXT, category TEXT, raw_text TEXT);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY, goal_name TEXT, target_amount REAL, current_amount REAL DEFAULT 0,
    target_date TEXT, priority INTEGER);
CREATE TABLE IF NOT EXISTS investment_allocation_targets (
    id INTEGER PRIMARY KEY, vehicle TEXT, target_pct REAL, expected_annual_return REAL,
    is_tax_advantaged INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS quote_cache (
    id INTEGER PRIMARY KEY, ticker TEXT UNIQUE, price REAL, fetch_ts TEXT,
    source_ts TEXT, fetch_success INTEGER, age_seconds INTEGER);
"""

# table -> ordered columns inserted on import (id auto)
_TABLES = {
    "user_profile": ["created_at", "name", "location", "wealth_bracket", "risk_tolerance"],
    "income_sources": ["source_name", "amount_per_period", "frequency", "is_active"],
    "expenses": ["category", "description", "amount", "frequency", "is_recurring"],
    "assets": ["asset_type", "description", "estimated_value"],
    "debts": ["debt_type", "description", "balance", "interest_rate", "min_payment"],
    "portfolio_holdings": ["ticker", "asset_class", "shares", "cost_basis", "last_known_price",
                           "last_updated", "last_quote_fetch_ts", "last_quote_price",
                           "quote_staleness_warning"],
    "transactions": ["recorded_at", "description", "amount", "direction", "category", "raw_text"],
    "goals": ["goal_name", "target_amount", "current_amount", "target_date", "priority"],
    "investment_allocation_targets": ["vehicle", "target_pct", "expected_annual_return",
                                      "is_tax_advantaged", "notes"],
}


class FinanceState:
    """Thin SQLite wrapper. Use as a context manager or call close()."""

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = os.path.expanduser(db_path)
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # WAL + a real busy timeout so overlapping runs queue instead of raising "database is
        # locked" (the module docstring's atomicity claim was previously unbacked).
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.DatabaseError:
            pass
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- lifecycle --
    def __enter__(self) -> "FinanceState":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def is_empty(self) -> bool:
        """True if there is no profile and no income/expenses — i.e. a first-time user."""
        cur = self.conn.execute("SELECT (SELECT COUNT(*) FROM user_profile) + "
                                "(SELECT COUNT(*) FROM income_sources) + "
                                "(SELECT COUNT(*) FROM expenses) AS n")
        return int(cur.fetchone()["n"]) == 0

    # -- import / export --
    def import_state(self, financial_state: dict, *, replace: bool = True) -> None:
        """Load a financial_state dict (persona fixture / intake output) into the DB."""
        cur = self.conn.cursor()
        if replace:
            for t in _TABLES:
                cur.execute(f"DELETE FROM {t}")
        prof = financial_state.get("profile")
        if prof:
            self._insert("user_profile", [{
                "created_at": prof.get("created_at"), "name": prof.get("name"),
                "location": prof.get("location"), "wealth_bracket": prof.get("wealth_bracket"),
                "risk_tolerance": prof.get("risk_tolerance", "moderate")}])
        key_for = {"income_sources": "income_sources", "expenses": "expenses", "assets": "assets",
                   "debts": "debts", "portfolio_holdings": "portfolio_holdings",
                   "transactions": "transactions", "goals": "goals",
                   "investment_allocation_targets": "investment_allocation_targets"}
        for table, key in key_for.items():
            rows = financial_state.get(key) or []
            if rows:
                self._insert(table, rows)
        self.conn.commit()

    def _insert(self, table: str, rows: list[dict]) -> None:
        cols = _TABLES[table]
        ph = ",".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})"
        self.conn.executemany(sql, [[r.get(c) for c in cols] for r in rows])

    def export(self) -> dict:
        """Produce the `financial_state` seed dict the graph reads (input contract §4)."""
        def rows(table: str) -> list[dict]:
            return [dict(r) for r in self.conn.execute(f"SELECT * FROM {table}")]

        prof_rows = rows("user_profile")
        profile = prof_rows[-1] if prof_rows else {"risk_tolerance": "moderate"}
        return {
            "profile": profile,
            "income_sources": rows("income_sources"),
            "expenses": rows("expenses"),
            "assets": rows("assets"),
            "debts": rows("debts"),
            "portfolio_holdings": rows("portfolio_holdings"),
            "transactions": rows("transactions"),
            "goals": rows("goals"),
            "investment_allocation_targets": rows("investment_allocation_targets"),
        }

    # -- quote cache (used by quote.py) --
    def read_quote_cache(self) -> dict[str, dict]:
        return {r["ticker"]: dict(r) for r in self.conn.execute("SELECT * FROM quote_cache")}

    def write_quote_cache(self, ticker: str, price: float | None, fetch_ts: str,
                          source_ts: str | None, fetch_success: bool, age_seconds: int) -> None:
        self.conn.execute(
            "INSERT INTO quote_cache (ticker, price, fetch_ts, source_ts, fetch_success, age_seconds) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
            "price=excluded.price, fetch_ts=excluded.fetch_ts, source_ts=excluded.source_ts, "
            "fetch_success=excluded.fetch_success, age_seconds=excluded.age_seconds",
            (ticker, price, fetch_ts, source_ts, int(fetch_success), age_seconds))
        self.conn.commit()

    def tickers(self) -> list[str]:
        return [r["ticker"] for r in
                self.conn.execute("SELECT ticker FROM portfolio_holdings WHERE ticker IS NOT NULL")]
