from fastapi import APIRouter, Depends, HTTPException, status
from ..config import Settings
from ..services import VectorDB
from ..dependencies import get_settings, get_vector_db, get_current_user_email

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

@router.post("/sync-knowledge")
def sync_knowledge_base(
    user_email: str = Depends(get_current_user_email),
    settings: Settings = Depends(get_settings),
    vector_db: VectorDB = Depends(get_vector_db),
):
    """
    Aciona a sincronização com o Google Drive e reindexação.

    A rota é síncrona de propósito: o FastAPI a executa em outra thread, então a API
    continua respondendo durante a indexação, que pode levar vários minutos.
    """
    admins = {email.strip().lower() for email in settings.ADMIN_EMAILS.split(",") if email.strip()}
    if user_email.lower() not in admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para atualizar os documentos.",
        )

    print(f"Sincronização solicitada por {user_email}")
    try:
        return vector_db.refresh_knowledge_base()
    except Exception as e:
        print(f"Erro na sincronização: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao atualizar a base de conhecimento. Veja os logs do servidor.",
        )
