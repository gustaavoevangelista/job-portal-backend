# Job Portal Backend

A lightweight FastAPI-based backend service for aggregating job listings from multiple sources and providing intelligent job matching and filtering. Designed as a personal job discovery tool with EU location compatibility checks and resume matching capabilities.

## Overview

The Job Portal Backend is a single-user local API that:

- **Aggregates Jobs**: Collects job postings from RSS feeds and JSON APIs
- **Smart Filtering**: Filters jobs by EU compatibility, relevance scoring, and other criteria
- **Resume Matching**: Computes match scores between job descriptions and your resume/experience
- **Status Tracking**: Maintains application status for each job (new, seen, applied, ignored)
- **Quick Stats**: Provides overview metrics of your job search progress

### Key Design Principles

This is a **minimal, personal tool** by design:
- ✅ No authentication required (single-user local use)
- ✅ No rate limiting (controlled environment)
- ✅ No multi-tenancy (your data only)
- ✅ Simple and focused (intentionally lightweight)

## Quick Start

### Prerequisites

- Python 3.9+
- pip or poetry for dependency management
- SQLite (included with Python)

### Installation

```bash
# Create a virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
uvicorn api:app --reload
```

The API will be available at `http://localhost:8000`

**Interactive API Documentation**: Visit `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc)

## Available Modules

| Module | Purpose |
|--------|---------|
| `api.py` | FastAPI application with REST endpoints |
| `models.py` | SQLAlchemy database models (Job, Application) |
| `ingest_rss.py` | RSS feed scraping and job ingestion |
| `ingest_json_apis.py` | JSON API scraping and job ingestion |
| `relevance.py` | Job relevance categorization (LLM-based) |
| `eu_filter.py` | EU location detection and compatibility checks |
| `resume_match.py` | Resume-to-job matching and scoring |

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com) - Modern async Python web framework
- **Database**: [SQLAlchemy](https://www.sqlalchemy.org) + SQLite - ORM and database
- **Job Scheduling**: [APScheduler](https://apscheduler.readthedocs.io) - Background task scheduling
- **Web Scraping**: [Playwright](https://playwright.dev) - Browser automation for scraping
- **Feed Parsing**: [feedparser](https://feedparser.readthedocs.io) - RSS/Atom feed parsing
- **Validation**: [Pydantic](https://docs.pydantic.dev) - Data validation and settings
- **Server**: [Uvicorn](https://www.uvicorn.org) - ASGI server

## API Endpoints

### Jobs

- `GET /jobs` - List all jobs with optional filters
  - Query parameters: `status`, `eu_compatible`, `min_relevance`, etc.
  
- `GET /jobs/{job_id}` - Get specific job details

- `PATCH /jobs/{job_id}` - Update job status
  - Request body: `{"status": "seen" | "applied" | "ignored"}`

### Statistics

- `GET /stats` - Get overview statistics
  - Returns: total jobs, application counts by status, match score distribution

### Data Models

**Job** Fields:
- `id` - Unique identifier
- `title` - Job title
- `company` - Company name
- `location` - Job location
- `description` - Full job description
- `source_url` - URL to job posting
- `source` - Source of the job (RSS feed, API, etc.)
- `posted_date` - When job was posted
- `relevance_score` - AI-based relevance (0-100)
- `resume_match_score` - Your resume match (0-100)
- `eu_compatible` - Whether location is EU-compatible
- `status` - Application status (new, seen, applied, ignored)
- `created_at` - When job was added to portal
- `updated_at` - Last update timestamp

## Database

SQLite database is automatically created on first run. Database file location can be configured via environment variables.

## CORS Configuration

CORS is configured to allow requests from the frontend running on:
- `http://localhost:3000`
- `http://127.0.0.1:3000`

Both localhost variants are explicitly allowed because browsers treat them as different origins.

## Environment Variables

Create a `.env` file in the backend directory:

```env
# Database
DATABASE_URL=sqlite:///./job_portal.db

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Job Ingestion
RSS_FEED_URLS=https://example.com/jobs.xml
JSON_API_URLS=https://example.com/api/jobs

# Other settings
LOG_LEVEL=INFO
```

## Development

### Running with Hot Reload

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Database Management

The database is automatically initialized on startup. To reset:

```bash
# Delete the database file to start fresh
rm job_portal.db
# Restart the API server
```

### Running Ingestion

```bash
python ingest_rss.py
python ingest_json_apis.py
```

## License

This project is private and for personal use.
