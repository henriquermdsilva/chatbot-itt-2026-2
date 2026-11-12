"""
Chat router for handling conversational endpoints.
"""
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status, Depends
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..schemas import (
    QueryRequest,
    QueryResponse,
    SourceDocument,
    ErrorResponse
)

from ..services import ITTGraph, IndexNotFoundError
from ..dependencies import get_graph, get_current_user_email

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/chat", 
    tags=["chat"],
    responses={500: {"model": ErrorResponse, "description": "Internal server error"}}
)


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Process user query",
    description="Process a user query and return AI-generated response with source documents",
    responses={
        200: {"description": "Successful response", "model": QueryResponse},
        400: {"description": "Bad request - invalid input", "model": ErrorResponse},
        401: {"description": "Missing, invalid or expired login token", "model": ErrorResponse},
        429: {"description": "Too many requests", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
        503: {"description": "Documents not indexed yet", "model": ErrorResponse},
    },
)
@limiter.limit("5/minute")
async def query_response(
    request: Request,
    query: QueryRequest,
    user_email: str = Depends(get_current_user_email),
    graph: ITTGraph = Depends(get_graph),
) -> QueryResponse:
    try:
        logger.info(f"Processing query from user: {user_email}")

        result = graph.invoke(query.message, history=[message.model_dump() for message in query.history])

        source_documents = [
            SourceDocument(**doc) for doc in result.get("source_documents", [])
        ]

        response = QueryResponse(
            response=result["response"],
            source_documents=source_documents
        )

        logger.info(f"Query processed successfully for user: {user_email}")
        return response

    except IndexNotFoundError as e:
        logger.warning(f"Índice indisponível: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A base de conhecimento ainda não foi indexada. Avise quem administra o sistema.",
        )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível processar a pergunta. Tente novamente.",
        )


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Process user query with streaming",
    description=(
        "Streams AI-generated response tokens as NDJSON (JSON Lines). "
        "Each line is a JSON object with a 'type' field: "
        "'sources' (sent once before tokens), 'token' (one per fragment), or 'done'."
    ),
    responses={
        200: {"description": "NDJSON stream of response tokens and sources"},
        400: {"description": "Bad request - invalid input", "model": ErrorResponse},
        401: {"description": "Missing, invalid or expired login token", "model": ErrorResponse},
        429: {"description": "Too many requests", "model": ErrorResponse},
        503: {"description": "Documents not indexed yet", "model": ErrorResponse},
    },
)
@limiter.limit("5/minute")
async def stream_response(
    request: Request,
    query: QueryRequest,
    user_email: str = Depends(get_current_user_email),
    graph: ITTGraph = Depends(get_graph),
) -> StreamingResponse:
    logger.info(f"Streaming query from user: {user_email}")

    async def generate():
        try:
            async for event in graph.astream_response(
                query.message,
                history=[m.model_dump() for m in query.history],
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except IndexNotFoundError as e:
            logger.warning(f"Índice indisponível no stream: {e}")
            yield json.dumps({
                "type": "error",
                "data": "A base de conhecimento ainda não foi indexada. Avise quem administra o sistema.",
            }, ensure_ascii=False) + "\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield json.dumps({
                "type": "error",
                "data": "Não foi possível processar a pergunta. Tente novamente.",
            }, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
