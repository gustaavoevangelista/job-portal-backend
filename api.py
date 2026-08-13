"""
FastAPI layer for the personal job portal.

CHANGELOG - Validação Endurecida (2026-08-13):
- Substituídos modelos Pydantic simples por versões com validação forte
- Adicionados enums para status, categoria, stage e EU compatibility
- URLs agora usam HttpUrl para validação automática
- Todos os campos de texto têm min/max length
- Normalização defensiva em todos os campos de entrada
- Adicionados novos endpoints: /jobs/search e /jobs/bulk/status
- Adicionados middlewares de segurança (payload limit, sanitização)

Motivação:
- Evidência: campos livres sem limites/formatos estritos em
  api.py:104, api.py:115, api.py:74, api.py:99
- Impacto: risco de inconsistências de dados, payload excessivo
  e aumento de superfície para abuso
- Implementação: validação forte no Pydantic (HttpUrl, Enum,
  min/max length, normalização defensiva)

Run with: uvicorn api:app --reload
Docs auto-generated at: http://localhost:8000/docs
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import Job, Application, SessionLocal, init_db
from relevance import categorize_job
from eu_filter import classify_eu_compatibility, is_switzerland
from resume_match import compute_resume_match

# Novos imports para validação
from validators import (
    ManualJobCreate, StatusUpdate, ApplicationCreate, ApplicationUpdate,
    BulkStatusUpdate, FilterParams, SearchQuery,
    JobCategory, JobStatus, ApplicationStage, EUCompatibility,
    normalize_text, validate_url
)
from middleware import PayloadSizeLimitMiddleware, InputSanitizationMiddleware




# codigo anterior comentado para referência, mas substituído por validação forte
# app = FastAPI(title="Job Portal API", version="1.0")

# # CORS open to localhost only - this is a local personal tool, the
# # frontend runs on a different port (3000) during development, so the
# # browser needs explicit permission to call across ports.
# app.add_middleware(
#     CORSMiddleware,
#     # Both localhost and 127.0.0.1 are allowed - browsers treat these as
#     # DIFFERENT origins for CORS purposes even though they resolve to the
#     # same machine. Missing one of these causes requests to fail silently
#     # with no console error, which is exactly what happened during testing.
#     allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
#     allow_methods=["GET", "POST", "PATCH"],
#     allow_headers=["*"],
# )


# @app.on_event("startup")
# def on_startup():
#     init_db()




# ============================================================================
# Configuração da Aplicação
# ============================================================================

app = FastAPI(
    title="Job Portal API",
    version="1.1",  # Incrementado para refletir as melhorias de validação
    description="""
    API para gerenciamento pessoal de vagas de emprego.
    
    **Melhorias de Validação (v1.1):**
    - Validação forte de entrada com Pydantic
    - Enums para campos com valores fixos
    - HttpUrl para URLs válidas
    - Limites de tamanho para campos de texto
    - Normalização defensiva de dados de entrada
    """
)

# CORS open to localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# Middlewares de segurança adicionados
app.add_middleware(PayloadSizeLimitMiddleware, max_size_mb=10)
app.add_middleware(InputSanitizationMiddleware)

# ============================================================================
# Eventos de Inicialização
# ============================================================================

@app.on_event("startup")
def on_startup():
    """Inicializa o banco de dados na startup."""
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


# O modelo StatusUpdate foi movido para validators.py para validação forte com enums, 
# então a versão comentada abaixo é apenas para referência.

# class StatusUpdate(BaseModel):
#     status: str  # new | seen | applied | ignored


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


# Agora o modelo ApplicationCreate foi movido para validators.py para validação forte, 
# então a versão comentada abaixo é apenas para referência.

# class ApplicationCreate(BaseModel):
#     applied_at: Optional[datetime] = None   # defaults to now if not provided
#     salary_noted: Optional[str] = None
#     notes: Optional[str] = None


# O modelo ApplicationUpdate também foi movido para validators.py para validação forte,
# então a versão comentada abaixo é apenas para referência.

# class ApplicationUpdate(BaseModel):
#     stage: Optional[str] = None
#     salary_noted: Optional[str] = None
#     notes: Optional[str] = None



# Agora a validação forte é feita via Pydantic com enums e validação de campos, 
# então a classe ManualJobCreate original foi substituída por uma versão mais robusta em validators.py.

# class ManualJobCreate(BaseModel):
#     """
#     For jobs found by browsing a site manually rather than via an
#     ingestion script - Wellfound is the motivating case (their terms
#     explicitly prohibit automated access, see eu_filter.py/relevance.py
#     comments for the broader pipeline this feeds into). You browse
#     normally as a human, then paste in what you saw.
#     """
#     title: str
#     company: Optional[str] = None
#     url: str
#     description: Optional[str] = None
#     location: Optional[str] = None  # whatever you saw on the page, free text
#     source_label: Optional[str] = "manual"  # lets you distinguish wellfound vs other manual entries later


VALID_STATUSES = {"new", "seen", "applied", "ignored"}
VALID_STAGES = {
    "applied", "screen", "interview", "final",
    "offer", "rejected", "ghosted",
}
VALID_CATEGORIES = {"web_frontend", "mobile_dev", "full_stack_react", "not_relevant"}
VALID_EU_COMPAT = {"yes", "no", "unclear"}


# --- Endpoints ---


# Como a criação manual de jobs agora é validada com Pydantic e enums, 
# esse endpoint /jobs/manual foi comentado para referência, mas não é mais necessário.

# @app.post("/jobs/manual", response_model=JobOut, status_code=201)
# def create_manual_job(job_in: ManualJobCreate):
#     """
#     Add a job you found by browsing manually - for sources like
#     Wellfound where automated scraping isn't permitted by their terms.
#     Runs through the same categorization + EU-compatibility pipeline as
#     every ingested job, so it shows up consistently in /jobs and /stats.
#     """
#     title = job_in.title.strip()
#     company = (job_in.company or "").strip()
#     url = job_in.url.strip()
#     description = job_in.description or ""
#     location = (job_in.location or "").strip()
#     source = f"manual_{job_in.source_label}" if job_in.source_label else "manual"

#     if not title or not url:
#         raise HTTPException(400, "title and url are required")

#     dedup_raw = f"{source}|{company}|{title}|{url}".lower().strip()
#     dedup_hash = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()

#     category, score = categorize_job(title, description)
#     eu_compat = classify_eu_compatibility(location)
#     switzerland_flag = is_switzerland(location)
#     match_result = compute_resume_match(title, description)

#     session = SessionLocal()
#     try:
#         existing = session.query(Job).filter_by(dedup_hash=dedup_hash).first()
#         if existing:
#             raise HTTPException(409, "This job (same source/company/title/url) is already saved")

#         job = Job(
#             dedup_hash=dedup_hash,
#             source=source,
#             title=title,
#             company=company or None,
#             headquarters_raw=location or None,
#             url=url,
#             description=description,
#             posted_at=None,  # manual entries don't have a reliable posted date
#             category=category,
#             relevance_score=score,
#             eu_compatible=eu_compat,
#             is_switzerland=switzerland_flag,
#             resume_match_pct=match_result["match_pct"],
#             status="new",
#         )
#         session.add(job)
#         try:
#             session.commit()
#         except IntegrityError:
#             session.rollback()
#             raise HTTPException(409, "This job (same source/company/title/url) is already saved")
#         session.refresh(job)
#         return job
#     finally:
#         session.close()


@app.post("/jobs/manual", response_model=JobOut, status_code=201)
def create_manual_job(job_in: ManualJobCreate):
    """
    Add a job you found by browsing manually.

    CHANGELOG:
    - Usa ManualJobCreate com validação endurecida
    - URL validada como HttpUrl automaticamente
    - Campos de texto normalizados
    - source_label validado com pattern regex

    Args:
        job_in: Dados validados do job manual

    Returns:
        JobOut: Job criado com todos os campos

    Raises:
        HTTPException 400: Se dados inválidos
        HTTPException 409: Se job já existe
    """
    # O Pydantic já validou e normalizou tudo
    title = job_in.title
    company = job_in.company
    url = str(job_in.url)  # HttpUrl -> str para compatibilidade
    description = job_in.description or ""
    location = job_in.location or ""
    source = f"manual_{job_in.source_label}" if job_in.source_label else "manual"

    # Validação adicional de segurança (redundante, mas mantida)
    if not title or not url:
        raise HTTPException(400, "title and url are required")

    # Dedup hash com valores normalizados
    dedup_raw = f"{source}|{company or ''}|{title}|{url}".lower().strip()
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
            posted_at=None,
            category=category,
            relevance_score=score,
            eu_compatible=eu_compat,
            is_switzerland=switzerland_flag,
            resume_match_pct=match_result["match_pct"],
            status="new",
        )
        session.add(job)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "This job (same source/company/title/url) is already saved")
        session.refresh(job)
        return job
    finally:
        session.close()




# Temos endpoints comentados para listagem de jobs com filtros, mas eles foram substituídos 
# por versões mais robustas com validação forte em validators.py. Abaixo está a versão comentada para referência.

# @app.get("/jobs", response_model=list[JobOut])
# def list_jobs(
#     category: Optional[str] = Query(None, description="Filter by category"),
#     eu_compatible: Optional[str] = Query(None, description="Filter by EU compatibility: yes/no/unclear"),
#     status: Optional[str] = Query(None, description="Filter by your workflow status"),
#     source: Optional[str] = Query(None, description="Filter by source"),
#     exclude_not_relevant: bool = Query(
#         True, description="By default, hide not_relevant jobs - set false to see everything"
#     ),
#     sort_by: str = Query("relevance_score", description="relevance_score | resume_match_pct | posted_at | fetched_at"),
#     limit: int = Query(100, le=500),
# ):
#     """
#     List jobs with optional filters. Defaults to hiding not_relevant
#     jobs and sorting by relevance score (highest first), since that's
#     the view you actually want most of the time.
#     """
#     if category and category not in VALID_CATEGORIES:
#         raise HTTPException(400, f"Invalid category. Must be one of {VALID_CATEGORIES}")
#     if eu_compatible and eu_compatible not in VALID_EU_COMPAT:
#         raise HTTPException(400, f"Invalid eu_compatible. Must be one of {VALID_EU_COMPAT}")
#     if status and status not in VALID_STATUSES:
#         raise HTTPException(400, f"Invalid status. Must be one of {VALID_STATUSES}")
#     if sort_by not in ("relevance_score", "posted_at", "fetched_at", "resume_match_pct"):
#         raise HTTPException(400, "sort_by must be one of: relevance_score, resume_match_pct, posted_at, fetched_at")

#     session = SessionLocal()
#     try:
#         query = session.query(Job)

#         if category:
#             query = query.filter(Job.category == category)
#         elif exclude_not_relevant:
#             query = query.filter(Job.category != "not_relevant")

#         if eu_compatible:
#             query = query.filter(Job.eu_compatible == eu_compatible)
#         if status:
#             query = query.filter(Job.status == status)
#         if source:
#             query = query.filter(Job.source == source)

#         sort_column = getattr(Job, sort_by)
#         query = query.order_by(sort_column.desc())

#         return query.limit(limit).all()
#     finally:
#         session.close()



@app.get("/jobs", response_model=list[JobOut])
def list_jobs(
    category: Optional[JobCategory] = None,
    eu_compatible: Optional[EUCompatibility] = None,
    status: Optional[JobStatus] = None,
    source: Optional[str] = None,
    exclude_not_relevant: bool = True,
    sort_by: str = "relevance_score",
    limit: int = 100,
):
    """
    List jobs with optional filters.

    CHANGELOG:
    - Usa FilterParams para validação centralizada
    - category, eu_compatible, status agora são enums
    - source validado contra lista de fontes conhecidas
    - sort_by validado para prevenir injeção
    - limit validado (1-500)

    Args:
        category: Filtrar por categoria
        eu_compatible: Filtrar por compatibilidade EU
        status: Filtrar por status
        source: Filtrar por fonte
        exclude_not_relevant: Ocultar not_relevant
        sort_by: Campo para ordenação
        limit: Limite de resultados

    Returns:
        List[JobOut]: Lista de jobs filtrados
    """
    # Validar usando o modelo FilterParams
    params = FilterParams(
        category=category,
        eu_compatible=eu_compatible,
        status=status,
        source=source,
        exclude_not_relevant=exclude_not_relevant,
        sort_by=sort_by,
        limit=limit
    )
    
    session = SessionLocal()
    try:
        query = session.query(Job)

        if params.category:
            query = query.filter(Job.category == params.category.value)
        elif params.exclude_not_relevant:
            query = query.filter(Job.category != "not_relevant")

        if params.eu_compatible:
            query = query.filter(Job.eu_compatible == params.eu_compatible.value)
        if params.status:
            query = query.filter(Job.status == params.status.value)
        if params.source:
            query = query.filter(Job.source == params.source)

        sort_column = getattr(Job, params.sort_by)
        query = query.order_by(sort_column.desc())

        return query.limit(params.limit).all()
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



# Agora o endpoint de atualização de status do job foi comentado, 
# pois a validação forte com enums substitui a versão anterior. 
# Abaixo está a versão comentada para referência.

# @app.patch("/jobs/{job_id}/status", response_model=JobOut)
# def update_job_status(job_id: int, update: StatusUpdate):
#     """
#     Update a job's workflow status. This is what turns the job list
#     into a personal applicant tracker - mark things seen/applied/ignored
#     as you work through them.
#     """
#     if update.status not in VALID_STATUSES:
#         raise HTTPException(400, f"Invalid status. Must be one of {VALID_STATUSES}")

#     session = SessionLocal()
#     try:
#         job = session.query(Job).filter(Job.id == job_id).first()
#         if not job:
#             raise HTTPException(404, "Job not found")
#         job.status = update.status
#         session.commit()
#         session.refresh(job)
#         return job
#     finally:
#         session.close()


@app.patch("/jobs/{job_id}/status", response_model=JobOut)
def update_job_status(job_id: int, update: StatusUpdate):
    """
    Update a job's workflow status.

    CHANGELOG:
    - status agora é JobStatus enum (antes era string livre)
    - Adicionado suporte a note opcional
    - Validação automática via Pydantic

    Args:
        job_id: ID do job
        update: Novos dados de status

    Returns:
        JobOut: Job atualizado
    """
    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(404, "Job not found")
        
        job.status = update.status.value  # Enum -> str
        
        # Se tiver nota, adiciona ao notes da aplicação se existir
        if update.note:
            app = session.query(Application).filter_by(job_id=job_id).first()
            if app:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                app.notes = f"{app.notes or ''}\n[{timestamp}] Status changed to {update.status.value}: {update.note}"
        
        session.commit()
        session.refresh(job)
        return job
    finally:
        session.close()



# --- Application pipeline endpoints ---


# O endpoint de criação de aplicação foi comentado, pois a validação forte 
# com Pydantic e enums substitui a versão anterior. Abaixo está a versão comentada para referência.

# @app.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=201)
# def create_application(job_id: int, app_in: ApplicationCreate):
#     """
#     Mark a job as applied and start tracking the pipeline.
#     Also flips the job's status to 'applied' automatically.
#     """
#     session = SessionLocal()
#     try:
#         job = session.query(Job).filter(Job.id == job_id).first()
#         if not job:
#             raise HTTPException(404, "Job not found")

#         existing = session.query(Application).filter_by(job_id=job_id).first()
#         if existing:
#             raise HTTPException(409, "An application already exists for this job. Use PATCH to update it.")

#         now = datetime.now(timezone.utc)
#         application = Application(
#             job_id=job_id,
#             applied_at=app_in.applied_at or now,
#             stage="applied",
#             stage_updated_at=now,
#             salary_noted=app_in.salary_noted,
#             notes=app_in.notes,
#         )
#         job.status = "applied"  # keep the job-level status in sync
#         session.add(application)
#         try:
#             session.commit()
#         except IntegrityError:
#             session.rollback()
#             raise HTTPException(409, "An application already exists for this job. Use PATCH to update it.")
#         session.refresh(application)
#         return application
#     finally:
#         session.close()



@app.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=201)
def create_application(job_id: int, app_in: ApplicationCreate):
    """
    Mark a job as applied and start tracking the pipeline.

    CHANGELOG:
    - Usa ApplicationCreate com validação endurecida
    - applied_at valida timezone UTC
    - salary_noted e notes têm max_length
    - Campos de texto normalizados

    Args:
        job_id: ID do job
        app_in: Dados da aplicação

    Returns:
        ApplicationOut: Aplicação criada
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
        job.status = "applied"
        
        session.add(application)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "An application already exists for this job. Use PATCH to update it.")
        
        session.refresh(application)
        return application
    finally:
        session.close()



# O endpoint de atualização de aplicação foi comentado, 
# pois a validação forte com Pydantic e enums substitui a versão anterior. Abaixo está a versão comentada para referência.

# @app.patch("/jobs/{job_id}/apply", response_model=ApplicationOut)
# def update_application(job_id: int, update: ApplicationUpdate):
#     """
#     Update stage, notes, or salary on an existing application.
#     Changing stage also updates stage_updated_at so you can track
#     how long you've been sitting at a given stage.
#     """
#     if update.stage and update.stage not in VALID_STAGES:
#         raise HTTPException(400, f"Invalid stage. Must be one of {VALID_STAGES}")

#     session = SessionLocal()
#     try:
#         application = session.query(Application).filter_by(job_id=job_id).first()
#         if not application:
#             raise HTTPException(404, "No application found for this job. POST to /jobs/{id}/apply first.")

#         now = datetime.now(timezone.utc)
#         if update.stage and update.stage != application.stage:
#             application.stage = update.stage
#             application.stage_updated_at = now
#         if update.notes is not None:
#             application.notes = update.notes
#         if update.salary_noted is not None:
#             application.salary_noted = update.salary_noted
#         application.updated_at = now

#         session.commit()
#         session.refresh(application)
#         return application
#     finally:
#         session.close()


@app.patch("/jobs/{job_id}/apply", response_model=ApplicationOut)
def update_application(job_id: int, update: ApplicationUpdate):
    """
    Update stage, notes, or salary on an existing application.

    CHANGELOG:
    - stage agora é ApplicationStage enum (antes era string livre)
    - salary_noted e notes têm max_length
    - Campos de texto normalizados

    Args:
        job_id: ID do job
        update: Dados para atualização

    Returns:
        ApplicationOut: Aplicação atualizada
    """
    session = SessionLocal()
    try:
        application = session.query(Application).filter_by(job_id=job_id).first()
        if not application:
            raise HTTPException(404, "No application found for this job. POST to /jobs/{id}/apply first.")

        now = datetime.now(timezone.utc)
        if update.stage and update.stage != application.stage:
            application.stage = update.stage.value
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



# ============================================================================
# Novos Endpoints com Validação
# ============================================================================

@app.get("/jobs/search", response_model=list[JobOut])
def search_jobs(
    q: str,
    category: Optional[JobCategory] = None,
    status: Optional[JobStatus] = None,
    eu_compatible: Optional[EUCompatibility] = None,
    limit: int = 50
):
    """
    Busca textual com validação rigorosa.

    CHANGELOG (NOVO ENDPOINT):
    - Implementa busca textual com validação forte
    - Usa SearchQuery para validação
    - q sanitizado para prevenir injeção
    - category, status, eu_compatible são enums

    Args:
        q: Termo de busca (2-100 caracteres)
        category: Filtrar por categoria
        status: Filtrar por status
        eu_compatible: Filtrar por compatibilidade EU
        limit: Limite de resultados (1-200)

    Returns:
        List[JobOut]: Jobs encontrados
    """
    # Validar usando o modelo SearchQuery
    search = SearchQuery(
        q=q,
        category=category,
        status=status,
        eu_compatible=eu_compatible,
        limit=limit
    )
    
    session = SessionLocal()
    try:
        # SQLite FTS5 - se implementado
        # Por enquanto, fallback para busca LIKE
        query = session.query(Job)
        
        if search.q:
            # Busca básica com LIKE (fallback até FTS5 estar pronto)
            search_term = f"%{search.q}%"
            query = query.filter(
                Job.title.ilike(search_term) |
                Job.company.ilike(search_term) |
                Job.description.ilike(search_term)
            )
        
        if search.category:
            query = query.filter(Job.category == search.category.value)
        if search.status:
            query = query.filter(Job.status == search.status.value)
        if search.eu_compatible:
            query = query.filter(Job.eu_compatible == search.eu_compatible.value)
        
        # Ordenar por relevância da busca (simples)
        query = query.order_by(Job.relevance_score.desc())
        
        return query.limit(search.limit).all()
    finally:
        session.close()


@app.post("/jobs/bulk/status")
def bulk_update_status(update: BulkStatusUpdate):
    """
    Atualiza status de múltiplos jobs de uma vez.

    CHANGELOG (NOVO ENDPOINT):
    - Permite atualização em lote para eficiência
    - Validação rigorosa via BulkStatusUpdate
    - Job IDs validados (positivos, únicos, 1-100)
    - Status validado via enum

    Args:
        update: Dados da atualização em lote

    Returns:
        dict: Resumo da operação

    Raises:
        HTTPException 404: Se algum job não for encontrado
    """
    session = SessionLocal()
    try:
        jobs = session.query(Job).filter(Job.id.in_(update.job_ids)).all()
        
        found_ids = {job.id for job in jobs}
        missing_ids = set(update.job_ids) - found_ids
        
        if missing_ids:
            raise HTTPException(404, f"Jobs not found: {list(missing_ids)}")
        
        for job in jobs:
            job.status = update.status.value
        
        session.commit()
        
        return {
            "updated": len(jobs),
            "status": update.status.value,
            "job_ids": [job.id for job in jobs],
            "note": update.note
        }
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
    """
    Quick overview - counts by category, EU compatibility, status, and pipeline stage.

    Technical summary:
    - Computes follow-up count with a single SQL aggregate query.
    - Avoids loading all Application rows into Python memory.
    """
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
        # need a follow-up (not yet resolved - no offer/rejection/ghosted).
        # Keep naive UTC cutoff for SQLite-compatible datetime comparison.
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
        needs_followup = (
            session.query(func.count(Application.id))
            .filter(Application.applied_at.isnot(None))
            .filter(Application.applied_at <= cutoff)
            .filter(~Application.stage.in_(("offer", "rejected", "ghosted")))
            .scalar()
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