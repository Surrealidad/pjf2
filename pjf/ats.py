"""Company job boards through their public ATS APIs.

Each company in config/companies.txt is probed once against the ATS patterns
below (a few slug guesses each). Hits and misses are cached in
state/ats_registry.json, so a company costs one probe, ever. Known boards are
fetched on every run. The registry is plain JSON: fix a wrong slug by hand.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from . import net
from .config import WORKERS
from .model import Job, norm, parse_date, strip_html

# Order = probe order, most common in games first.
BOARDS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
    "teamtailor": "https://{slug}.teamtailor.com/jobs.rss",
    "personio": "https://{slug}.jobs.personio.de/xml",
    "lever_eu": "https://api.eu.lever.co/v0/postings/{slug}?mode=json",
}
# Systems probed before teamtailor/personio/lever_eu were added. Misses recorded
# without a "tried" list were probed with these, so they get re-probed with the rest.
FIRST_ATS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee")
XML_ITEM = {"teamtailor": "item", "personio": "position"}   # XML feeds, not JSON
PROBE_TIMEOUT = 8
CHECK_VERSION = 2   # bump when name_matches changes: saved boards get re-checked
FETCH_TIMEOUT = 25

GENERIC_SUFFIX = re.compile(
    r"\b(studios?|games?|entertainment|interactive|group|holdings?|"
    r"technologies|technology|software|digital|media|labs?|inc|llc|ltd|"
    r"gmbh|bv|ab|oy|sa|srl|spa|s\.?l\.?)\b", re.I)
# A first word this generic is not a safe slug on its own ("the", "game", ...).
GENERIC_FIRST = {"the", "game", "games", "studio", "studios", "digital", "interactive",
                 "entertainment", "media", "group", "team", "play", "mobile", "labs",
                 "software", "red", "blue", "black", "white", "big", "little", "new"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def slug_variants(name: str) -> list[str]:
    """Ordered slug guesses for a company name, most likely first."""
    name = (name or "").strip()
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", name).split()
    if not words:
        return []
    stripped = GENERIC_SUFFIX.sub("", name).strip()
    candidates = [_slug(name), _slug(stripped), "-".join(w.lower() for w in words)]
    if words[0].lower() not in GENERIC_FIRST:
        candidates.append(words[0].lower())
    out = []
    for cand in candidates:
        cand = cand.strip("-")
        if len(cand) >= 3 and cand not in out:
            out.append(cand)
    return out[:4]


def load_companies(path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


# --- parsers: payload -> list[Job] -----------------------------------------

def _greenhouse(company, slug, payload):
    for j in payload.get("jobs", []):
        yield Job("greenhouse", f"greenhouse:{slug}", j.get("title", ""), company,
                  j.get("absolute_url", ""), str(j.get("updated_at", ""))[:10],
                  (j.get("location") or {}).get("name", ""), None,
                  strip_html(j.get("content", "")))


def _lever(company, slug, payload):
    for j in payload if isinstance(payload, list) else []:
        cats = j.get("categories") or {}
        workplace = (j.get("workplaceType") or "").lower()
        loc = " / ".join(filter(None, [cats.get("location"), workplace]))
        remote = True if workplace == "remote" else (False if workplace in ("onsite", "on-site") else None)
        posted = parse_date(j.get("createdAt"))
        yield Job("lever", f"lever:{slug}", j.get("text", ""), company,
                  j.get("hostedUrl", ""), posted.isoformat() if posted else "",
                  loc, remote,
                  strip_html(j.get("descriptionPlain") or j.get("description", "")))


def _ashby(company, slug, payload):
    for j in payload.get("jobs", []):
        workplace = (j.get("workplaceType") or "").lower()
        loc = " / ".join(filter(None, [j.get("location", ""), workplace]))
        remote = True if (j.get("isRemote") or workplace == "remote") else None
        yield Job("ashby", f"ashby:{slug}", j.get("title", ""), company,
                  j.get("jobUrl") or j.get("applyUrl", ""),
                  str(j.get("publishedAt", ""))[:10], loc, remote,
                  strip_html(j.get("descriptionPlain") or j.get("descriptionHtml", "")))


def _smartrecruiters(company, slug, payload):
    for j in payload.get("content", []):
        loc = j.get("location") or {}
        loc_str = loc.get("fullLocation") or ", ".join(
            p for p in [loc.get("city"), loc.get("region"), loc.get("country")] if p)
        remote = True if loc.get("remote") else None
        ident = (j.get("company") or {}).get("identifier") or slug
        yield Job("smartrecruiters", f"smartrecruiters:{slug}", j.get("name", ""), company,
                  f"https://jobs.smartrecruiters.com/{ident}/{j.get('id', '')}",
                  str(j.get("releasedDate", ""))[:10], loc_str, remote, "")


def _workable(company, slug, payload):
    for j in payload.get("jobs", []):
        loc = j.get("location") or {}
        loc_str = loc.get("location_str") or ", ".join(
            p for p in [j.get("city"), j.get("state"), j.get("country")] if p)
        remote = True if (loc.get("telecommuting") or j.get("telecommuting")) else None
        yield Job("workable", f"workable:{slug}", j.get("title", ""), company,
                  j.get("url") or j.get("shortlink", ""),
                  str(j.get("published_on", ""))[:10], loc_str, remote,
                  strip_html(j.get("full_description") or j.get("description", "")))


def _recruitee(company, slug, payload):
    for j in payload.get("offers", []):
        loc = j.get("location") or j.get("city") or ""
        remote = True if j.get("remote") else None
        yield Job("recruitee", f"recruitee:{slug}", j.get("title", ""), company,
                  j.get("careers_url") or j.get("careers_apply_url", ""),
                  str(j.get("published_at", ""))[:10], loc, remote,
                  strip_html((j.get("description") or "") + " " + (j.get("requirements") or "")))


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def xml_items(body: bytes, item_tag: str) -> list[dict]:
    """Flatten each <item_tag> element: direct children become keys (lowercase,
    no namespace); a child with sub-elements gets all its text joined."""
    root = ET.fromstring(body)
    out = []
    for node in root.iter():
        if _local(node.tag) != item_tag:
            continue
        d = {}
        for child in node:
            name = _local(child.tag)
            text = " ".join(t.strip() for t in child.itertext() if t.strip())
            if text:
                d[name] = f"{d[name]} | {text}" if name in d else text
        out.append(d)
    return out


def _teamtailor(company, slug, payload):
    for j in payload:
        loc = j.get("locations") or j.get("location") or ""
        status = (j.get("remotestatus") or j.get("remote_status") or "").lower()
        remote = None
        if status in ("fully", "remote", "full"):
            remote = True
        elif status == "hybrid":
            loc = f"{loc} / hybrid" if loc else "hybrid"
        elif status in ("none", "onsite", "on-site"):
            remote = False
        posted = parse_date(j.get("pubdate"))
        yield Job("teamtailor", f"teamtailor:{slug}", j.get("title", ""), company,
                  j.get("link", ""), posted.isoformat() if posted else "", loc, remote,
                  strip_html(j.get("description", "")))


def _personio(company, slug, payload):
    for j in payload:
        loc = " / ".join(filter(None, [j.get("office"), j.get("additionaloffices")]))
        yield Job("personio", f"personio:{slug}", j.get("name", ""), company,
                  f"https://{slug}.jobs.personio.de/job/{j.get('id', '')}",
                  str(j.get("createdat", ""))[:10], loc, None,
                  strip_html(j.get("jobdescriptions", "")))


def _lever_eu(company, slug, payload):
    for job in _lever(company, slug, payload):
        job.source, job.board = "lever", f"lever_eu:{slug}"
        yield job


PARSERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby,
           "smartrecruiters": _smartrecruiters, "workable": _workable,
           "recruitee": _recruitee, "teamtailor": _teamtailor,
           "personio": _personio, "lever_eu": _lever_eu}


def load(ats, slug, timeout):
    """Fetch a board. Returns the payload (JSON, or a list of dicts for XML
    feeds) or None when the board does not answer or is not a board."""
    url = BOARDS[ats].format(slug=slug)
    if ats in XML_ITEM:
        status, body = net.get(url, timeout, "application/rss+xml, application/xml, */*;q=0.5")
        if status != 200:
            return None
        try:
            return xml_items(body, XML_ITEM[ats])
        except ET.ParseError:   # an HTML page instead of a feed
            return None
    return net.get_json(url, timeout=timeout)[1]


def _has_jobs(ats, payload) -> bool:
    if payload is None:
        return False
    if isinstance(payload, list):   # lever, lever_eu, teamtailor, personio
        return bool(payload)
    if not isinstance(payload, dict):
        return False
    return bool(payload.get({"recruitee": "offers", "smartrecruiters": "content"}.get(ats, "jobs")))


def name_matches(name: str, payload) -> bool:
    """True if the company name shows up in the board data (descriptions, URLs,
    company fields). Guards against a short slug hitting a different company,
    e.g. "neon" for Neon Giant landing on a bank's board."""
    blob = _slug(json.dumps(payload, ensure_ascii=False)[:3_000_000])
    full = _slug(name)
    core = _slug(GENERIC_SUFFIX.sub("", name))
    # The name minus "Games"/"Studios" is only trusted when long enough not to be
    # an ordinary word ("keen", "vivid"); otherwise the full name must appear.
    return (len(full) >= 4 and full in blob) or (len(core) >= 6 and core in blob)


def fetch_board(entry):
    """Fetch one known board. Returns (entry, board_id, ok, jobs).

    Entries saved before the name check existed are checked once here; a board
    that fails the check is turned back into a miss (ats/slug set to None)."""
    ats, slug = entry["ats"], entry["slug"]
    board = f"{ats}:{slug}"
    payload = load(ats, slug, FETCH_TIMEOUT)
    if payload is None:
        return entry, board, False, []
    if entry.get("verified") != CHECK_VERSION:
        if not name_matches(entry.get("name", ""), payload):
            entry.update(ats=None, slug=None, rejected=board)
            return entry, board, True, []
        entry["verified"] = CHECK_VERSION
    try:
        return entry, board, True, list(PARSERS[ats](entry.get("name", slug), slug, payload))
    except (AttributeError, TypeError, KeyError):  # unexpected payload shape
        return entry, board, False, []


def probe(name, systems=None):
    """Look for a company's board on the given systems (default: all).
    Returns (registry_entry, jobs)."""
    systems = list(systems or BOARDS)
    entry = {"name": name, "ats": None, "slug": None, "tried": systems,
             "checked": dt.date.today().isoformat()}
    for slug in slug_variants(name):
        for ats in systems:
            payload = load(ats, slug, PROBE_TIMEOUT)
            if _has_jobs(ats, payload) and name_matches(name, payload):
                entry.update(ats=ats, slug=slug, verified=CHECK_VERSION)
                try:
                    return entry, list(PARSERS[ats](name, slug, payload))
                except (AttributeError, TypeError, KeyError):
                    return entry, []
    return entry, []


def to_probe(registry: dict, companies: list[str]) -> list[tuple]:
    """(name, systems) pairs still to probe: new companies get every system,
    earlier misses only the systems they were not tried on yet."""
    out = []
    for name in companies:
        entry = registry.get(norm(name))
        if entry is None:
            out.append((name, list(BOARDS)))
        elif not entry.get("ats"):
            tried = set(entry.get("tried") or FIRST_ATS)
            if entry.get("rejected"):
                tried.discard(entry["rejected"].split(":", 1)[0])  # may exist under another slug
            missing = [a for a in BOARDS if a not in tried]
            if missing:
                out.append((name, missing))
    return out


def collect(registry: dict, companies: list[str], probe_limit: int, log=print, manual=()):
    """Fetch known boards, probe up to probe_limit companies.

    manual: boards set by hand in config/sources.json ({"name", "ats", "slug"});
    they override the registry. Mutates registry. Returns (jobs, board_status)
    where board_status maps board id -> True/False (fetched OK or not).
    """
    jobs, status = [], {}
    for m in manual:
        if m.get("ats") in BOARDS and m.get("slug"):
            registry[norm(m["name"])] = {"name": m["name"], "ats": m["ats"], "slug": m["slug"],
                                         "verified": CHECK_VERSION, "manual": True}

    known = [e for e in registry.values() if e.get("ats")]
    if known:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for entry, board, ok, found in pool.map(fetch_board, known):
                status[board] = ok
                jobs.extend(found)
                if entry.get("rejected") == board and not entry.get("ats"):
                    log(f"  dropped board: {entry['name']} -> {board} (name not found in its data)")

    todo = to_probe(registry, companies)[:max(0, probe_limit)]
    discovered = 0
    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for entry, found in pool.map(lambda t: probe(*t), todo):
                old = registry.get(norm(entry["name"])) or {}
                if not entry["ats"]:
                    entry["tried"] = sorted(set(entry["tried"]) | set(old.get("tried") or
                                                                    (FIRST_ATS if old else ())))
                    if old.get("rejected"):
                        entry["rejected"] = old["rejected"]
                registry[norm(entry["name"])] = entry
                if entry["ats"]:
                    discovered += 1
                    status[f"{entry['ats']}:{entry['slug']}"] = True
                    jobs.extend(found)
                    log(f"  found board: {entry['name']} -> {entry['ats']}/{entry['slug']}")

    failed = sum(1 for ok in status.values() if not ok)
    left = len(to_probe(registry, companies))
    log(f"[ats] {len(known)} known boards ({failed} failed), probed {len(todo)} companies, "
        f"{discovered} new boards, {left} companies left to probe, {len(jobs)} postings")
    return jobs, status
