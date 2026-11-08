from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field, SecretStr

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / '.test.env', BACKEND_DIR / '.env'),
        env_file_encoding='utf-8-sig', extra='ignore',
    )
    
    FRONTEND_DEV_URL: str = "http://localhost:5173"
    FRONTEND_URL: str = "https://chatbot-itt.vercel.app"
    
    GOOGLE_API_KEY: str = ""

    GOOGLE_CLIENT_ID: str = "961077150905-dsdb9plq43u7akdb4c77g3ai3ch1budm.apps.googleusercontent.com"
    ALLOWED_EMAIL_DOMAIN: str = "institutotadao-itt.org.br" # Vazio aceita qualquer domínio
    AUTH_DEV_MODE: bool = False # Aceita o "dev-token" do botão "Skip Login (Dev)"; nunca em produção
    ADMIN_EMAILS: str = "" # E-mails que podem usar "Atualizar Docs", separados por vírgula
    
    LLM_PROVIDER: Literal['openwebui', 'google'] = 'openwebui'
    OPENWEBUI_BASE_URL: str = 'https://llm.ic.unicamp.br'
    OPENWEBUI_API_KEY: SecretStr = Field(
        default=SecretStr(''), validation_alias=AliasChoices('OPENWEBUI_API_KEY', 'api_key')
    )
    OPENWEBUI_EMBEDDING_MODEL: str = 'nomic-embed-text:latest'
    LLM_TIMEOUT: float = Field(default=120, gt=0)
    LLM_MODEL: str = 'gemma3:12b'
    LLM_TEMPERATURE: float = 0.3
    RETRIEVAL_LANGUAGE: str = ''
    
    FAISS_INDEX_PATH: str = str(BACKEND_DIR / 'faiss_index_openwebui')
    
    GOOGLE_DRIVE_FOLDER_ID: str = "" # ID da pasta (fica na URL do navegador)
    SYNC_ON_STARTUP: bool = True
    GOOGLE_CREDENTIALS_PATH: str = str(BACKEND_DIR / 'credentials' / 'service_account.json')
    GOOGLE_CREDENTIALS_JSON: SecretStr = SecretStr('')
    local_data_path: str = str(BACKEND_DIR / 'data') # Pasta ou PDF local
