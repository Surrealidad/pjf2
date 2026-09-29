"""Paths and tunable numbers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
DOCS_DIR = ROOT / "docs"

COMPANIES_FILE = CONFIG_DIR / "companies.txt"   # game companies to look up on ATS boards
SOURCES_FILE = CONFIG_DIR / "sources.json"      # feeds + quick links
REGISTRY_FILE = STATE_DIR / "ats_registry.json" # company -> ATS board (committed)
JOBS_FILE = STATE_DIR / "jobs.json"             # jobs seen (committed)
LAST_RUN_FILE = STATE_DIR / "last_run.json"     # summary of the latest run (committed)
PAGE_FILE = DOCS_DIR / "index.html"             # results page (GitHub Pages serves /docs)
MARKS_FILE = ROOT / "marks.json"                # Pablo's marks, local only (.gitignore)

MAX_AGE_DAYS = 60     # drop postings older than this, when the source gives a date
PRUNE_DAYS = 180      # forget jobs not seen for this long
WORKERS = 8           # parallel requests for ATS boards
