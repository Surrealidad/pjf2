"""RSS and Atom job feeds (config/sources.json -> "feeds")."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import net
from .model import Job, parse_date, strip_html

ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
SPLIT = (" at ", " @ ", " - ", " – ", " | ")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_feed(body: bytes) -> list[dict]:
    """Items of an RSS or Atom document as plain dicts. Raises ET.ParseError."""
    root = ET.fromstring(body)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        d = {}
        for child in node:
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "link":
                href = child.get("href") or text
                if href and ("link" not in d or child.get("rel") in (None, "alternate")):
                    d["link"] = href
            elif name in ("title", "pubdate", "published", "updated", "date",
                          "description", "summary", "content", "encoded"):
                d.setdefault(name, text)
            elif "company" in name or "employer" in name:
                d.setdefault("company", text)
            elif "location" in name or name in ("region", "country"):
                d.setdefault("location", text)
        items.append(d)
    return items


HIRING = re.compile(r"^(?P<company>.+?) is hiring (?:an? )?(?P<title>.+?)"
                    r"(?: to work from (?P<where>.+?))?$", re.I)
REMOTE_SUFFIX = re.compile(r"\s*\(remote job\)\s*$", re.I)


def split_title(raw: str):
    """Return (title, company, where) from a feed title.

    Handles "Company is hiring a Role to work from Anywhere" (Work With Indies),
    "Company is hiring Role (Remote Job)" (Remote Game Jobs), and
    "Role at Company" / "Role - Company" (most others).
    """
    raw = REMOTE_SUFFIX.sub("", (raw or "").strip())
    m = HIRING.match(raw)
    if m:
        return m.group("title").strip(), m.group("company").strip(), (m.group("where") or "").strip()
    for sep in SPLIT:
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip(), ""
    return raw, "", ""


def _item_to_job(feed: dict, item: dict) -> Job:
    title, company, where = split_title(item.get("title", ""))
    if item.get("company"):  # an explicit company field beats a guess from the title
        company = item["company"]
    body = item.get("encoded") or item.get("content") or item.get("description") or item.get("summary", "")
    posted = parse_date(item.get("pubdate") or item.get("published") or item.get("updated") or item.get("date"))
    return Job(
        source=feed["name"],
        board=f"feed:{feed['name']}",
        title=title,
        company=company,
        url=item.get("link", ""),
        posted=posted.isoformat() if posted else "",
        location=item.get("location") or where,
        remote=True if feed.get("remote") else None,
        description=strip_html(body),
    )


def collect(feeds: list[dict], log=print):
    """Returns (jobs, board_status)."""
    jobs, status = [], {}
    for feed in feeds:
        if not feed.get("enabled", True):
            continue
        board = f"feed:{feed['name']}"
        code, body = net.get(feed["url"], accept=ACCEPT)
        if code != 200:
            status[board] = False
            log(f"  feed failed: {feed['name']} (HTTP {code or 'no response'})")
            continue
        try:
            items = parse_feed(body)
        except ET.ParseError:
            status[board] = False
            log(f"  feed failed: {feed['name']} (not valid RSS/Atom)")
            continue
        status[board] = True
        jobs.extend(_item_to_job(feed, it) for it in items if it.get("title"))
    ok = sum(status.values())
    log(f"[feeds] {ok}/{len(status)} feeds OK, {len(jobs)} postings")
    return jobs, status
