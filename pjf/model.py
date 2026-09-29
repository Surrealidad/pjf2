"""The Job record and small text helpers."""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import re
from dataclasses import dataclass
from typing import Optional


def norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


_TAG = re.compile(r"<[^>]+>")


def strip_html(text, limit=6000) -> str:
    # Greenhouse entity-encodes its markup: unescape, strip tags, unescape again.
    text = html.unescape(text or "")
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()[:limit]


def parse_date(value) -> Optional[dt.date]:
    """ISO dates, RFC 822 dates (RSS) and epoch milliseconds. None if unknown."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.utcfromtimestamp(value / 1000).date()
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return email.utils.parsedate_to_datetime(text).date()
    except (TypeError, ValueError, IndexError):
        return None


@dataclass
class Job:
    source: str                     # "greenhouse", "lever", or the feed name
    board: str                      # fetch unit, e.g. "greenhouse:riotgames" or "feed:GameJobs.co"
    title: str
    company: str
    url: str
    posted: str = ""                # ISO date if known
    location: str = ""              # as stated by the source
    remote: Optional[bool] = None   # True if the source flags it as remote
    description: str = ""           # plain text, used for filtering only, never stored
    family: str = ""                # set by the filter
    verdict: str = ""               # set by the filter: ok | check

    @property
    def key(self) -> str:
        base = f"{norm(self.company)}|{norm(self.title)}"
        return hashlib.sha1(base.encode()).hexdigest()[:16]
