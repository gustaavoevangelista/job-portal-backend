"""
FastAPI layer for the personal job portal.

Minimal by design - this is a single-user local tool, not a public
service, so there's deliberately no auth, no rate limiting, no
multi-tenancy. Two real endpoints: list jobs (with filters) and update
a job's status (new/seen/applied/ignored), plus a stats endpoint for
a quick overview.

Run with: uvicorn api:app --reload
Docs auto-generated at: http://localhost:8000/docs
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func

from models import Job, Application, SessionLocal, init_db
from relevance import categorize_job
from eu_filter import classify_eu_compatibility, is_switzerland
from resume_match import compute_resume_match

app = FastAPI(title="Job Portal API", version="1.0")

# CORS open to localhost only - this is a local personal tool, the
# frontend runs on a different port (3000) during development, so the
# browser needs explicit permission to call across ports.
app.add_middleware(
    CORSMiddleware,
    # Both localhost and 127.0.0.1 are allowed - browsers treat these as
    # DIFFERENT origins for CORS purposes even though they resolve to the
    # same machine. Missing one of these causes requests to fail silently
    # with no console error, which is exactly what happened during testing.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# --- Response/request shapes ---

class JobOut(BaseModel):
    id: int
    source: str
    title: str
    company: Optional[str]
    headquarters_raw: Optional[str]
    url: str
    description: Optional[str]
    posted_at: Optional[datetime]
    fetched_at: Optional[datetime]
    category: str
    relevance_score: int
    eu_compatible: str
    is_switzerland: bool
    resume_match_pct: int
    status: str

    class Config:
        from_attributes = True


class StatusUpdate(BaseModel):
    status: str  # new | seen | applied | ignored


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    applied_at: datetime
    stage: str
    stage_updated_at: Optional[datetime]
    salary_noted: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    applied_at: Optional[datetime] = None   # defaults to now if not provided
    salary_noted: Optional[str] = None
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    stage: Optional[str] = None
    salary_noted: Optional[str] = None
    notes: Optional[str] = None


class ManualJobCreate(BaseModel):
    """
    For jobs found by browsing a site manually rather than via an
    ingestion script - Wellfound is the motivating case (their terms
    explicitly prohibit automated access, see eu_filter.py/relevance.py
    comments for the broader pipeline this feeds into). You browse
    normally as a human, then paste in what you saw.
    """
    title: str
    company: Optional[str] = None
    url: str
    description: Optional[str] = None
    location: Optional[str] = None  # whatever you saw on the page, free text
    source_label: Optional[str] = "manual"  # lets you distinguish wellfound vs other manual entries later


VALID_STATUSES = {"new", "seen", "applied", "ignored"}
VALID_STAGES = {
    "applied", "screen", "interview", "final",
    "offer", "rejected", "ghosted",
}
VALID_CATEGORIES = {"web_frontend", "mobile_dev", "full_stack_react", "not_relevant"}
VALID_EU_COMPAT = {"yes", "no", "unclear"}


# --- Endpoints ---

@app.post("/jobs/manual", response_model=JobOut, status_code=201)
def create_manual_job(job_in: ManualJobCreate):
    """
    Add a job you found by browsing manually - for sources like
    Wellfound where automated scraping isn't permitted by their terms.
    Runs through the same categorization + EU-compatibility pipeline as
    every ingested job, so it shows up consistently in /jobs and /stats.
    """
    title = job_in.title.strip()
    company = (job_in.company or "").strip()
    url = job_in.url.strip()
    description = job_in.description or ""
    location = (job_in.location or "").strip()
    source = f"manual_{job_in.source_label}" if job_in.source_label else "manual"

    if not title or not url:
        raise HTTPException(400, "title and url are required")

    dedup_raw = f"{source}|{company}|{title}|{url}".lower().strip()
    dedup_hash = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()

    category, score = categorize_job(title, description)
    eu_compat = classify_eu_compatibility(location)
    switzerland_flag = is_switzerland(location)
    match_result = compute_resume_match(title, description)

    session = SessionLocal()
    try:
        existing = session.query(Job).filter_by(dedup_hash=dedup_hash).first()
        if existing:
            raise HTTPException(409, "This job (same source/company/title/url) is already saved")

        job = Job(
            dedup_hash=dedup_hash,
            source=source,
            title=title,
            company=company or None,
            headquarters_raw=location or None,
            url=url,
            description=description,
            posted_at=None,  # manual entries don't have a reliable posted date
            category=category,
            relevance_score=score,
            eu_compatible=eu_compat,
            is_switzerland=switzerland_flag,
            resume_match_pct=match_result["match_pct"],
            status="new",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(
    category: Optional[str] = Query(None, description="Filter by category"),
    eu_compatible: Optional[str] = Query(None, description="Filter by EU compatibility: yes/no/unclear"),
    status: Optional[str] = Query(None, description="Filter by your workflow status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    exclude_not_relevant: bool = Query(
        True, description="By default, hide not_relevant jobs - set false to see everything"
    ),
    sort_by: str = Query("relevance_score", description="relevance_score | resume_match_pct | posted_at | fetched_at"),
    limit: int = Query(100, le=500),
):
    """
    List jobs with optional filters. Defaults to hiding not_relevant
    jobs and sorting by relevance score (highest first), since that's
    the view you actually want most of the time.
    """
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category. Must be one of {VALID_CATEGORIES}")
    if eu_compatible and eu_compatible not in VALID_EU_COMPAT:
        raise HTTPException(400, f"Invalid eu_compatible. Must be one of {VALID_EU_COMPAT}")
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of {VALID_STATUSES}")
    if sort_by not in ("relevance_score", "posted_at", "fetched_at", "resume_match_pct"):
        raise HTTPException(400, "sort_by must be one of: relevance_score, resume_match_pct, posted_at, fetched_at")

    session = SessionLocal()
    try:
        query = session.query(Job)

        if category:
            query = query.filter(Job.category == category)
        elif exclude_not_relevant:
            query = query.filter(Job.category != "not_relevant")

        if eu_compatible:
            query = query.filter(Job.eu_compatible == eu_compatible)
        if status:
            query = query.filter(Job.status == status)
        if source:
            query = query.filter(Job.source == source)

        sort_column = getattr(Job, sort_by)
        query = query.order_by(sort_column.desc())

        return query.limit(limit).all()
    finally:
        session.close()


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    """Fetch a single job by id - useful for a detail view in the frontend."""
    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(404, "Job not found")
        return job
    finally:
        session.close()


@app.patch("/jobs/{job_id}/status", response_model=JobOut)
def update_job_status(job_id: int, update: StatusUpdate):
    """
    Update a job's workflow status. This is what turns the job list
    into a personal applicant tracker - mark things seen/applied/ignored
    as you work through them.
    """
    if update.status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of {VALID_STATUSES}")

    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = update.status
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()


# --- Application pipeline endpoints ---

@app.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=201)
def create_application(job_id: int, app_in: ApplicationCreate):
    """
    Mark a job as applied and start tracking the pipeline.
    Also flips the job's status to 'applied' automatically.
    """
    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(404, "Job not found")

        existing = session.query(Application).filter_by(job_id=job_id).first()
        if existing:
            raise HTTPException(409, "An application already exists for this job. Use PATCH to update it.")

        now = datetime.now(timezone.utc)
        application = Application(
            job_id=job_id,
            applied_at=app_in.applied_at or now,
            stage="applied",
            stage_updated_at=now,
            salary_noted=app_in.salary_noted,
            notes=app_in.notes,
        )
        job.status = "applied"  # keep the job-level status in sync
        session.add(application)
        session.commit()
        session.refresh(application)
        return application
    finally:
        session.close()


@app.patch("/jobs/{job_id}/apply", response_model=ApplicationOut)
def update_application(job_id: int, update: ApplicationUpdate):
    """
    Update stage, notes, or salary on an existing application.
    Changing stage also updates stage_updated_at so you can track
    how long you've been sitting at a given stage.
    """
    if update.stage and update.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Must be one of {VALID_STAGES}")

    session = SessionLocal()
    try:
        application = session.query(Application).filter_by(job_id=job_id).first()
        if not application:
            raise HTTPException(404, "No application found for this job. POST to /jobs/{id}/apply first.")

        now = datetime.now(timezone.utc)
        if update.stage and update.stage != application.stage:
            application.stage = update.stage
            application.stage_updated_at = now
        if update.notes is not None:
            application.notes = update.notes
        if update.salary_noted is not None:
            application.salary_noted = update.salary_noted
        application.updated_at = now

        session.commit()
        session.refresh(application)
        return application
    finally:
        session.close()


@app.get("/jobs/{job_id}/apply", response_model=ApplicationOut)
def get_application(job_id: int):
    """Get the application detail for a specific job."""
    session = SessionLocal()
    try:
        application = session.query(Application).filter_by(job_id=job_id).first()
        if not application:
            raise HTTPException(404, "No application found for this job.")
        return application
    finally:
        session.close()


@app.get("/pipeline", response_model=list[dict])
def get_pipeline():
    """
    Your full application pipeline - all applied jobs with their current
    stage, sorted by applied_at so you see oldest applications first
    (most likely to need a follow-up nudge).

    New mlrd feature:  
    - Uses a single SQL OUTER JOIN (Application + Job) to avoid N+1 queries.
    - Preserves the same response shape while reducing DB round-trips.
    """
    session = SessionLocal()
    try:
        application_rows = (
            session.query(Application, Job)
            .outerjoin(Job, Job.id == Application.job_id)
            .order_by(Application.applied_at.asc())
            .all()
        )
        result = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for SQLite comparison
        for app, job in application_rows:
            # SQLite returns datetimes as naive (no tzinfo) even when stored
            # with timezone.utc - strip tzinfo from both sides to compare safely.
            applied = app.applied_at.replace(tzinfo=None) if app.applied_at else None
            days_since = (now - applied).days if applied else None
            result.append({
                "application_id": app.id,
                "job_id": app.job_id,
                "title": job.title if job else "Unknown",
                "company": job.company if job else "Unknown",
                "url": job.url if job else "",
                "resume_match_pct": job.resume_match_pct if job else 0,
                "eu_compatible": job.eu_compatible if job else "unclear",
                "stage": app.stage,
                "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                "days_since_applied": days_since,
                "salary_noted": app.salary_noted,
                "notes": app.notes,
                "needs_followup": (
                    days_since is not None
                    and days_since >= 10
                    and app.stage not in ("offer", "rejected", "ghosted")
                ),
            })
        return result
    finally:
        session.close()


@app.get("/stats")
def get_stats():
    """Quick overview - counts by category, EU compatibility, status, and pipeline stage."""
    session = SessionLocal()
    try:
        total = session.query(func.count(Job.id)).scalar()

        by_category = dict(
            session.query(Job.category, func.count(Job.id)).group_by(Job.category).all()
        )
        by_eu_compat = dict(
            session.query(Job.eu_compatible, func.count(Job.id))
            .filter(Job.category != "not_relevant")
            .group_by(Job.eu_compatible)
            .all()
        )
        by_status = dict(
            session.query(Job.status, func.count(Job.id))
            .filter(Job.category != "not_relevant")
            .group_by(Job.status)
            .all()
        )
        by_source = dict(
            session.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
        )

        # Pipeline counts - how many applications are at each stage
        by_stage = dict(
            session.query(Application.stage, func.count(Application.id))
            .group_by(Application.stage)
            .all()
        )

        # How many active applications are older than 10 days and might
        # need a follow-up (not yet resolved - no offer/rejection/ghosted)
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for SQLite comparison
        all_apps = session.query(Application).all()
        needs_followup = sum(
            1 for a in all_apps
            if a.applied_at
            and (now - a.applied_at.replace(tzinfo=None)).days >= 10
            and a.stage not in ("offer", "rejected", "ghosted")
        )

        return {
            "total_jobs": total,
            "by_category": by_category,
            "by_eu_compatible_among_relevant": by_eu_compat,
            "by_status_among_relevant": by_status,
            "by_source": by_source,
            "pipeline": {
                "total_applications": session.query(func.count(Application.id)).scalar(),
                "by_stage": by_stage,
                "needs_followup": needs_followup,
            },
        }
    finally:
        session.close()