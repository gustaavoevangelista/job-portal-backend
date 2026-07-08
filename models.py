"""
Database models for the job portal.

Two tables:
  - Job: what the job is (ingested from sources, scored, categorized)
  - Application: what YOU are doing about it (pipeline stage, notes,
    salary info, dates). Kept separate from Job intentionally - the
    ingestion pipeline should never overwrite your application notes
    when it re-fetches a job, and a job's metadata (title, company,
    EU-compat) should be readable without coupling to application state.
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Dedup key: a hash of (source + company + title + url).
    # Unique constraint means re-running ingestion never creates duplicates.
    dedup_hash = Column(String(64), unique=True, nullable=False, index=True)

    source = Column(String(50), nullable=False)        # e.g. "weworkremotely_frontend", "remotive", "working_nomads"
    title = Column(String(300), nullable=False)
    company = Column(String(200))
    headquarters_raw = Column(String(300))               # location/region signal - meaning varies by source, see ingestion modules
    url = Column(String(500), nullable=False)
    description = Column(Text)
    posted_at = Column(DateTime)                         # when the job was posted (per source)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Category instead of a flat true/false - a job can be a strong web
    # frontend match, a mobile match (React Native, Swift, Flutter, etc),
    # a full-stack role with heavy React signal, or not relevant at all.
    # See relevance.py for how this is decided.
    #   "web_frontend"      - title clearly says frontend/React/Vue/Angular web role
    #   "mobile_dev"        - mobile (React Native, Swift/SwiftUI, Flutter, native Android/iOS), kept separate from web
    #   "full_stack_react"  - full-stack/product engineer titles with strong React signal in description
    #   "not_relevant"      - everything else
    category = Column(String(20), default="not_relevant", index=True)
    relevance_score = Column(Integer, default=0)

    # How well this job matches YOUR actual skills (React/Next/TS core
    # stack + secondary experience), 0-100. See resume_match.py.
    # Distinct from relevance_score, which only measures "is this a
    # frontend/full-stack/mobile role at all" - this measures "is this
    # role a good fit for what you specifically know."
    resume_match_pct = Column(Integer, default=0, index=True)

    # Derived from headquarters_raw via eu_filter.py - "yes"/"no"/"unclear".
    # Deliberately conservative: ambiguous strings like "Worldwide" are
    # "unclear", not "yes" - see eu_filter.py module docstring for why.
    eu_compatible = Column(String(10), default="unclear", index=True)
    # Switzerland is geographically/culturally EU-adjacent but NOT an EU
    # member state - tracked separately since it matters for actual
    # payroll/tax/EOR feasibility, not lumped into eu_compatible="yes".
    is_switzerland = Column(Boolean, default=False)

    # Triage status - this is pre-application: have you seen/dismissed
    # this listing? Separate from Application.stage which tracks the
    # actual pipeline once you've applied.
    status = Column(String(20), default="new")           # new | seen | applied | ignored

    # One job can have at most one application (for you, in this single-
    # user tool) but modeled as a relationship rather than inline columns
    # so the ingestion pipeline can never accidentally overwrite notes.
    application = relationship("Application", back_populates="job", uselist=False)


class Application(Base):
    """
    Tracks your actual pipeline for a job you've applied to.
    Created when you decide to apply; updated as the process progresses.

    Pipeline stages (stage column):
      applied      - you sent an application
      screen       - phone/email screen scheduled or done
      interview    - technical or cultural interview stage
      final        - final round / decision pending
      offer        - you have an offer in hand
      rejected     - they said no, or you withdrew
      ghosted      - applied, no response after follow-up

    Deliberately simple: no sub-stages, no "interview 1 / interview 2"
    tracking - put that level of detail in the notes field. A notes
    field that you actually use beats a perfect schema you don't.
    """
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True, nullable=False, index=True)

    # When you sent the application - used to compute "days since applied"
    # for follow-up reminders and to sort your pipeline chronologically.
    applied_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc))

    # Current pipeline stage
    stage = Column(String(20), nullable=False, default="applied")
    # When the stage last changed - useful for "how long have I been
    # at this stage?" without having to parse notes for dates.
    stage_updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Salary/rate discussed or listed - free text so you can write
    # "€65k", "€450/day", "TBD", or whatever is actually relevant.
    salary_noted = Column(String(100))

    # Free-text notes - recruiter name, what you said, red flags,
    # follow-up dates, anything. Don't over-engineer this; just write.
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="application")


# SQLite file lives next to this script. Swap this path if you want
# the DB stored elsewhere (e.g. a `data/` folder).
DATABASE_URL = "sqlite:///jobs.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create tables if they don't exist yet. Safe to call every run."""
    Base.metadata.create_all(engine)