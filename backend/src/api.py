from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
from contextlib import asynccontextmanager

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .routers import chat_router, admin_router
from .routers.chat import limiter
from .dependencies import get_settings
from .services import VectorDB


async def startup_sync():
    """
    Função que roda em segundo plano quando o servidor liga.
    Ela recria a memória automaticamente.
    """
    print("Auto-Sync: Iniciando sincronização automática com Google Drive...")
    try:
        settings = get_settings()
        has_api_key = (
            bool(settings.OPENWEBUI_API_KEY.get_secret_value())
            if settings.LLM_PROVIDER == 'openwebui' else bool(settings.GOOGLE_API_KEY)
        )
        if settings.SYNC_ON_STARTUP and settings.GOOGLE_DRIVE_FOLDER_ID and has_api_key:
            vector_db = VectorDB(settings)
            await asyncio.to_thread(vector_db.refresh_knowledge_base)
            print("Auto-Sync: Memória recriada com sucesso! O Chat está pronto.")
        else:
            print("Auto-Sync: Sincronizacao desativada ou configuracoes incompletas.")
    except Exception as e:
        print(f"Auto-Sync Falhou: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(startup_sync())
    yield
    print("Servidor desligando...")


settings = get_settings()

app = FastAPI(
    title="ITT Chatbot API",
    description="API for ITT institutional chatbot with RAG capabilities",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# Substitui o handler do slowapi, que responde em inglês no campo "error":
# o frontend mostra o campo "detail", como nos demais erros da API.
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded(*_: object) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas perguntas em pouco tempo. Aguarde um minuto e tente de novo."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, settings.FRONTEND_DEV_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "message": "ITT Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["root"])
async def health():
    """
    Liveness probe usado pelo healthcheck do Docker Compose.
    """
    return {"status": "ok"}
