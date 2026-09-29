"""PJF v2 source probe. Python 3.9+, standard library only.

Usage:  python probe_sources.py
Output: probe_results.md (table) in the current folder.

For each site it checks, politely (1 request/second):
  - robots.txt: does it block generic crawlers from the jobs path?
  - feeds: RSS/Atom <link> tags on the page, plus common feed paths
  - structured data: schema.org JobPosting (JSON-LD) on the jobs page
  - bot wall: Cloudflare / challenge pages, 403s
It does NOT scrape job listings.
"""
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (PJF source probe; personal job search tool)"
DELAY = 1.0

# name, jobs page URL, note. Fix or fill the "TODO" ones.
SITES = [
    ("Hitmarker", "https://hitmarker.net/jobs", "ToS forbids scraping, quick link only"),
    ("Work With Indies", "https://www.workwithindies.com/", "had RSS in v1"),
    ("Remote Game Jobs", "https://remotegamejobs.com/", ""),
    ("Games Jobs Direct", "https://www.gamesjobsdirect.com/", ""),
    ("Games-Career", "https://www.games-career.com/", "had RSS in v1"),
    ("GameJobs.co", "https://gamejobs.co/", ""),
    ("Grackle HQ", "https://gracklehq.com/jobs", "aggregator of career pages"),
    ("GamesIndustry.biz Jobs", "https://jobs.gamesindustry.biz/", ""),
    ("ArtStation Jobs", "https://www.artstation.com/jobs", ""),
    ("PocketGamer.biz Jobs", "https://jobs.pocketgamer.biz/", ""),
    ("GameDev.net Jobs", "https://gamedev.net/jobs/", ""),
    ("GameDevJobs.io", "https://gamedevjobs.io/", ""),
    ("Amir Satvat (ASGC)", "https://amirsatvat.com/", "company list source"),
    ("r/gamedevclassifieds", "https://www.reddit.com/r/gameDevClassifieds/new/.rss", "Reddit RSS"),
    ("r/gameDevJobs", "https://www.reddit.com/r/gameDevJobs/new/.rss", "Reddit RSS"),
    # Suggested extras
    ("XP Game Jobs", "https://xpgamejobs.com/", "suggested"),
    ("Outscal Jobs", "https://outscal.com/jobs", "suggested, feeds Amir Satvat's lists"),
    ("GameJobs.eu", "https://gamejobs.eu/", "suggested, Europe"),
    # TODO: need URLs from Pablo
    # ("8Bit", "https://...", ""),
    # ("Dev.play", "https://...", ""),
    # ("AWE Games", "https://...", ""),
    # ("Level Up Coding", "https://...", ""),
]

FEED_PATHS = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/jobs/feed", "/jobs.rss",
              "/jobs/rss", "/jobs.json", "/api/jobs"]


def get(url, timeout=15):
    """Return (status, headers_dict, text). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    time.sleep(DELAY)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400_000).decode("utf-8", "replace")
            return r.status, {k.lower(): v for k, v in r.headers.items()}, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read(50_000).decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body
    except Exception as e:
        return 0, {}, f"ERROR {type(e).__name__}: {e}"


def is_bot_wall(status, headers, body):
    if status == 0:
        return "unreachable"
    b = body[:5000].lower()
    if "just a moment" in b or "cf-chl" in b or "challenge-platform" in b:
        return "Cloudflare challenge"
    if status in (403, 429, 503) and ("cloudflare" in headers.get("server", "").lower()):
        return f"Cloudflare {status}"
    if status == 403:
        return "403 forbidden"
    return ""


def looks_like_feed(headers, body):
    ct = headers.get("content-type", "").lower()
    head = body[:500].lstrip().lower()
    if "xml" in ct or head.startswith("<?xml") or "<rss" in head or "<feed" in head:
        return "<item" in body or "<entry" in body
    if "json" in ct or head.startswith("[") or head.startswith("{"):
        return len(body) > 200
    return False


def probe(name, url, note):
    row = {"site": name, "url": url, "note": note}
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"

    # robots.txt
    status, _, robots = get(base + "/robots.txt")
    rp = urllib.robotparser.RobotFileParser()
    if status == 200:
        rp.parse(robots.splitlines())
        row["robots"] = "allows" if rp.can_fetch("*", url) else "BLOCKS jobs path"
    else:
        row["robots"] = f"none ({status})"

    # main page
    status, headers, body = get(url)
    row["status"] = str(status)
    row["bot_wall"] = is_bot_wall(status, headers, body) or "no"

    if looks_like_feed(headers, body):
        row["feeds"] = "page itself is a feed"
    else:
        links = re.findall(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', body, re.I)
        hrefs = [re.search(r'href=["\']([^"\']+)', l) for l in links]
        found = [urljoin(url, h.group(1)) for h in hrefs if h]
        if not found and row["bot_wall"] == "no":  # skips unreachable and walled sites
            for path in FEED_PATHS:
                s, h, b = get(base + path)
                if s == 200 and looks_like_feed(h, b):
                    found.append(base + path)
                    break
        row["feeds"] = ", ".join(found[:3]) or "none found"

    row["jsonld_jobposting"] = "yes" if re.search(r'"@type"\s*:\s*"JobPosting"', body) else "no"
    row["remote_mentioned"] = "yes" if re.search(r"\bremote\b", body, re.I) else "no"
    return row


def main():
    rows = []
    for name, url, note in SITES:
        print(f"Probing {name} ...", flush=True)
        rows.append(probe(name, url, note))

    cols = ["site", "status", "robots", "bot_wall", "feeds", "jsonld_jobposting",
            "remote_mentioned", "note", "url"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |")
    with open("probe_results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\nDone. Paste the contents of probe_results.md into the chat.")


if __name__ == "__main__":
    main()
