"""Workday career sites (big publishers), set up by hand in config/sources.json:

  "workday": [{"name": "Epic Games",
               "url": "https://epicgames.wd5.myworkdayjobs.com/en-US/Epic_Games",
               "search": "remote"}]

"url" is the careers page as it shows in the browser. Workday has no documented
API; the career site itself calls POST {host}/wday/cxs/{tenant}/{site}/jobs.
Pages hold 20 jobs at most, so a search keyword keeps the number of requests low.
"""
from __future__ import annotations

import datetime as dt
import re
import time
from urllib.parse import urlparse

from . import net
from .model import Job

PAGE = 20
MAX_PAGES = 10
LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
MULTI = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)


def parse_site(url: str):
    """(host, tenant, site) from a careers URL, or None."""
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x and not LOCALE.match(x)]
    if not p.netloc or not parts:
        return None
    return p.netloc, p.netloc.split(".")[0], parts[0]


def posted_date(text: str, today: dt.date) -> str:
    """'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    t = (text or "").lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*day", t)
    return (today - dt.timedelta(days=int(m.group(1)))).isoformat() if m else ""


def _remote(value: str):
    v = (value or "").lower()
    if "hybrid" in v:
        return None, "hybrid"
    if "remote" in v:
        return True, ""
    if "site" in v or "office" in v:
        return False, ""
    return None, ""


def fetch_site(entry: dict, today: dt.date | None = None):
    """Returns (board_id, ok, jobs)."""
    today = today or dt.date.today()
    parsed = parse_site(entry.get("url", ""))
    board = f"workday:{entry.get('name', '?')}"
    if not parsed:
        return board, False, []
    host, tenant, site = parsed
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    search = entry.get("search", "remote")
    jobs, total = [], None
    for page in range(MAX_PAGES):
        if page:
            time.sleep(0.5)   # Workday throttles fast pagination
        _, payload = net.post_json(api, {"appliedFacets": {}, "limit": PAGE,
                                         "offset": page * PAGE, "searchText": search}, timeout=30)
        if payload is None:
            return board, bool(jobs), jobs
        if total is None:
            total = payload.get("total") or 0   # only the first page carries the total
        batch = payload.get("jobPostings") or []
        for j in batch:
            loc = j.get("locationsText") or ""
            if MULTI.match(loc):
                loc = ""   # "3 Locations" says nothing
            remote, extra = _remote(j.get("remoteType", ""))
            if extra:
                loc = f"{loc} / {extra}" if loc else extra
            note = f"Found by a Workday search for '{search}'." if "remote" in search.lower() else ""
            jobs.append(Job("workday", board, j.get("title", ""), entry.get("name", ""),
                            f"https://{host}/en-US/{site}{j.get('externalPath', '')}",
                            posted_date(j.get("postedOn", ""), today), loc, remote, note))
        if not batch or (page + 1) * PAGE >= total:
            break
    return board, True, jobs


def collect(sites: list[dict], log=print):
    """Returns (jobs, board_status)."""
    jobs, status = [], {}
    for entry in sites:
        board, ok, found = fetch_site(entry)
        status[board] = ok
        jobs.extend(found)
        if not ok:
            log(f"  workday failed: {entry.get('name')}")
    log(f"[workday] {sum(status.values())}/{len(status)} sites OK, {len(jobs)} postings")
    return jobs, status
