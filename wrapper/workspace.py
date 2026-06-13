"""Per-user, session-independent persistence layout for epiphany-finance.

All app data lives under ~/.epiphany-finance/users/<slug>/ so it survives the agent clearing its
session. Each user gets their own folder holding their SQLite state, dated reports, charts, harness
sessions, and a profile. A top-level registry tracks users + the last-used one.

    ~/.epiphany-finance/
      users.json                      # registry: slug -> {name, created, last_used}
      users/
        <slug>/
          state.db                    # this user's SQLite (profile, income, quotes, ...)
          profile.json                # name, created, last_run, run_count
          reports/  <date>-financial-<mode>-report.md / .pdf / -charts/
          sessions/ <timestamp>/      # harness ledger per run (persisted, replayable)
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone

ROOT = os.path.expanduser("~/.epiphany-finance")
USERS_DIR = os.path.join(ROOT, "users")
REGISTRY = os.path.join(ROOT, "users.json")


def slugify(name: str | None) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "default"


def _load_registry() -> dict:
    try:
        with open(REGISTRY, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_registry(reg: dict) -> None:
    os.makedirs(ROOT, exist_ok=True)
    tmp = REGISTRY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)
    os.replace(tmp, REGISTRY)


def last_user() -> str | None:
    """Slug of the most-recently-used user (so a returning user needs no flag)."""
    reg = _load_registry()
    if not reg:
        return None
    return max(reg, key=lambda s: reg[s].get("last_used", ""))


def user_dir(slug: str) -> str:
    return os.path.join(USERS_DIR, slug)


def reports_dir(slug: str) -> str:
    return os.path.join(user_dir(slug), "reports")


def sessions_dir(slug: str) -> str:
    return os.path.join(user_dir(slug), "sessions")


def db_path(slug: str) -> str:
    return os.path.join(user_dir(slug), "state.db")


def ensure_user(name_or_slug: str | None, *, name: str | None = None, now: datetime | None = None) -> str:
    """Create (or touch) a user's folder tree; update the registry + profile. Returns the slug."""
    now = now or datetime.now(timezone.utc)
    slug = slugify(name_or_slug)
    d = user_dir(slug)
    for sub in (d, reports_dir(slug), sessions_dir(slug)):
        os.makedirs(sub, exist_ok=True)
    reg = _load_registry()
    entry = reg.get(slug, {"name": name or name_or_slug or slug, "created": now.isoformat()})
    if name:
        entry["name"] = name
    entry["last_used"] = now.isoformat()
    reg[slug] = entry
    _save_registry(reg)
    # per-user profile.json (run_count for persistence visibility)
    ppath = os.path.join(d, "profile.json")
    try:
        prof = json.load(open(ppath, encoding="utf-8"))
    except (OSError, ValueError):
        prof = {"slug": slug, "name": entry["name"], "created": entry["created"], "run_count": 0}
    prof["name"] = entry["name"]
    prof["last_run"] = now.isoformat()
    prof["run_count"] = int(prof.get("run_count", 0)) + 1
    with open(ppath, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2)
    return slug


def report_basename(mode: str, *, now: datetime | None = None) -> str:
    """Descriptive, dated, collision-safe base filename (no extension)."""
    now = now or datetime.now(timezone.utc)
    mode = mode or "report"
    label = "financial-report" if mode == "report" else f"financial-{mode}-report"
    return f"{now.strftime('%Y-%m-%d_%H%M%S')}-{label}"


def list_reports(slug: str) -> list[str]:
    d = reports_dir(slug)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith((".md", ".pdf")))


def list_users() -> list[str]:
    """Slugs of every saved user, in the registry."""
    return list(_load_registry().keys())


def _count_sessions(slug: str) -> int:
    d = sessions_dir(slug)
    return len(os.listdir(d)) if os.path.isdir(d) else 0


def reset_user(slug: str) -> dict:
    """Permanently delete ONE user's data: their whole folder tree (state.db, reports, sessions,
    profile) + their registry entry. Returns a summary of what was removed (computed before delete,
    so it is accurate even though the folder is gone). Idempotent — a missing user just reports
    ``existed: False``. Other users and the store are untouched."""
    d = user_dir(slug)
    summary = {"scope": "user", "slug": slug, "path": d, "existed": os.path.isdir(d),
               "reports": len(list_reports(slug)), "sessions": _count_sessions(slug)}
    if os.path.isdir(d):
        shutil.rmtree(d)
    reg = _load_registry()
    if slug in reg:
        del reg[slug]
        _save_registry(reg)
    return summary


def reset_all() -> dict:
    """Permanently delete the ENTIRE epiphany-finance store (all users, the registry, every report
    and session, and any legacy top-level state.db) by removing ~/.epiphany-finance/ wholesale.
    Returns a summary (user list captured before delete)."""
    summary = {"scope": "all", "path": ROOT, "existed": os.path.isdir(ROOT), "users": list_users()}
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    return summary
