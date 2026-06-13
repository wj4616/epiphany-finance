"""Shared test scaffolding: make `wrapper` importable + provide common fixtures."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

BUILD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BUILD_DIR not in sys.path:
    sys.path.insert(0, BUILD_DIR)

GRAPH = os.path.join(BUILD_DIR, "graph.json")
FIXTURES = os.path.join(BUILD_DIR, "fixtures")


@pytest.fixture
def graph_path():
    return GRAPH


@pytest.fixture
def fixtures_dir():
    return FIXTURES


def load_persona(name):
    with open(os.path.join(FIXTURES, f"{name}.json")) as f:
        return json.load(f)


@pytest.fixture
def now():
    return datetime(2026, 6, 3, 20, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_prices():
    def _f(t):
        return ({"VTI": 372.45, "VXUS": 95.10, "BND": 72.10}[t], "2026-06-03T20:00:00Z")
    return _f


@pytest.fixture
def quote_data(now, mock_prices):
    from wrapper import quote
    from wrapper.state import FinanceState
    db = FinanceState(":memory:")
    db.import_state(load_persona("middle"))
    return quote.fetch_quotes(db.tickers(), db, now=now, fetcher=mock_prices)
