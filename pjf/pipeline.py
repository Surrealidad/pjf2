"""One run: collect -> filter -> merge into state -> rebuild the page."""
from __future__ import annotations

import time

from .model import norm
from . import ats, config, feeds, filters, page, remote_boards, state, workday


def load_sources() -> dict:
    return state.load(config.SOURCES_FILE, {"feeds": [], "quick_links": []})


def run(probe=40, use_ats=True, use_feeds=True, use_remote=True, use_workday=True,
        log=print) -> dict:
    started = time.time()
    run_ts = state.now_ts()
    sources = load_sources()
    jobs, status = [], {}

    companies = ats.load_companies(config.COMPANIES_FILE)
    registry = state.load(config.REGISTRY_FILE, {})

    # Order matters for duplicates: the first source to list a job keeps it.
    if use_ats:
        found, st = ats.collect(registry, companies, probe, log, manual=sources.get("boards", []))
        state.save(config.REGISTRY_FILE, registry)
        jobs += found
        status.update(st)

    if use_workday and sources.get("workday"):
        found, st = workday.collect(sources["workday"], log)
        jobs += found
        status.update(st)

    if use_feeds:
        found, st = feeds.collect(sources.get("feeds", []), log)
        jobs += found
        status.update(st)

    if use_remote and sources.get("remote_boards"):
        known = {norm(c) for c in companies} | {norm(e.get("name", "")) for e in registry.values()}
        found, st = remote_boards.collect(sources["remote_boards"], known, log)
        jobs += found
        status.update(st)

    kept, dropped = filters.apply(jobs, log=log)

    db = state.load(config.JOBS_FILE, {})
    new = state.merge(db, kept, status, run_ts)
    state.save(config.JOBS_FILE, db)

    summary = {
        "run": run_ts,
        "seconds": round(time.time() - started),
        "postings": len(jobs),
        "kept": len(kept),
        "new": new,
        "active": len(state.active_jobs(db)),
        "dropped": dropped,
        "boards_ok": sum(1 for ok in status.values() if ok),
        "boards_failed": sorted(b for b, ok in status.items() if not ok),
    }
    state.save(config.LAST_RUN_FILE, summary)
    page.build(db, sources.get("quick_links", []), summary, config.PAGE_FILE)
    log(f"[done] {summary['active']} active jobs, {new} new. Page: {config.PAGE_FILE}")
    return summary


def rebuild_page():
    db = state.load(config.JOBS_FILE, {})
    summary = state.load(config.LAST_RUN_FILE, {})
    page.build(db, load_sources().get("quick_links", []), summary, config.PAGE_FILE)
    print(f"Page rebuilt: {config.PAGE_FILE}")
