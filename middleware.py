"""
Middlewares para validação e segurança adicional.

CHANGELOG (2026-08-13):
- Adicionado PayloadSizeLimitMiddleware: limita tamanho do payload
- Adicionado InputSanitizationMiddleware: sanitiza entrada JSON

Motivação:
- Prevenir ataques de DoS via payloads grandes
- Prevenir injeção via caracteres de controle
- Complementar a validação Pydantic com camada de segurança
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import json
import re


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limita tamanho do payload para evitar abuso.

    Implementação:
    - Verifica o header Content-Length
    - Rejeita requests com payload maior que o limite configurado

    Motivação:
    - Prevenir ataques de DoS
    - Evitar sobrecarga de memória
    """
    
    def __init__(self, app, max_size_mb: int = 10):
        """
        Inicializa o middleware com limite configurável.

        Args:
            app: Aplicação FastAPI
            max_size_mb: Tamanho máximo em MB (padrão: 10)
        """
        super().__init__(app)
        self.max_size = max_size_mb * 1024 * 1024
    
    async def dispatch(self, request: Request, call_next):
        """
        Processa a request, verificando o tamanho do payload.

        Args:
            request: Request HTTP
            call_next: Próximo middleware/handler

        Returns:
            Response: Resposta HTTP
        """
        if request.method in ("POST", "PATCH", "PUT"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Payload too large. Max size: {self.max_size // (1024*1024)}MB"
                    }
                )
        
        return await call_next(request)


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Sanitiza entrada para prevenir injection em campos de texto.

    Implementação:
    - Remove caracteres de controle não-imprimíveis
    - Preserva caracteres Unicode válidos
    - Opera recursivamente em objetos JSON

    Motivação:
    - Prevenir injeção de caracteres de controle
    - Garantir dados limpos para storage
    - Complementar a normalização do Pydantic
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Processa a request, sanitizando o payload JSON.

        Args:
            request: Request HTTP
            call_next: Próximo middleware/handler

        Returns:
            Response: Resposta HTTP
        """
        # Só processa JSON
        if request.method in ("POST", "PATCH", "PUT"):
            try:
                body = await request.body()
                if body:
                    data = json.loads(body)
                    # Sanitiza campos de texto recursivamente
                    sanitized = self._sanitize_object(data)
                    # Substitui o body com dados sanitizados
                    # Nota: isso modifica a request, o que é seguro pois 
                    # o corpo original já foi lido
                    request._body = json.dumps(sanitized).encode()
            except json.JSONDecodeError:
                # Se não for JSON, passa adiante
                pass
        
        return await call_next(request)
    
    def _sanitize_object(self, obj):
        """
        Sanitiza recursivamente objetos JSON.

        Args:
            obj: Objeto Python (dict, list, str, etc)

        Returns:
            Objeto sanitizado
        """
        if isinstance(obj, dict):
            return {k: self._sanitize_object(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_object(item) for item in obj]
        elif isinstance(obj, str):
            # Remove caracteres de controle, mantém Unicode válido
            return ''.join(char for char in obj if char.isprintable() or char in '\n\r\t')
        else:
            return obj