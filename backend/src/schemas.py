"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(..., min_length=1, max_length=5000)
    sources: List[str] = Field(default_factory=list, max_length=20)


class QueryRequest(BaseModel):
    """Request model for query endpoint."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User query message",
        examples=["Quem compõe a Diretoria do ITT?"]
    )
    history: List[ChatMessage] = Field(default_factory=list[ChatMessage], max_length=12, examples=[[]])


class SourceDocument(BaseModel):
    """Model for source document information."""
    source: str = Field(..., description="Source file name")
    page: Optional[int] = Field(None, description="Page number (1-based)")
    sheet: Optional[str] = Field(None, description="Worksheet name for Excel sources")
    snippet: str = Field(..., description="Relevant part of the document")


class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    response: str = Field(
        ...,
        description="AI-generated response",
        examples=["A Diretoria é composta por Diretor Presidente, Primeiro e Segundo Diretores "
        "Assistentes e Diretor Suplente."]
    )
    source_documents: List[SourceDocument] = Field(
        default_factory=list[SourceDocument],
        description="List of source documents used",
        examples=[[{
            "source": "Estatuto ITT versao registrada 2022-08-20.pdf",
            "page": 4,
            "sheet": None,
            "snippet": "Artigo 13º. A Diretoria será composta por três associados Fundadores...",
        }]]
    )

class ErrorResponse(BaseModel):
    """Response model for errors."""
    detail: str = Field(..., description="Error description")
    error_code: Optional[str] = Field(None, description="Error code for tracking")
