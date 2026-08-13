"""
Validações compartilhadas e modelos Pydantic endurecidos para o job portal.

Este módulo centraliza todas as definições de validação para garantir:
- Consistência de tipos e formatos em toda a aplicação
- Prevenção de dados malformados ou maliciosos
- Documentação clara dos requisitos de cada campo
- Reutilização entre diferentes endpoints

As validações foram endurecidas para resolver:
- Evidência: campos livres sem limites/formatos estritos em 
  api.py:104, api.py:115, api.py:74, api.py:99
- Impacto: risco de inconsistências de dados, payload excessivo 
  e aumento de superfície para abuso
- Implementação: validação forte no Pydantic (HttpUrl, Enum, 
  min/max length, normalização defensiva)

Principais mudanças:
- HttpUrl para URLs (validação de formato obrigatória)
- Enums para campos com conjunto fixo de valores
- min_length/max_length para campos de texto
- Normalização defensiva (strip, remoção de whitespace excessivo)
- Validação customizada com @field_validator
"""

import re
from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from pydantic import ValidationError

# ============================================================================
# ENUMS PARA CAMPOS COM VALORES FIXOS
# ============================================================================
# Substitui strings soltas que podiam receber qualquer valor
# ============================================================================

class JobCategory(str, Enum):
    """
    Categorias de vaga - valores fixos e validados.
    
    Mudança: antes era uma string livre em api.py:74, agora é um enum
    que garante que apenas valores válidos sejam aceitos.
    """
    WEB_FRONTEND = "web_frontend"
    MOBILE_DEV = "mobile_dev"
    FULL_STACK_REACT = "full_stack_react"
    NOT_RELEVANT = "not_relevant"

class JobStatus(str, Enum):
    """
    Status do workflow - valores fixos e validados.
    
    Mudança: antes era uma string livre em api.py:115, agora é um enum
    que garante que apenas valores válidos sejam aceitos.
    """
    NEW = "new"
    SEEN = "seen"
    APPLIED = "applied"
    IGNORED = "ignored"

class ApplicationStage(str, Enum):
    """
    Estágios do pipeline de aplicação - valores fixos e validados.
    
    Mudança: antes era uma string livre em api.py:104, agora é um enum
    que garante que apenas valores válidos sejam aceitos.
    """
    APPLIED = "applied"
    SCREEN = "screen"
    INTERVIEW = "interview"
    FINAL = "final"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"

class EUCompatibility(str, Enum):
    """
    Compatibilidade EU - valores fixos e validados.
    """
    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"

class SourceType(str, Enum):
    """
    Fontes de jobs - validadas para evitar valores inventados.
    """
    WEWORKREMOTELY_FRONTEND = "weworkremotely_frontend"
    WEWORKREMOTELY_FULLSTACK = "weworkremotely_fullstack"
    REMOTIVE = "remotive"
    WORKING_NOMADS = "working_nomads"
    REMOTEOK = "remoteok"
    MANUAL = "manual"
    
    @classmethod
    def is_valid_source(cls, value: str) -> bool:
        """
        Permite manual_* prefixos dinâmicos para fontes manuais.
        
        Exemplo: "manual_wellfound" é válido, mesmo não estando no enum.
        """
        if value.startswith("manual_"):
            return True
        return value in cls._value2member_map_

# ============================================================================
# MODELOS BASE COM VALIDAÇÕES ENDURECIDAS
# ============================================================================

class BaseJobModel(BaseModel):
    """
    Campos base para todos os modelos de job com validações rigorosas.
    
    Mudanças implementadas:
    - title: agora tem min_length=1 e max_length=300 (antes era livre)
    - company: agora tem min_length=1 e max_length=200 (antes era livre)
    - url: agora é HttpUrl (antes era string sem validação)
    - description: agora tem max_length=50000 (antes era livre)
    - location: agora tem min_length=1 e max_length=300 (antes era livre)
    - Todos os campos de texto passam por normalização automática
    """
    
    title: str = Field(
        min_length=1,
        max_length=300,
        description="Título da vaga - obrigatório, 1-300 caracteres"
    )
    company: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Nome da empresa - opcional, até 200 caracteres"
    )
    url: HttpUrl = Field(
        description="URL da vaga - deve ser uma URL válida (http/https)"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=50000,  # 50KB limite razoável para descrição
        description="Descrição da vaga - opcional, até 50KB"
    )
    location: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Localização - opcional, até 300 caracteres"
    )
    
    @field_validator("title", "company", "location")
    @classmethod
    def strip_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalização: remove whitespace excessivo de campos de texto.
        
        Mudança: implementa normalização defensiva para garantir
        consistência dos dados armazenados.
        """
        if v is not None and isinstance(v, str):
            # Remove espaços extras, tabs, newlines
            cleaned = re.sub(r'\s+', ' ', v.strip())
            return cleaned if cleaned else None
        return v
    
    @field_validator("description")
    @classmethod
    def clean_description(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalização defensiva de descrição.
        
        Mudança: remove caracteres de controle não-imprimíveis
        para prevenir problemas de renderização e storage.
        """
        if v is not None and isinstance(v, str):
            # Remove whitespace excessivo mas preserva quebras de linha
            cleaned = re.sub(r'[ \t]+', ' ', v.strip())
            # Remove caracteres de controle não-imprimíveis
            cleaned = ''.join(char for char in cleaned if char.isprintable() or char in '\n\r\t')
            return cleaned if cleaned else None
        return v

# ============================================================================
# MODELOS DE REQUISIÇÃO COM VALIDAÇÃO ENDURECIDA
# ============================================================================

class ManualJobCreate(BaseModel):
    """
    Modelo para criação manual de jobs com validação endurecida.
    
    Mudanças implementadas:
    - Adicionado Field com min_length/max_length para todos os campos
    - Adicionado HttpUrl para validação de URL
    - source_label com normalização e validação manual
    - @field_validator com mode="before" para normalização ANTES da validação
    - @field_validator com mode="after" para normalização final
    """
    
    title: str = Field(
        min_length=1,
        max_length=300,
        description="Título da vaga - obrigatório"
    )
    company: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Nome da empresa"
    )
    url: HttpUrl = Field(
        description="URL da vaga - deve ser uma URL válida"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="Descrição da vaga"
    )
    location: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Localização da vaga"
    )
    source_label: Optional[str] = Field(
        default="manual",
        min_length=1,
        max_length=50,
        description="Rótulo para identificar fonte manual específica"
    )
    
    @field_validator("title", "company", "location", "description", mode="before")
    @classmethod
    def normalize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """
        Normaliza campos de texto ANTES da validação.
        
        Importante: mode="before" garante que a normalização
        aconteça antes das validações de pattern e length.
        """
        if v is not None and isinstance(v, str):
            # Remove espaços extras, tabs, newlines
            cleaned = re.sub(r'\s+', ' ', v.strip())
            return cleaned if cleaned else None
        return v
    
    @field_validator("source_label", mode="before")
    @classmethod
    def normalize_source_label_before(cls, v: Optional[str]) -> Optional[str]:
        """
        Normaliza source_label ANTES da validação.
        
        Isso garante que caracteres especiais e espaços sejam
        tratados antes da validação do pattern.
        """
        if v is not None and isinstance(v, str):
            # Remove espaços extras
            cleaned = v.strip()
            if cleaned == "":
                return "manual"
            # Converte para minúsculas e substitui caracteres especiais
            normalized = re.sub(r'[^a-z0-9_\-]', '_', cleaned.lower())
            return normalized if normalized else "manual"
        return "manual"
    
    @field_validator("source_label", mode="after")
    @classmethod
    def validate_source_label(cls, v: Optional[str]) -> Optional[str]:
        """
        Validação final do source_label.
        
        Verifica se o valor normalizado atende ao padrão.
        """
        if v is not None:
            # Verifica se contém apenas caracteres permitidos
            if not re.match(r'^[a-z0-9_\-]+$', v):
                raise ValueError(f"Invalid source_label: '{v}'. Must contain only a-z, 0-9, _, -")
        return v
    
    @model_validator(mode="after")
    def validate_manual_job(self) -> "ManualJobCreate":
        """
        Validação adicional de consistência entre campos.
        """
        # Se company for vazio depois do strip, vira None
        if self.company == "":
            self.company = None
        return self
    

class StatusUpdate(BaseModel):
    """
    Modelo para atualização de status com validação endurecida.
    
    Substitui o modelo StatusUpdate original em api.py:56-58.
    
    Mudanças implementadas:
    - status agora é JobStatus enum (antes era string livre)
    - Adicionado campo note opcional com validação
    - Adicionado @field_validator para normalização
    """
    
    status: JobStatus = Field(
        description="Novo status do job"
    )
    note: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Nota opcional sobre a mudança de status"
    )
    
    @field_validator("note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza nota para consistência."""
        if v:
            cleaned = re.sub(r'\s+', ' ', v.strip())
            return cleaned if cleaned else None
        return v

class ApplicationCreate(BaseModel):
    """
    Modelo para criação de aplicação com validação endurecida.
    
    Substitui o modelo ApplicationCreate original em api.py:70-75.
    
    Mudanças implementadas:
    - applied_at agora valida timezone (garante UTC)
    - salary_noted tem max_length=100 (antes era livre)
    - notes tem max_length=5000 (antes era livre)
    - Adicionado @field_validator para normalização
    """
    
    applied_at: Optional[datetime] = Field(
        default=None,
        description="Data de aplicação - padrão: agora"
    )
    salary_noted: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Salário mencionado - até 100 caracteres"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Notas sobre a aplicação - até 5KB"
    )
    
    @field_validator("salary_noted", "notes")
    @classmethod
    def clean_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza campos de texto."""
        if v:
            cleaned = re.sub(r'\s+', ' ', v.strip())
            return cleaned if cleaned else None
        return v
    
    @field_validator("applied_at")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        """
        Garante que a data está em UTC com timezone.
        
        Mudança: previne problemas de comparação de datas
        entre diferentes timezones.
        """
        if v:
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        return v

class ApplicationUpdate(BaseModel):
    """
    Modelo para atualização de aplicação com validação endurecida.
    
    Substitui o modelo ApplicationUpdate original em api.py:77-82.
    
    Mudanças implementadas:
    - stage agora é ApplicationStage enum (antes era string livre)
    - salary_noted tem max_length=100 (antes era livre)
    - notes tem max_length=5000 (antes era livre)
    - Adicionado @field_validator para normalização
    """
    
    stage: Optional[ApplicationStage] = Field(
        default=None,
        description="Novo estágio do pipeline"
    )
    salary_noted: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Salário mencionado - até 100 caracteres"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Notas sobre a aplicação - até 5KB"
    )
    
    @field_validator("salary_noted", "notes")
    @classmethod
    def clean_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza campos de texto."""
        if v:
            cleaned = re.sub(r'\s+', ' ', v.strip())
            return cleaned if cleaned else None
        return v

class BulkStatusUpdate(BaseModel):
    """
    Modelo para atualização em lote de status (nova feature).
    
    Mudanças implementadas:
    - job_ids: lista de inteiros com validação de tamanho (1-100)
    - status: JobStatus enum
    - note: opcional com max_length=1000
    - @field_validator para remover duplicatas e validar IDs
    """
    
    job_ids: List[int] = Field(
        min_length=1,
        max_length=100,
        description="IDs dos jobs para atualizar - entre 1 e 100"
    )
    status: JobStatus = Field(
        description="Novo status para todos os jobs"
    )
    note: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Nota opcional sobre a mudança em lote"
    )
    
    @field_validator("job_ids")
    @classmethod
    def validate_job_ids(cls, v: List[int]) -> List[int]:
        """
        Remove duplicatas e valida IDs positivos.
        
        Mudança: garante que IDs sejam válidos e únicos
        para evitar problemas de processamento em lote.
        """
        if not v:
            raise ValueError("At least one job ID is required")
        
        # Remove duplicatas mantendo ordem
        seen = set()
        unique_ids = []
        for job_id in v:
            if job_id not in seen:
                seen.add(job_id)
                unique_ids.append(job_id)
        
        for job_id in unique_ids:
            if job_id <= 0:
                raise ValueError(f"Job ID must be positive, got {job_id}")
        
        return unique_ids

class SearchQuery(BaseModel):
    """
    Modelo para busca textual (nova feature).
    
    Mudanças implementadas:
    - q: query com min/max length
    - category, status, eu_compatible: enums para validação
    - limit: validação de range (1-200)
    - @field_validator para sanitização da query
    """
    
    q: str = Field(
        min_length=2,
        max_length=100,
        description="Termo de busca - 2-100 caracteres"
    )
    category: Optional[JobCategory] = Field(
        default=None,
        description="Filtro por categoria"
    )
    status: Optional[JobStatus] = Field(
        default=None,
        description="Filtro por status"
    )
    eu_compatible: Optional[EUCompatibility] = Field(
        default=None,
        description="Filtro por compatibilidade EU"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Limite de resultados - 1-200"
    )
    
    @field_validator("q")
    @classmethod
    def clean_query(cls, v: str) -> str:
        """
        Limpa e normaliza a query de busca.
        
        Mudança: remove caracteres especiais que podem
        quebrar a busca ou causar injeção.
        """
        # Remove caracteres especiais que podem quebrar FTS
        cleaned = re.sub(r'[^\w\s\-]', ' ', v)
        cleaned = re.sub(r'\s+', ' ', cleaned.strip())
        return cleaned

class FilterParams(BaseModel):
    """
    Parâmetros de filtro para listagem (endurecimento do existente).
    
    Mudanças implementadas:
    - category, eu_compatible, status: enums (antes eram strings livres)
    - source: validação via SourceType.is_valid_source
    - sort_by: validação de campo válido
    - limit: validação de range (1-500)
    """
    
    category: Optional[JobCategory] = Field(
        default=None,
        description="Filtro por categoria"
    )
    eu_compatible: Optional[EUCompatibility] = Field(
        default=None,
        description="Filtro por compatibilidade EU"
    )
    status: Optional[JobStatus] = Field(
        default=None,
        description="Filtro por status"
    )
    source: Optional[str] = Field(
        default=None,
        description="Filtro por fonte"
    )
    exclude_not_relevant: bool = Field(
        default=True,
        description="Ocultar jobs not_relevant por padrão"
    )
    sort_by: str = Field(
        default="relevance_score",
        description="Campo para ordenação"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Limite de resultados - 1-500"
    )
    
    @field_validator("source")
    @classmethod
    def validate_source(cls, v: Optional[str]) -> Optional[str]:
        """
        Valida que a fonte é conhecida ou é manual_*.
        
        Mudança: previne uso de fontes inventadas que poderiam
        causar inconsistências nos dados.
        """
        if v:
            if not SourceType.is_valid_source(v):
                valid_sources = list(SourceType._value2member_map_.keys())
                raise ValueError(
                    f"Invalid source: {v}. Must be one of {valid_sources} or manual_*"
                )
        return v
    
    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        """
        Valida campo de ordenação.
        
        Mudança: previne injeção de SQL via ordenação arbitrária.
        """
        valid_fields = {"relevance_score", "posted_at", "fetched_at", "resume_match_pct"}
        if v not in valid_fields:
            raise ValueError(f"sort_by must be one of: {', '.join(valid_fields)}")
        return v

# ============================================================================
# FUNÇÕES AUXILIARES PARA USO EM OUTROS MÓDULOS
# ============================================================================

def normalize_text(text: Optional[str]) -> Optional[str]:
    """
    Normalização defensiva de texto para uso geral.
    
    Usada em ingestão e outros módulos que precisam de
    normalização consistente.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r'\s+', ' ', text.strip())
    return cleaned if cleaned else None

def validate_url(url: str) -> bool:
    """
    Validação adicional de URL (além do HttpUrl).
    
    Usada em ingestão para validar URLs antes de processar.
    """
    if not url:
        return False
    try:
        HttpUrl(url)
        return True
    except ValueError:
        return False

def sanitize_for_search(text: str) -> str:
    """
    Sanitiza texto para busca FTS.
    """
    return re.sub(r'[^\w\s]', ' ', text.lower().strip())