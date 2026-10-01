"""Plain-code filters: role family, seniority, age, remote, location, duplicates."""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter

from . import location as loc
from .config import MAX_AGE_DAYS
from .model import Job, parse_date

# First match wins, so the more specific families come first.
FAMILIES = [
    ("localization", re.compile(
        r"locali[sz]|translat|linguist|\blqa\b|language (?:quality|lead|manager|specialist)", re.I)),
    ("audio", re.compile(
        r"\b(audio|sound|composer|music|voice ?over|voice (?:director|producer|actor|casting)|"
        r"dialogue|\bvo\b)", re.I)),
    ("data", re.compile(
        r"\b(data|analytics?|analyst|business intelligence|bi|insights?|statistic\w*|"
        r"machine learning|user research(?:er)?)\b", re.I)),
    ("production", re.compile(
        r"\b(producer|production|project manager|program(?:me)? manager|development manager|"
        r"delivery manager|scrum master|release manager|product owner)\b", re.I)),
    ("operations", re.compile(
        r"\b(operations|live ?ops|studio manager|business manager|vendor manager|"
        r"outsourc\w*)\b", re.I)),
]

SENIORITY = re.compile(
    r"\b(intern(ship)?|junior|jr\.?|graduate|grad|trainee|apprentice(ship)?|entry[- ]level|"
    r"working student|werkstudent|praktikum|placement|becario|pr[aá]cticas)\b", re.I)

# Freelance and linguist work (translators, transcribers, testers, talent pools):
# not the kind of role PJF looks for. "Translation Manager" is kept.
NOT_A_ROLE = re.compile(
    r"\b(freelance|freelancers?|translators?|transcreat\w*|transcri(?:ption|bers?)|"
    r"locali[sz]ers|linguists?|testers?|lqa testing|evaluat(?:ion|ors?)|talent pool|"
    r"general application)\b", re.I)

REMOTE_WORD = re.compile(
    r"\b(remote|remotely|anywhere|worldwide|work from home|wfh|home[- ]based|distributed|"
    r"telecommut\w*|teletrabajo|remoto)\b", re.I)

REASONS = ["role", "seniority", "old", "onsite", "not remote", "location", "duplicate"]


def family(title: str) -> str:
    for name, rx in FAMILIES:
        if rx.search(title or ""):
            return name
    return ""


def worth_a_look(title: str) -> bool:
    """Cheap title-only check, used before spending a request on a job page."""
    return bool(family(title)) and not SENIORITY.search(title) and not NOT_A_ROLE.search(title)


def classify(job: Job, today: dt.date) -> str:
    """Return a drop reason, or "" to keep. Sets job.family and job.verdict."""
    job.family = family(job.title)
    if not job.family:
        return "role"
    if SENIORITY.search(job.title):
        return "seniority"
    if NOT_A_ROLE.search(job.title):
        return "role"
    posted = parse_date(job.posted)
    if posted and (today - posted).days > MAX_AGE_DAYS:
        return "old"

    place_text = job.location or ""
    strong = (job.remote is True or bool(REMOTE_WORD.search(place_text))
              or bool(REMOTE_WORD.search(job.title)))
    if job.remote is False and not strong:
        return "onsite"
    # An explicit hybrid/on-site location wins over a source's remote flag
    # (some boards flag hybrid jobs as remote), unless the location also says remote.
    if loc.ONSITE.search(place_text) and not REMOTE_WORD.search(place_text):
        return "onsite"

    place = loc.classify_place(place_text)
    if place == "blocked":
        return "location"

    if not strong:
        if place_text.strip():
            if not loc.is_wide(place_text):   # a city or country with no remote signal
                return "not remote"
        elif not REMOTE_WORD.search(job.description or ""):
            return "not remote"

    body = loc.body_verdict(job.description)
    if body == "blocked":
        return "location"

    job.verdict = "ok" if strong and (place == "ok" or body == "ok") else "check"
    return ""


def apply(jobs: list[Job], today: dt.date | None = None, log=print):
    """Filter and de-duplicate. Earlier sources win duplicates (ATS before feeds)."""
    today = today or dt.date.today()
    kept, seen, dropped = [], set(), Counter()
    for job in jobs:
        reason = classify(job, today)
        if not reason and job.key in seen:
            reason = "duplicate"
        if reason:
            dropped[reason] += 1
            continue
        seen.add(job.key)
        kept.append(job)
    detail = ", ".join(f"{r} {dropped[r]}" for r in REASONS if dropped[r])
    log(f"[filter] {len(jobs)} postings -> kept {len(kept)} (dropped: {detail or 'none'})")
    return kept, dict(dropped)
