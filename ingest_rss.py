"""
Feed-based job ingestion.

Covers sources that expose a public RSS feed - no scraping, no
bot-detection risk, just parsing structured data they already
intend to share.

Note on WWR's categories: "Front-End Programming" is a loose bucket,
not a strict tag - it includes .NET, QA, SRE, and other roles that
happen to be filed there. Relevance categorization (relevance.py) is
what actually narrows results to genuine frontend/full-stack-React
work; don't rely on the category name alone.
"""

import hashlib
from datetime import datetime, timezone

import feedparser

from models import Job, SessionLocal, init_db
from relevance import categorize_job, extract_headquarters
from eu_filter import classify_eu_compatibility, is_switzerland
from resume_match import compute_resume_match
from ingest_common import get_existing_dedup_hashes

from validators import normalize_text, validate_url  # NOVO

# Each entry: (source_name, feed_url)
RSS_SOURCES = [
    ("weworkremotely_frontend", "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss"),
    ("weworkremotely_fullstack", "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"),
]


def make_dedup_hash(source: str, title: str, company: str, url: str) -> str:
    raw = f"{source}|{company}|{title}|{url}".lower().strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# def parse_entry(source_name: str, entry) -> dict:
#     """Normalize one feedparser entry into our Job shape."""
#     title = entry.get("title", "").strip()

#     # WWR formats titles like "Company Name: Job Title"
#     company = None
#     job_title = title
#     if ":" in title:
#         possible_company, possible_title = title.split(":", 1)
#         if len(possible_company) < 60:
#             company = possible_company.strip()
#             job_title = possible_title.strip()

#     url = entry.get("link", "").strip()
#     description = entry.get("summary", "").strip()

#     posted_at = None
#     if entry.get("published_parsed"):
#         posted_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

#     headquarters_raw = extract_headquarters(description)
#     category, score = categorize_job(job_title, description)
#     eu_compat = classify_eu_compatibility(headquarters_raw)
#     switzerland_flag = is_switzerland(headquarters_raw)
#     match_result = compute_resume_match(job_title, description)

#     return {
#         "dedup_hash": make_dedup_hash(source_name, job_title, company or "", url),
#         "source": source_name,
#         "title": job_title,
#         "company": company,
#         "headquarters_raw": headquarters_raw,
#         "url": url,
#         "description": description,
#         "posted_at": posted_at,
#         "category": category,
#         "relevance_score": score,
#         "eu_compatible": eu_compat,
#         "is_switzerland": switzerland_flag,
#         "resume_match_pct": match_result["match_pct"],
#     }


def parse_entry(source_name: str, entry) -> dict:
    """Normalize one feedparser entry into our Job shape.
    
    CHANGELOG:
    - Adicionada validação de URL (validate_url)
    - Normalização de campos com normalize_text
    - Retorna None para URLs inválidas
    """
    title = normalize_text(entry.get("title", "")) or ""
    
    # WWR formats titles like "Company Name: Job Title"
    company = None
    job_title = title
    if ":" in title:
        possible_company, possible_title = title.split(":", 1)
        if len(possible_company) < 60:
            company = possible_company.strip()
            job_title = possible_title.strip()

    url = entry.get("link", "").strip()
    
    # Validação de URL
    if not validate_url(url):
        return None
    
    description = normalize_text(entry.get("summary", "")) or ""

    posted_at = None
    if entry.get("published_parsed"):
        posted_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

    headquarters_raw = extract_headquarters(description)
    category, score = categorize_job(job_title, description)
    eu_compat = classify_eu_compatibility(headquarters_raw)
    switzerland_flag = is_switzerland(headquarters_raw)
    match_result = compute_resume_match(job_title, description)

    return {
        "dedup_hash": make_dedup_hash(source_name, job_title, company or "", url),
        "source": source_name,
        "title": job_title,
        "company": company,
        "headquarters_raw": headquarters_raw,
        "url": url,
        "description": description,
        "posted_at": posted_at,
        "category": category,
        "relevance_score": score,
        "eu_compatible": eu_compat,
        "is_switzerland": switzerland_flag,
        "resume_match_pct": match_result["match_pct"],
    }



# def ingest_rss_source(source_name: str, feed_url: str) -> dict:
#     """
#     Fetch and store all entries from one RSS feed.
#     Returns a dict of counts: new, skipped, and per-category totals.
#     """
#     feed = feedparser.parse(feed_url)

#     if feed.bozo:
#         print(f"  [warn] feed parse issue for {source_name}: {feed.bozo_exception}")

#     session = SessionLocal()
#     counts = {"new": 0, "skipped": 0, "web_frontend": 0, "mobile_dev": 0, "full_stack_react": 0}

#     try:
#         parsed_jobs = [parse_entry(source_name, entry) for entry in feed.entries]
#         dedup_hashes = [job_data["dedup_hash"] for job_data in parsed_jobs]
#         existing_hashes = get_existing_dedup_hashes(session, dedup_hashes)

#         for job_data in parsed_jobs:
#             if job_data["dedup_hash"] in existing_hashes:
#                 counts["skipped"] += 1
#                 continue

#             job = Job(**job_data)
#             session.add(job)
#             existing_hashes.add(job_data["dedup_hash"])
#             counts["new"] += 1
#             if job_data["category"] in ("web_frontend", "mobile_dev", "full_stack_react"):
#                 counts[job_data["category"]] += 1

#         session.commit()
#     finally:
#         session.close()

#     return counts


def ingest_rss_source(source_name: str, feed_url: str) -> dict:
    """
    Fetch and store all entries from one RSS feed.

    CHANGELOG:
    - Filtra entradas com URL inválida (parse_entry retorna None)
    """
    feed = feedparser.parse(feed_url)

    if feed.bozo:
        print(f"  [warn] feed parse issue for {source_name}: {feed.bozo_exception}")

    session = SessionLocal()
    counts = {"new": 0, "skipped": 0, "web_frontend": 0, "mobile_dev": 0, "full_stack_react": 0}

    try:
        # Parse entries, filter out invalid ones (None)
        parsed_jobs = []
        for entry in feed.entries:
            job_data = parse_entry(source_name, entry)
            if job_data is not None:
                parsed_jobs.append(job_data)
            else:
                counts["skipped"] += 1  # Contabiliza jobs pulados por URL inválida
        
        dedup_hashes = [job_data["dedup_hash"] for job_data in parsed_jobs]
        existing_hashes = get_existing_dedup_hashes(session, dedup_hashes)

        for job_data in parsed_jobs:
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



def rescore_existing_jobs():
    """
    Re-run categorization + headquarters extraction + EU-compatibility
    classification + resume match scoring against jobs already in the
    DB. Useful after tuning relevance.py's, eu_filter.py's, or
    resume_match.py's logic, so you don't have to wipe and re-fetch
    everything.
    """
    session = SessionLocal()
    try:
        jobs = session.query(Job).all()
        updated = 0
        for job in jobs:
            category, score = categorize_job(job.title, job.description)
            hq = extract_headquarters(job.description)
            # Only overwrite headquarters_raw if extract_headquarters found
            # something - some sources (Remotive, Working Nomads) populate
            # this field from their own API data, not from regex extraction,
            # and an empty regex result shouldn't clobber that.
            effective_hq = hq if hq else job.headquarters_raw
            eu_compat = classify_eu_compatibility(effective_hq)
            switzerland_flag = is_switzerland(effective_hq)
            match_result = compute_resume_match(job.title, job.description)
            match_pct = match_result["match_pct"]

            changed = (
                (job.category, job.relevance_score, job.eu_compatible,
                 job.is_switzerland, job.resume_match_pct)
                != (category, score, eu_compat, switzerland_flag, match_pct)
                or (hq and job.headquarters_raw != hq)
            )
            if changed:
                job.category = category
                job.relevance_score = score
                job.resume_match_pct = match_pct
                if hq:
                    job.headquarters_raw = hq
                job.eu_compatible = eu_compat
                job.is_switzerland = switzerland_flag
                updated += 1
        session.commit()
        print(f"Rescored {len(jobs)} jobs, {updated} changed.")
    finally:
        session.close()


def run_all_rss_sources():
    init_db()
    print("Starting RSS ingestion...\n")

    totals = {"new": 0, "web_frontend": 0, "mobile_dev": 0, "full_stack_react": 0}
    for source_name, feed_url in RSS_SOURCES:
        print(f"Fetching: {source_name}")
        counts = ingest_rss_source(source_name, feed_url)
        print(
            f"  -> {counts['new']} new, {counts['skipped']} already in DB "
            f"(web_frontend={counts['web_frontend']}, "
            f"mobile_dev={counts['mobile_dev']}, "
            f"full_stack_react={counts['full_stack_react']})\n"
        )
        for key in totals:
            totals[key] += counts.get(key, 0)

    print(
        f"Done. {totals['new']} new jobs added. "
        f"web_frontend={totals['web_frontend']}, "
        f"mobile_dev={totals['mobile_dev']}, "
        f"full_stack_react={totals['full_stack_react']}"
    )


if __name__ == "__main__":
    run_all_rss_sources()