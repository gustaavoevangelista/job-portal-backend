"""
JSON-API job ingestion: Remotive + Working Nomads.

Both expose free, public, no-auth-required JSON endpoints - same
"don't scrape what's already offered structured" principle as the
WWR RSS feeds in ingest_rss.py. This module follows the identical
pattern: fetch -> normalize into our Job shape -> categorize -> dedupe
-> store. categorize_job() and extract_headquarters() are reused
as-is from relevance.py; no source-specific classification logic.

--- Remotive-specific notes ---
Remotive's API has documented usage terms that matter even for
personal/non-commercial use:
  - Don't hit it more than ~4x/day (they explicitly ask for this;
    >2x/minute gets you blocked). This script is meant to be run
    manually or on a daily cron, not polled frequently.
  - Attribution: if you ever show these jobs anywhere beyond your own
    eyes, link back to the original Remotive job URL and credit
    Remotive as the source. We store source="remotive" and keep the
    original url intact specifically so this is always possible.
  - Their domain has moved before (remotive.io -> remotive.com).
    REMOTIVE_API_URL below is the current documented endpoint as of
    this writing - if requests start failing, check
    https://github.com/remotive-com/remote-jobs-api for the latest.

--- Working Nomads-specific notes ---
Public JSON endpoint, no auth, no documented rate-limit guidance found -
being conservative anyway (this is a personal tool, not worth being a
bad citizen over). Field names confirmed: url, title, description,
company_name, category_name, tags, location, pub_date.
"""

import hashlib
from datetime import datetime, timezone

import httpx

from models import Job, SessionLocal, init_db
from relevance import categorize_job, extract_headquarters
from eu_filter import classify_eu_compatibility, is_switzerland
from resume_match import compute_resume_match
from ingest_common import get_existing_dedup_hashes

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs?category=software-dev"
WORKING_NOMADS_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"

# --- RemoteOK-specific notes ---
# Confirmed live field names: position (not "title"), company, location,
# description, url, apply_url, tags, date, epoch.
#
# IMPORTANT: the first element of the returned array is metadata, not a
# job - it's a dict like {"legal": "..."} with no "position" field.
# Must be skipped or code will crash/misparse trying to read it as a job.
#
# Attribution requirement (confirmed from the live API's own "legal"
# field): must link back DIRECTLY to the job's URL on RemoteOK (no
# redirects, no nofollow) and credit RemoteOK as the source if this
# data is ever shown beyond personal use. The url/apply_url fields are
# stored specifically so this is always honorable later.
#
# RemoteOK is a general board, not frontend-specific - expect heavy
# noise (legal, video editing, property maintenance, etc). This is
# fine; categorize_job() already separates signal from noise without
# needing a frontend-specific source.
REMOTEOK_API_URL = "https://remoteok.com/api"

# A descriptive User-Agent is good practice for any API consumption -
# identifies the request honestly rather than masquerading as a browser.
HEADERS = {"User-Agent": "personal-job-portal/1.0 (single-user, non-commercial)"}


def make_dedup_hash(source: str, title: str, company: str, url: str) -> str:
    raw = f"{source}|{company}|{title}|{url}".lower().strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_iso_date(date_str: str):
    """Best-effort ISO date parsing - both sources use slightly different formats."""
    if not date_str:
        return None
    try:
        # Handles both 'YYYY-MM-DDTHH:MM:SS' and with timezone offsets
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def fetch_remotive_jobs() -> list[dict]:
    """
    Fetch and normalize jobs from Remotive's public API.
    Returns a list of dicts matching our Job shape (un-saved).
    """
    response = httpx.get(REMOTIVE_API_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.json()

    jobs = []
    for entry in payload.get("jobs", []):
        title = entry.get("title", "").strip()
        company = entry.get("company_name", "").strip()
        url = entry.get("url", "").strip()
        description = entry.get("description", "") or ""
        # Remotive gives us this directly - no regex needed, unlike WWR
        location_raw = entry.get("candidate_required_location", "") or ""
        posted_at = _parse_iso_date(entry.get("publication_date", ""))

        category, score = categorize_job(title, description)
        eu_compat = classify_eu_compatibility(location_raw)
        switzerland_flag = is_switzerland(location_raw)
        match_result = compute_resume_match(title, description)
        # Remotive doesn't embed "Headquarters:" in description like WWR does,
        # so headquarters_raw stays empty here - candidate_required_location
        # carries the equivalent information for this source, stored separately.

        jobs.append({
            "dedup_hash": make_dedup_hash("remotive", title, company, url),
            "source": "remotive",
            "title": title,
            "company": company,
            "headquarters_raw": location_raw,  # repurposed: this source's location signal
            "url": url,
            "description": description,
            "posted_at": posted_at,
            "category": category,
            "relevance_score": score,
            "eu_compatible": eu_compat,
            "is_switzerland": switzerland_flag,
            "resume_match_pct": match_result["match_pct"],
        })

    return jobs


def fetch_working_nomads_jobs() -> list[dict]:
    """
    Fetch and normalize jobs from Working Nomads' public API.
    Returns a list of dicts matching our Job shape (un-saved).
    """
    response = httpx.get(WORKING_NOMADS_API_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    entries = response.json()

    jobs = []
    for entry in entries:
        title = entry.get("title", "").strip()
        company = entry.get("company_name", "").strip()
        url = entry.get("url", "").strip()
        description = entry.get("description", "") or ""
        location_raw = entry.get("location", "") or ""
        posted_at = _parse_iso_date(entry.get("pub_date", ""))

        category, score = categorize_job(title, description)
        eu_compat = classify_eu_compatibility(location_raw)
        switzerland_flag = is_switzerland(location_raw)
        match_result = compute_resume_match(title, description)

        jobs.append({
            "dedup_hash": make_dedup_hash("working_nomads", title, company, url),
            "source": "working_nomads",
            "title": title,
            "company": company,
            "headquarters_raw": location_raw,
            "url": url,
            "description": description,
            "posted_at": posted_at,
            "category": category,
            "relevance_score": score,
            "eu_compatible": eu_compat,
            "is_switzerland": switzerland_flag,
            "resume_match_pct": match_result["match_pct"],
        })

    return jobs


def fetch_remoteok_jobs() -> list[dict]:
    """
    Fetch and normalize jobs from RemoteOK's public API.
    Returns a list of dicts matching our Job shape (un-saved).

    Note: RemoteOK is a general-purpose remote job board, not
    frontend-specific - most of what comes back will be irrelevant
    (legal, video editing, sales, etc). categorize_job() filters this
    down same as every other source; no special handling needed here.
    """
    response = httpx.get(REMOTEOK_API_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    entries = response.json()

    jobs = []
    for entry in entries:
        # First element is API metadata (legal notice), not a job -
        # confirmed live: it has no "position" field. Skip anything
        # missing the fields a real job entry always has.
        if "position" not in entry or "url" not in entry:
            continue

        title = (entry.get("position") or "").strip()
        company = (entry.get("company") or "").strip()
        url = (entry.get("url") or entry.get("apply_url") or "").strip()
        description = entry.get("description", "") or ""
        location_raw = (entry.get("location") or "").strip()

        posted_at = None
        if entry.get("date"):
            posted_at = _parse_iso_date(entry["date"])

        category, score = categorize_job(title, description)
        eu_compat = classify_eu_compatibility(location_raw)
        switzerland_flag = is_switzerland(location_raw)
        match_result = compute_resume_match(title, description)

        jobs.append({
            "dedup_hash": make_dedup_hash("remoteok", title, company, url),
            "source": "remoteok",
            "title": title,
            "company": company,
            "headquarters_raw": location_raw,
            "url": url,
            "description": description,
            "posted_at": posted_at,
            "category": category,
            "relevance_score": score,
            "eu_compatible": eu_compat,
            "is_switzerland": switzerland_flag,
            "resume_match_pct": match_result["match_pct"],
        })

    return jobs


def store_jobs(job_dicts: list[dict]) -> dict:
    """Save a list of normalized job dicts, skipping ones already in the DB."""
    session = SessionLocal()
    counts = {"new": 0, "skipped": 0, "web_frontend": 0, "mobile_dev": 0, "full_stack_react": 0}

    try:
        dedup_hashes = [job_data["dedup_hash"] for job_data in job_dicts]
        existing_hashes = get_existing_dedup_hashes(session, dedup_hashes)

        for job_data in job_dicts:
            if job_data["dedup_hash"] in existing_hashes:
                counts["skipped"] += 1
                continue

            job = Job(**job_data)
            session.add(job)
            existing_hashes.add(job_data["dedup_hash"])
            counts["new"] += 1
            if job_data["category"] in ("web_frontend", "mobile_dev", "full_stack_react"):
                counts[job_data["category"]] += 1

        session.commit()
    finally:
        session.close()

    return counts


def run_json_sources():
    init_db()
    print("Starting JSON API ingestion...\n")

    totals = {"new": 0, "web_frontend": 0, "mobile_dev": 0, "full_stack_react": 0}

    print("Fetching: remotive")
    try:
        remotive_jobs = fetch_remotive_jobs()
        counts = store_jobs(remotive_jobs)
        print(
            f"  -> {counts['new']} new, {counts['skipped']} already in DB "
            f"(web_frontend={counts['web_frontend']}, "
            f"mobile_dev={counts['mobile_dev']}, "
            f"full_stack_react={counts['full_stack_react']})\n"
        )
        for key in totals:
            totals[key] += counts.get(key, 0)
    except httpx.HTTPError as e:
        print(f"  [error] Remotive fetch failed: {e}\n")

    print("Fetching: working_nomads")
    try:
        wn_jobs = fetch_working_nomads_jobs()
        counts = store_jobs(wn_jobs)
        print(
            f"  -> {counts['new']} new, {counts['skipped']} already in DB "
            f"(web_frontend={counts['web_frontend']}, "
            f"mobile_dev={counts['mobile_dev']}, "
            f"full_stack_react={counts['full_stack_react']})\n"
        )
        for key in totals:
            totals[key] += counts.get(key, 0)
    except httpx.HTTPError as e:
        print(f"  [error] Working Nomads fetch failed: {e}\n")

    print("Fetching: remoteok")
    try:
        remoteok_jobs = fetch_remoteok_jobs()
        counts = store_jobs(remoteok_jobs)
        print(
            f"  -> {counts['new']} new, {counts['skipped']} already in DB "
            f"(web_frontend={counts['web_frontend']}, "
            f"mobile_dev={counts['mobile_dev']}, "
            f"full_stack_react={counts['full_stack_react']})\n"
        )
        for key in totals:
            totals[key] += counts.get(key, 0)
    except httpx.HTTPError as e:
        print(f"  [error] RemoteOK fetch failed: {e}\n")

    print(
        f"Done. {totals['new']} new jobs added. "
        f"web_frontend={totals['web_frontend']}, "
        f"mobile_dev={totals['mobile_dev']}, "
        f"full_stack_react={totals['full_stack_react']}"
    )


if __name__ == "__main__":
    run_json_sources()