"""General remote-job boards, kept only when the posting is from a game company.

Everything on these boards is remote, so the hard part is the games filter:
a posting stays if its company is in config/companies.txt (or the ATS registry),
or if the company name or the ad itself clearly points at video games.
Gambling (iGaming, casino, betting) is excluded.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import feeds, net
from .model import Job, norm, parse_date, strip_html

GAME_TEXT = re.compile(
    r"\b(video ?games?|computer games?|mobile games?|console games?|pc games?|"
    r"games? (?:industry|studio|studios|company|developer|development|publisher|publishing)|"
    r"game (?:studio|development|developer|design|designer|producer|engine|economy|titles?)|"
    r"gamedev|gaming (?:industry|company|studio)|esports|e-sports|"
    r"free[- ]to[- ]play|live ?ops|playstation|xbox|nintendo|steam|unreal engine|unity3d|"
    r"our games|aaa (?:games?|titles?)|indie games?)\b", re.I)
GAMBLING = re.compile(r"\b(igaming|casino|gambling|betting|sportsbook|slots?|lottery|poker|bingo)\b", re.I)


def is_game_job(job: Job, known: set) -> bool:
    text = f"{job.title} {job.company} {job.description[:5000]}"
    if GAMBLING.search(text):
        return False
    if norm(job.company) in known:
        return True
    if re.search(r"\b(games?|gaming)\b", job.company or "", re.I):
        return True
    return bool(GAME_TEXT.search(text))


# --- one function per board: returns list[Job] or None when the board failed ---

def _remotive():
    jobs, seen = [], set()
    for query in ("search=game", "search=gaming", "category=data", "category=product",
                  "category=project-management"):
        _, payload = net.get_json(f"https://remotive.com/api/remote-jobs?{query}", timeout=30)
        if payload is None:
            return None
        for j in payload.get("jobs", []):
            if j.get("url") in seen:
                continue
            seen.add(j.get("url"))
            jobs.append(Job("Remotive", "remote:Remotive", j.get("title", ""),
                            j.get("company_name", ""), j.get("url", ""),
                            str(j.get("publication_date", ""))[:10],
                            j.get("candidate_required_location", ""), True,
                            strip_html(j.get("description", ""))))
    return jobs


def _remoteok():
    _, payload = net.get_json("https://remoteok.com/api", timeout=30)
    if not isinstance(payload, list):
        return None
    jobs = []
    for j in payload:
        if not isinstance(j, dict) or "position" not in j:
            continue   # the first element is a legal notice
        posted = parse_date(j.get("date"))
        tags = " ".join(j.get("tags") or [])
        jobs.append(Job("RemoteOK", "remote:RemoteOK", j.get("position", ""), j.get("company", ""),
                        j.get("url", ""), posted.isoformat() if posted else "",
                        j.get("location", ""), True,
                        strip_html(f"{j.get('description', '')} {tags}")))
    return jobs


def _himalayas():
    jobs = []
    for page in range(15):   # the API caps a page at 20
        _, payload = net.get_json(f"https://himalayas.app/jobs/api?offset={page * 20}&limit=20", timeout=30)
        if payload is None:
            return jobs or None
        batch = payload.get("jobs", [])
        for j in batch:
            pub = j.get("pubDate")
            posted = parse_date(pub * 1000 if isinstance(pub, (int, float)) else pub)
            where = ", ".join(j.get("locationRestrictions") or []) or "Worldwide"
            jobs.append(Job("Himalayas", "remote:Himalayas", j.get("title", ""),
                            j.get("companyName", ""),
                            j.get("applicationLink") or j.get("guid", ""),
                            posted.isoformat() if posted else "", where, True,
                            strip_html(j.get("description") or j.get("excerpt", ""))))
        if not batch or (page + 1) * 20 >= payload.get("totalCount", 0):
            break
    return jobs


def _jobicy():
    jobs, seen, answered = [], set(), False
    for geo in ("emea", "europe", "spain"):
        status, payload = net.get_json(f"https://jobicy.com/api/v2/remote-jobs?count=100&geo={geo}", timeout=30)
        if status == 404:
            answered = True   # no jobs for that region right now
            continue
        if payload is None:
            continue
        answered = True
        for j in payload.get("jobs", []):
            if j.get("url") in seen:
                continue
            seen.add(j.get("url"))
            jobs.append(Job("Jobicy", "remote:Jobicy", j.get("jobTitle", ""), j.get("companyName", ""),
                            j.get("url", ""), str(j.get("pubDate", ""))[:10],
                            j.get("jobGeo", ""), True,
                            strip_html(j.get("jobDescription") or j.get("jobExcerpt", ""))))
    return jobs if answered else None


def _wwr():
    status, body = net.get("https://weworkremotely.com/remote-jobs.rss", 30, feeds.ACCEPT)
    if status != 200:
        return None
    try:
        items = feeds.parse_feed(body)
    except ET.ParseError:
        return None
    jobs = []
    for it in items:
        company, _, title = (it.get("title") or "").partition(":")
        if not title:
            company, title = "", company
        posted = parse_date(it.get("pubdate"))
        jobs.append(Job("We Work Remotely", "remote:We Work Remotely", title.strip(), company.strip(),
                        it.get("link", ""), posted.isoformat() if posted else "",
                        it.get("location", ""), True, strip_html(it.get("description", ""))))
    return jobs


def _workingnomads():
    _, payload = net.get_json("https://www.workingnomads.com/api/exposed_jobs/", timeout=30)
    if not isinstance(payload, list):
        return None
    return [Job("Working Nomads", "remote:Working Nomads", j.get("title", ""), j.get("company_name", ""),
                j.get("url", ""), str(j.get("pub_date", ""))[:10], j.get("location", ""), True,
                strip_html(f"{j.get('description', '')} {j.get('tags') or ''}"))
            for j in payload if isinstance(j, dict)]


BOARDS = {
    "Remotive": _remotive,
    "RemoteOK": _remoteok,
    "Himalayas": _himalayas,
    "Jobicy": _jobicy,
    "We Work Remotely": _wwr,
    "Working Nomads": _workingnomads,
}


def collect(enabled: list[str], known_companies: set, log=print):
    """Returns (jobs, board_status). Only game-company postings are returned."""
    jobs, status, read = [], {}, 0
    for name in enabled:
        fn = BOARDS.get(name)
        if fn is None:
            log(f"  unknown remote board in config: {name}")
            continue
        try:
            found = fn()
        except (AttributeError, TypeError, KeyError, ValueError):  # unexpected payload shape
            found = None
        status[f"remote:{name}"] = found is not None
        if found is None:
            log(f"  remote board failed: {name}")
            continue
        read += len(found)
        jobs.extend(j for j in found if is_game_job(j, known_companies))
    ok = sum(status.values())
    log(f"[remote] {ok}/{len(status)} boards OK, {read} postings, {len(jobs)} from game companies")
    return jobs, status
