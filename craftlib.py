"""craftlib: storage, path safety, backup, and the math brains.

Plain Python stdlib only. Domestic, local-first, no network calls.

Built by Asdale Dynamics, LLC for the Andy's Craft Room tool family:
this module is the shared brain for works-in-progress, stash materials,
gift deadlines, and finish-first planning.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import datetime
import tempfile
from pathlib import Path
from typing import Any

MAX_BACKUPS = 5
STORE_VERSION = 1
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class CraftError(Exception):
    """Raised for expected, user-facing problems (bad input, missing doc)."""


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _safe_child(base: Path, candidate: Path) -> bool:
    """True if candidate stays strictly inside base after normalization."""
    base_r = os.path.realpath(base)
    cand_r = os.path.realpath(candidate)
    return cand_r == base_r or cand_r.startswith(base_r + os.sep)


def safe_path(base_dir: str | os.PathLike[str], *parts: str) -> Path:
    """Join parts and guarantee the result stays inside base_dir.

    Rejects absolute overrides, traversal like ``../../etc/passwd``, and
    sneaky absolute-path prefixes. Symlink-realpath-aware.
    """
    base = Path(base_dir).resolve()
    try:
        candidate = base.joinpath(*parts)
    except (TypeError, ValueError) as exc:  # non-str parts, etc.
        raise CraftError("unsafe path") from exc
    for part in parts:
        if isinstance(part, os.PathLike) or not isinstance(part, str):
            raise CraftError("unsafe path")
        if part.startswith("/") or part.startswith("\\") or "\x00" in part:
            raise CraftError("unsafe path")
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        base = base.resolve()
    if not _safe_child(base, candidate):
        raise CraftError("unsafe path")
    return candidate


# ---------------------------------------------------------------------------
# Storage: JSON on disk with automatic timestamped backups
# ---------------------------------------------------------------------------

def empty_store() -> dict[str, Any]:
    return {
        "version": STORE_VERSION,
        "wips": [],
        "stash": [],
        "deadlines": [],
    }


def utc_today() -> datetime.date:
    """Single seam for tests monkeypatching 'today' (default: real clock)."""
    return datetime.date.today()


def load_store(path: Path) -> dict[str, Any]:
    f = Path(path)
    if not f.exists() or f.stat().st_size == 0:
        return empty_store()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CraftError(f"data file is not valid JSON: {f}") from exc
    if not isinstance(data, dict):
        raise CraftError("data file must contain a JSON object")
    out = empty_store()
    out["version"] = data.get("version", STORE_VERSION)
    for key in ("wips", "stash", "deadlines"):
        val = data.get(key, [])
        if not isinstance(val, list):
            raise CraftError(f"data has wrong shape for {key}")
        out[key] = val
    return out


def backup_store(path: Path, backup_dir: Path | None = None) -> Path | None:
    """Copy the current file into backup_dir as a timestamped .json.

    Keeps at most MAX_BACKUPS newest files. Returns the backup path, or
    None if there was nothing to back up yet.
    """
    f = Path(path)
    if not f.exists() or f.stat().st_size == 0:
        return None
    bdir = backup_dir if backup_dir is not None else f.parent / "backups"
    bdir = Path(bdir)
    if not _safe_child(Path(path).resolve().parent, bdir):
        raise CraftError("unsafe path")
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = safe_path(bdir, f"craft-store-{stamp}.json")
    shutil.copy2(f, dest)
    backups = sorted(bdir.glob("craft-store-*.json"))
    for old in backups[:-MAX_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def save_store(path: Path, data: dict[str, Any]) -> None:
    f = Path(path)
    backup_store(f)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=str(f.parent), suffix=".tmp"
    )
    try:
        json.dump(data, tmp, indent=2, sort_keys=False)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, f)


# ---------------------------------------------------------------------------
# Progress math
# ---------------------------------------------------------------------------

def _int_in_range(value: Any, minimum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CraftError(f"{name} must be an integer")
    if value < minimum:
        raise CraftError(f"{name} must be >= {minimum}")
    return value


def progress_pct(done: Any, total: Any) -> int:
    """Percent complete, 0..100, clamped. done == total -> 100 even at 0."""
    total_i = _int_in_range(total, 0, "total")
    done_i = _int_in_range(done, 0, "done_units")
    if done_i > total_i:
        raise CraftError("done_units cannot exceed total_units")
    return 100 if total_i == 0 else min(100, round(done_i * 100 / total_i))


# ---------------------------------------------------------------------------
# Deadline math
# ---------------------------------------------------------------------------

def days_until(date_str: Any, today: datetime.date | None = None) -> int:
    """Whole days from today until date_str (ISO YYYY-MM-DD). Negative = overdue."""
    if today is None:
        today = utc_today()
    if isinstance(date_str, datetime.date):
        target = date_str
    else:
        if not isinstance(date_str, str):
            raise CraftError("date must be an ISO YYYY-MM-DD string")
        try:
            target = datetime.date.fromisoformat(date_str)
        except ValueError as exc:
            raise CraftError("date must be an ISO YYYY-MM-DD string") from exc
    return (target - today).days


def lead_time_nudge(days_left: int, lead_time_days: int) -> str:
    """Human nudge based on how close we are to the deadline.

    lead_time_days is how many days the maker asked for as working time.
    """
    if lead_time_days <= 0:
        lead_time_days = 1
    if days_left < 0:
        return "overdue"
    if days_left == 0:
        return "due today"
    if days_left <= max(1, lead_time_days // 4):
        return "start now - critically close"
    if days_left <= lead_time_days // 2:
        return "nudge: past half of lead time"
    if days_left <= lead_time_days:
        return "on track - reserve some time"
    return "plenty of time"


# ---------------------------------------------------------------------------
# Finish-first ranking
# ---------------------------------------------------------------------------

def remaining_need(entry: dict[str, Any], stash: list[dict[str, Any]]) -> float:
    """Units of the first needed material we still lack. 0 if fully covered."""
    mats = entry.get("needs", [])
    if not mats:
        return 0.0
    first = mats[0] or {}
    per_unit = first.get("per_unit", 0)
    name = first.get("name", "")
    units_left = max(0, (entry.get("total_units") or 0) - (entry.get("done_units") or 0))
    need = (per_unit or 0) * units_left
    if need <= 0:
        return 0.0
    have = sum(
        (s.get("quantity") or 0)
        for s in stash
        if (s.get("material") or "").lower() == str(name).lower()
    )
    return max(0.0, need - have)


def min_days_left(entry: dict[str, Any],
                  today: datetime.date | None = None) -> int | None:
    """Days until the nearest deadline, or None when no deadline exists."""
    best = None
    for d in entry.get("deadlines", []):
        days = days_until(d.get("event_date"), today)
        if best is None or days < best:
            best = days
    return best


def finish_first_score(entry: dict[str, Any], stash: list[dict[str, Any]],
                       today: datetime.date | None = None) -> float:
    """Higher score = more likely to actually be finished first.

    Mixes percent complete (0..1) with urgency from the nearest deadline
    and a small penalty for materials still missing.
    """
    total = entry.get("total_units") or 0
    done = entry.get("done_units") or 0
    pct = progress_pct(done, total) / 100.0
    days = min_days_left(entry, today)
    if days is None:
        days = 365
    urgency = 1 - min(max(days, -14), 365) / 365.0  # overdue -> max urgency
    blocked = min(remaining_need(entry, stash) / (total or 1), 1.0)
    return round(pct * 0.55 + urgency * 0.30 + (1 - blocked) * 0.15, 4)


def rank_wips(wips: list[dict[str, Any]], stash: list[dict[str, Any]],
              today: datetime.date | None = None) -> list[dict[str, Any]]:
    """WIPs sorted so the top row is the one to pick up next."""
    ranked = []
    for w in wips:
        ranked.append(
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "progress_pct": progress_pct(w.get("done_units", 0), w.get("total_units", 0)),
                "days_to_deadline": min_days_left(w, today),
                "deadline_nudge": _nearest_nudge(w, today),
                "missing_material_qty": remaining_need(w, stash),
                "score": finish_first_score(w, stash, today),
            }
        )
    ranked.sort(key=lambda r: -r["score"])
    return ranked


def _nearest_nudge(entry: dict[str, Any], today: datetime.date | None) -> str | None:
    best = None
    for d in entry.get("deadlines", []):
        days = days_until(d.get("event_date"), today)
        lead = d.get("lead_time_days", 14)
        nudge = lead_time_nudge(days, lead)
        if best is None or days < best[0]:
            best = (days, nudge)
    return best[1] if best else None
