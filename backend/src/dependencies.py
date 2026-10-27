"""
FastAPI dependencies for dependency injection.
"""
import logging
from functools import lru_cache
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from .services import VectorDB, ITTGraph
from .config import Settings

logger = logging.getLogger(__name__)

DEV_TOKEN = "dev-token"
DEV_EMAIL = "dev@itt.local"

# Tolerância para relógios fora de sincronia entre o servidor e o Google
CLOCK_SKEW_SECONDS = 30

# auto_error=False: sem token, devolvemos nosso próprio 401 em vez do erro padrão do FastAPI
bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings instance
    """
    return Settings()


def get_vector_db(settings: Settings = Depends(get_settings)) -> VectorDB:
    """
    Get VectorDB instance with injected settings.
    
    Args:
        settings: Injected Settings instance
        
    Returns:
        VectorDB instance
    """
    return VectorDB(settings)


def get_graph(
    settings: Settings = Depends(get_settings),
    vector_db: VectorDB = Depends(get_vector_db)
) -> ITTGraph:
    """
    Get ITTGraph instance with injected dependencies.
    
    Args:
        settings: Injected Settings instance
        vector_db: Injected VectorDB instance
        
    Returns:
        ITTGraph instance
    """
    return ITTGraph(settings, vector_db)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_email(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Validate the Google ID token sent as "Authorization: Bearer <token>".

    Args:
        credentials: Injected Bearer token, or None when missing
        settings: Injected Settings instance

    Returns:
        Verified e-mail of the logged-in user
    """
    if credentials is None:
        raise _unauthorized("Login necessário.")
    token = credentials.credentials

    if settings.AUTH_DEV_MODE and token == DEV_TOKEN:
        return DEV_EMAIL

    try:
        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID, CLOCK_SKEW_SECONDS
        )
    except ValueError as e:
        logger.warning(f"Token do Google recusado: {e}")
        raise _unauthorized("Sessão inválida ou expirada. Entre novamente.")
    except GoogleAuthError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar o login agora. Tente novamente.",
        )

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise _unauthorized("A conta Google precisa ter um e-mail verificado.")
    return email
