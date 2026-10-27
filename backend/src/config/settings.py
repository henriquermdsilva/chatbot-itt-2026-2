from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    FRONTEND_DEV_URL: str = "http://localhost:5173"
    FRONTEND_URL: str = "https://chatbot-itt.vercel.app"
    
    GOOGLE_API_KEY: str = ""

    GOOGLE_CLIENT_ID: str = "961077150905-dsdb9plq43u7akdb4c77g3ai3ch1budm.apps.googleusercontent.com"
    AUTH_DEV_MODE: bool = False # Aceita o "dev-token" do botão "Skip Login (Dev)"; nunca em produção
    
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TEMPERATURE: float = 0.3
    
    FAISS_INDEX_PATH: str = "faiss_index"
    
    GOOGLE_DRIVE_FOLDER_ID: str = "" # ID da pasta (fica na URL do navegador)
    GOOGLE_CREDENTIALS_PATH: str = "credentials/service_account.json"
    LOCAL_DATA_PATH: str = "data" # Onde baixar os PDFs do Drive; a pasta é apagada e recriada a cada sincronização
