"""Per-user, session-independent persistence + dated descriptive report naming."""
import os
from datetime import datetime, timezone

import pytest
from conftest import load_persona

from wrapper import run, workspace
from wrapper.state import FinanceState


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Redirect the workspace root to a temp dir so tests never touch ~/.epiphany-finance."""
    root = str(tmp_path / "efin")
    monkeypatch.setattr(workspace, "ROOT", root)
    monkeypatch.setattr(workspace, "USERS_DIR", os.path.join(root, "users"))
    monkeypatch.setattr(workspace, "REGISTRY", os.path.join(root, "users.json"))
    return root


def test_report_basename_is_dated_and_descriptive():
    now = datetime(2026, 6, 4, 14, 48, 5, tzinfo=timezone.utc)
    bn = workspace.report_basename("report", now=now)
    assert bn == "2026-06-04_144805-financial-report"
    assert workspace.report_basename("budget", now=now).endswith("financial-budget-report")
    assert bn.startswith("2026-06-04")   # dated


def test_ensure_user_creates_folder_tree_and_registry(ws):
    slug = workspace.ensure_user("Alex Doe")
    assert slug == "alex-doe"
    d = workspace.user_dir(slug)
    assert os.path.isdir(d) and os.path.isdir(workspace.reports_dir(slug))
    assert os.path.isdir(workspace.sessions_dir(slug))
    assert os.path.exists(os.path.join(d, "profile.json"))
    assert workspace.last_user() == slug


def test_per_user_isolation(ws):
    a = workspace.ensure_user("Alice")
    b = workspace.ensure_user("Bob")
    assert workspace.db_path(a) != workspace.db_path(b)
    assert "alice" in workspace.db_path(a) and "bob" in workspace.db_path(b)


def test_data_persists_across_reopen(ws):
    slug = workspace.ensure_user("Sam")
    dbp = workspace.db_path(slug)
    with FinanceState(dbp) as db:
        db.import_state(load_persona("middle"))
    # reopen a fresh handle (simulates a future session) -> data still there
    with FinanceState(dbp) as db2:
        exp = db2.export()
        assert exp["profile"]["wealth_bracket"] == "middle"
        assert len(exp["portfolio_holdings"]) == 2
        assert not db2.is_empty()


def test_reports_are_dated_and_never_overwrite(ws, tmp_path):
    slug = workspace.ensure_user("Dana")
    db = FinanceState(workspace.db_path(slug))
    db.import_state(load_persona("destitute"))
    state = {"report_markdown": "## What this means for you\nx\n## Glossary\nETF: fund\n",
             "chart_specs": []}
    rdir = workspace.reports_dir(slug)
    bn1 = workspace.report_basename("report", now=datetime(2026, 6, 4, 9, 0, 0, tzinfo=timezone.utc))
    bn2 = workspace.report_basename("budget", now=datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc))
    for bn in (bn1, bn2):
        run.finalize(state, out_dir=rdir, quote_data={"prices": {}}, bracket="destitute",
                     fstate=db.export(), db=db, markdown=True, pdf_flag=False, basename=bn,
                     out=lambda *a: None)
    files = workspace.list_reports(slug)
    assert f"{bn1}.md" in files and f"{bn2}.md" in files     # both kept, not overwritten
    assert all("2026-06-04" in f for f in files)             # dated
    db.close()


# ---- --reset / --reset-all: the ONLY thing that erases the otherwise-persistent store ----
def _seed_user(name):
    slug = workspace.ensure_user(name)
    with FinanceState(workspace.db_path(slug)) as db:
        db.import_state(load_persona("middle"))
    return slug


def test_reset_user_wipes_only_that_user(ws):
    a, b = _seed_user("Alice"), _seed_user("Bob")
    summary = workspace.reset_user(a)
    assert summary["existed"] and summary["scope"] == "user"
    assert not os.path.isdir(workspace.user_dir(a))          # Alice's tree gone
    assert a not in workspace.list_users()                    # registry entry gone
    assert os.path.isdir(workspace.user_dir(b))               # Bob untouched
    assert b in workspace.list_users()


def test_reset_all_wipes_the_whole_store(ws):
    _seed_user("Alice"); _seed_user("Bob")
    summary = workspace.reset_all()
    assert summary["scope"] == "all" and set(summary["users"]) == {"alice", "bob"}
    assert not os.path.isdir(workspace.ROOT)                  # entire store gone
    assert workspace.list_users() == []


def test_reset_missing_user_is_noop(ws):
    assert workspace.reset_user("nobody")["existed"] is False  # idempotent, no raise


# ---- the flag, end-to-end through the CLI entrypoint (integration, not just the helper) ----
def test_cli_reset_persists_by_default_then_wipes_with_flag(ws):
    slug = _seed_user("Sam")
    # default behavior: data is STILL there across a fresh state handle (persistent)
    with FinanceState(workspace.db_path(slug)) as db:
        assert not db.is_empty()
    # --reset --yes (no prompt) wipes just this user via the real CLI main()
    assert run.main(["--reset", "--yes", "--user", "Sam"]) == 0
    assert "sam" not in workspace.list_users()
    assert not os.path.isdir(workspace.user_dir(slug))


def test_cli_reset_confirmation_guards_accidental_wipe(ws, monkeypatch):
    slug = _seed_user("Sam")
    monkeypatch.setattr("builtins.input", lambda *_a: "no")   # user declines the prompt
    assert run.main(["--reset", "--user", "Sam"]) == 0
    assert "sam" in workspace.list_users()                    # NOT deleted — cancelled
    assert os.path.isdir(workspace.user_dir(slug))
    monkeypatch.setattr("builtins.input", lambda *_a: "yes")  # user confirms
    assert run.main(["--reset", "--user", "Sam"]) == 0
    assert "sam" not in workspace.list_users()                # now wiped


def test_cli_reset_all_via_flag(ws):
    _seed_user("Alice"); _seed_user("Bob")
    assert run.main(["--reset-all", "--yes"]) == 0
    assert workspace.list_users() == []
    assert not os.path.isdir(workspace.ROOT)
