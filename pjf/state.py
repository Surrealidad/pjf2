"""JSON state files. jobs.json layout:

{
  "last_run": "2026-09-23T10:00:00Z",
  "boards": {"greenhouse:riotgames": "<time of the last successful fetch>", ...},
  "jobs":   {"<key>": {"title": ..., "first_seen": ..., "last_seen": ..., ...}, ...}
}

A job is active when it was seen in the latest successful fetch of its board.
A board that fails keeps its jobs active, so a bad run never empties the page.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from .config import PRUNE_DAYS

STORED = ("title", "company", "url", "source", "board", "location", "posted", "family", "verdict")


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def now_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def merge(db: dict, jobs, board_status: dict, run_ts: str) -> int:
    """Record this run's kept jobs. Returns the number of new jobs."""
    db.setdefault("jobs", {})
    db.setdefault("boards", {})
    for board, ok in board_status.items():
        if ok:
            db["boards"][board] = run_ts
    new = 0
    for job in jobs:
        rec = db["jobs"].get(job.key)
        if rec is None:
            rec = {"first_seen": run_ts}
            new += 1
        rec.update({k: getattr(job, k) for k in STORED})
        rec["last_seen"] = run_ts
        db["jobs"][job.key] = rec
    db["last_run"] = run_ts

    cutoff = (dt.datetime.strptime(run_ts, "%Y-%m-%dT%H:%M:%SZ")
              - dt.timedelta(days=PRUNE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["jobs"] = {k: r for k, r in db["jobs"].items() if r.get("last_seen", "") >= cutoff}
    return new


def active_jobs(db: dict) -> list[dict]:
    boards = db.get("boards", {})
    out = []
    for key, rec in db.get("jobs", {}).items():
        if rec.get("last_seen", "") >= boards.get(rec.get("board"), ""):
            out.append(dict(rec, key=key))
    return out
