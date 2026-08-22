"""
Testes para os validadores Pydantic.

CHANGELOG (2026-08-13):
- Testes para todos os modelos de validação
- Verifica casos válidos e inválidos
- Testa normalização de campos
- CORRIGIDO: Mensagens de erro agora verificam o texto correto
- CORRIGIDO: Testes de normalização com source_label
- CORRIGIDO: Teste source_label_with_spaces agora espera normalização
- CORRIGIDO: Teste empty_title verifica string_type também
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from validators import (
    ManualJobCreate, StatusUpdate, ApplicationCreate, ApplicationUpdate,
    BulkStatusUpdate, SearchQuery, FilterParams,
    JobStatus, ApplicationStage, EUCompatibility, JobCategory
)


class TestManualJobCreate:
    """Testes para ManualJobCreate."""
    
    def test_valid_job(self):
        """Teste de criação com dados válidos."""
        job = ManualJobCreate(
            title="Senior React Developer",
            company="Tech Corp",
            url="https://example.com/job/123",
            description="Great job opportunity",
            location="Remote Europe",
            source_label="wellfound"
        )
        assert job.title == "Senior React Developer"
        assert job.company == "Tech Corp"
        assert str(job.url) == "https://example.com/job/123"
        assert job.source_label == "wellfound"
    
    def test_strips_whitespace(self):
        """Teste de normalização de whitespace."""
        job = ManualJobCreate(
            title="  Senior React Developer  ",
            company="  Tech Corp  ",
            url="https://example.com/job/123",
            location="  Remote  ",
            source_label="wellfound"
        )
        assert job.title == "Senior React Developer"
        assert job.company == "Tech Corp"
        assert job.location == "Remote"
        assert job.source_label == "wellfound"
    
    def test_source_label_normalization(self):
        """Teste de normalização de source_label."""
        job = ManualJobCreate(
            title="Developer",
            company="Tech Corp",
            url="https://example.com/job/123",
            source_label="Wellfound!@#"
        )
        assert job.source_label == "wellfound___"
    
    def test_source_label_with_spaces(self):
        """Teste que source_label com espaços é normalizado."""
        job = ManualJobCreate(
            title="Developer",
            company="Tech Corp",
            url="https://example.com/job/123",
            source_label="  wellfound  "
        )
        assert job.source_label == "wellfound"
    
    def test_invalid_url(self):
        """Teste que URL inválida é rejeitada."""
        with pytest.raises(ValidationError) as exc:
            ManualJobCreate(
                title="Developer",
                company="Tech Corp",
                url="not-a-url"
            )
        assert "url" in str(exc.value).lower()
    
    def test_title_too_long(self):
        """Teste que título muito longo é rejeitado."""
        long_title = "A" * 301
        with pytest.raises(ValidationError) as exc:
            ManualJobCreate(
                title=long_title,
                company="Tech Corp",
                url="https://example.com/job/123"
            )
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg
    
    def test_empty_title(self):
        """Teste que título vazio é rejeitado."""
        with pytest.raises(ValidationError) as exc:
            ManualJobCreate(
                title="",
                company="Tech Corp",
                url="https://example.com/job/123"
            )
        # O validador pode retornar string_type (se virar None) ou string_too_short
        error_msg = str(exc.value)
        assert "string_type" in error_msg or "too_short" in error_msg or "min_length" in error_msg


class TestStatusUpdate:
    """Testes para StatusUpdate."""
    
    def test_valid_status(self):
        """Teste com status válido."""
        update = StatusUpdate(status=JobStatus.APPLIED)
        assert update.status == JobStatus.APPLIED
    
    def test_valid_status_with_note(self):
        """Teste com status válido e nota."""
        update = StatusUpdate(
            status=JobStatus.SEEN,
            note="Reviewed this job"
        )
        assert update.status == JobStatus.SEEN
        assert update.note == "Reviewed this job"
    
    def test_invalid_status(self):
        """Teste que status inválido é rejeitado."""
        with pytest.raises(ValidationError):
            StatusUpdate(status="invalid_status")  # type: ignore
    
    def test_note_too_long(self):
        """Teste que nota muito longa é rejeitada."""
        long_note = "A" * 1001
        with pytest.raises(ValidationError) as exc:
            StatusUpdate(
                status=JobStatus.SEEN,
                note=long_note
            )
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg


class TestApplicationCreate:
    """Testes para ApplicationCreate."""
    
    def test_valid_application(self):
        """Teste com dados válidos."""
        app = ApplicationCreate(
            salary_noted="€65k",
            notes="Applied via LinkedIn"
        )
        assert app.salary_noted == "€65k"
        assert app.notes == "Applied via LinkedIn"
    
    def test_with_applied_at(self):
        """Teste com applied_at especificado."""
        now = datetime.now()
        app = ApplicationCreate(
            applied_at=now,
            salary_noted="€65k"
        )
        assert app.applied_at.tzinfo is not None
    
    def test_salary_too_long(self):
        """Teste que salary_noted muito longo é rejeitado."""
        long_salary = "€" * 101
        with pytest.raises(ValidationError) as exc:
            ApplicationCreate(salary_noted=long_salary)
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg
    
    def test_notes_too_long(self):
        """Teste que notes muito longo é rejeitado."""
        long_notes = "A" * 5001
        with pytest.raises(ValidationError) as exc:
            ApplicationCreate(notes=long_notes)
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg
    
    def test_strips_whitespace(self):
        """Teste de normalização de whitespace."""
        app = ApplicationCreate(
            salary_noted="  €65k  ",
            notes="  Applied via LinkedIn  "
        )
        assert app.salary_noted == "€65k"
        assert app.notes == "Applied via LinkedIn"


class TestApplicationUpdate:
    """Testes para ApplicationUpdate."""
    
    def test_valid_update(self):
        """Teste com dados válidos."""
        update = ApplicationUpdate(
            stage=ApplicationStage.INTERVIEW,
            salary_noted="€70k",
            notes="Technical interview scheduled"
        )
        assert update.stage == ApplicationStage.INTERVIEW
        assert update.salary_noted == "€70k"
        assert update.notes == "Technical interview scheduled"
    
    def test_partial_update(self):
        """Teste com dados parciais."""
        update = ApplicationUpdate(stage=ApplicationStage.OFFER)
        assert update.stage == ApplicationStage.OFFER
        assert update.salary_noted is None
        assert update.notes is None
    
    def test_invalid_stage(self):
        """Teste que stage inválido é rejeitado."""
        with pytest.raises(ValidationError):
            ApplicationUpdate(stage="invalid_stage")  # type: ignore


class TestBulkStatusUpdate:
    """Testes para BulkStatusUpdate."""
    
    def test_valid_bulk_update(self):
        """Teste com dados válidos."""
        update = BulkStatusUpdate(
            job_ids=[1, 2, 3],
            status=JobStatus.SEEN,
            note="Reviewed all"
        )
        assert len(update.job_ids) == 3
        assert update.status == JobStatus.SEEN
        assert update.note == "Reviewed all"
    
    def test_deduplicates_job_ids(self):
        """Teste que job_ids são deduplicados."""
        update = BulkStatusUpdate(
            job_ids=[1, 2, 2, 3, 3, 3],
            status=JobStatus.SEEN
        )
        assert update.job_ids == [1, 2, 3]
    
    def test_empty_job_ids(self):
        """Teste que lista vazia é rejeitada."""
        with pytest.raises(ValidationError) as exc:
            BulkStatusUpdate(
                job_ids=[],
                status=JobStatus.SEEN
            )
        error_msg = str(exc.value)
        assert "too_short" in error_msg or "min_length" in error_msg
    
    def test_too_many_job_ids(self):
        """Teste que mais de 100 IDs é rejeitado."""
        with pytest.raises(ValidationError) as exc:
            BulkStatusUpdate(
                job_ids=list(range(101)),
                status=JobStatus.SEEN
            )
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg
    
    def test_negative_job_id(self):
        """Teste que ID negativo é rejeitado."""
        with pytest.raises(ValidationError) as exc:
            BulkStatusUpdate(
                job_ids=[-1, 1, 2],
                status=JobStatus.SEEN
            )
        assert "positive" in str(exc.value)


class TestSearchQuery:
    """Testes para SearchQuery."""
    
    def test_valid_search(self):
        """Teste com busca válida."""
        search = SearchQuery(
            q="React developer",
            category=JobCategory.WEB_FRONTEND,
            limit=50
        )
        assert search.q == "React developer"
        assert search.category == JobCategory.WEB_FRONTEND
        assert search.limit == 50
    
    def test_query_too_short(self):
        """Teste que query muito curta é rejeitada."""
        with pytest.raises(ValidationError) as exc:
            SearchQuery(q="R")
        error_msg = str(exc.value)
        assert "too_short" in error_msg or "min_length" in error_msg
    
    def test_query_too_long(self):
        """Teste que query muito longa é rejeitada."""
        long_query = "A" * 101
        with pytest.raises(ValidationError) as exc:
            SearchQuery(q=long_query)
        error_msg = str(exc.value)
        assert "too_long" in error_msg or "max_length" in error_msg
    
    def test_sanitizes_query(self):
        """Teste que query é sanitizada."""
        search = SearchQuery(q="React!@# Developer")
        assert search.q == "React Developer"
    
    def test_limit_out_of_range(self):
        """Teste que limit fora do range é rejeitado."""
        with pytest.raises(ValidationError):
            SearchQuery(q="test", limit=0)
        with pytest.raises(ValidationError):
            SearchQuery(q="test", limit=201)


class TestFilterParams:
    """Testes para FilterParams."""
    
    def test_valid_filters(self):
        """Teste com filtros válidos."""
        params = FilterParams(
            category=JobCategory.WEB_FRONTEND,
            eu_compatible=EUCompatibility.YES,
            status=JobStatus.NEW,
            source="remotive",
            sort_by="relevance_score",
            limit=100
        )
        assert params.category == JobCategory.WEB_FRONTEND
        assert params.source == "remotive"
    
    def test_manual_source_valid(self):
        """Teste que source manual_* é válido."""
        params = FilterParams(source="manual_wellfound")
        assert params.source == "manual_wellfound"
    
    def test_invalid_source(self):
        """Teste que source inválido é rejeitado."""
        with pytest.raises(ValidationError) as exc:
            FilterParams(source="invalid_source")
        assert "Invalid source" in str(exc.value)
    
    def test_invalid_sort_by(self):
        """Teste que sort_by inválido é rejeitado."""
        with pytest.raises(ValidationError) as exc:
            FilterParams(sort_by="invalid_field")
        assert "sort_by must be one of" in str(exc.value)
    
    def test_limit_out_of_range(self):
        """Teste que limit fora do range é rejeitado."""
        with pytest.raises(ValidationError):
            FilterParams(limit=0)
        with pytest.raises(ValidationError):
            FilterParams(limit=501)