"""Chat e embeddings do OpenWebUI, usando a mesma chave de usuario."""

import json
import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from typing import Any, AsyncIterator, Iterator, List, Optional
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings


class RateLimitError(RuntimeError):
    pass

def _auth_headers(settings: Settings) -> dict:
    key = settings.OPENWEBUI_API_KEY.get_secret_value()
    if not key:
        raise ValueError('Defina OPENWEBUI_API_KEY (ou api_key) no backend/.test.env.')
    return {'Authorization': f'Bearer {key}'}

def post(settings: Settings, path: str, payload: dict) -> dict:
    try:
        response = httpx.post(
            settings.OPENWEBUI_BASE_URL.rstrip('/') + path,
            headers=_auth_headers(settings),
            json=payload, timeout=settings.LLM_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        error = RateLimitError if exc.response.status_code == 429 else RuntimeError
        raise error(
            f'OpenWebUI retornou HTTP {exc.response.status_code}. '
            'Verifique a chave, o modelo e as permissoes do endpoint.'
        ) from None
    except httpx.RequestError:
        raise RuntimeError('Falha de conexao ou tempo limite ao acessar OpenWebUI.') from None
    except ValueError:
        raise RuntimeError('OpenWebUI retornou uma resposta JSON invalida.') from None


def _roles(messages: List[BaseMessage]) -> List[dict]:
    role_map = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
    return [{'role': role_map[m.type], 'content': m.content} for m in messages]

def _parse_sse_line(line: str) -> str:
    """Extrai o token de texto de uma linha SSE 'data: {...}'.

    Retorna string vazia para linhas de controle ([DONE], vazias, erros).
    """
    if not line.startswith('data:'):
        return ''
    data = line[len('data:'):].strip()
    if data == '[DONE]':
        return ''
    try:
        chunk = json.loads(data)
        return chunk['choices'][0]['delta'].get('content') or ''
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return ''


class OpenWebUIChat(BaseChatModel):
    """LangChain ChatModel backed by the OpenWebUI /api/chat/completions endpoint.

    Supports both synchronous invoke() and streaming via stream() / astream(),
    so graph.py can call rag_chain.astream() and receive real token-by-token chunks.
    """

    settings: Any  # Settings object injected at construction

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "openwebui"

    def _build_payload(self, messages: List[BaseMessage], stream: bool) -> dict:
        return {
            'model': self.settings.LLM_MODEL,
            'messages': _roles(messages),
            'temperature': self.settings.LLM_TEMPERATURE,
            'max_tokens': 1024,
            'stream': stream,
        }

    # ------------------------------------------------------------------
    # Synchronous path (used by triage chain and /chat/query endpoint)
    # ------------------------------------------------------------------
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._build_payload(messages, stream=False)
        result = post(self.settings, '/api/chat/completions', payload)
        try:
            content = result['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError('OpenWebUI retornou uma resposta de chat vazia ou invalida.') from None
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    # ------------------------------------------------------------------
    # Synchronous streaming (stream())
    # ------------------------------------------------------------------
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        payload = self._build_payload(messages, stream=True)
        url = self.settings.OPENWEBUI_BASE_URL.rstrip('/') + '/api/chat/completions'
        headers = _auth_headers(self.settings)
        with httpx.stream('POST', url, headers=headers, json=payload,
                          timeout=self.settings.LLM_TIMEOUT) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                token = _parse_sse_line(line)
                if token:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=token))

    # ------------------------------------------------------------------
    # Asynchronous streaming (astream()) — usado por graph.py
    # ------------------------------------------------------------------
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        payload = self._build_payload(messages, stream=True)
        url = self.settings.OPENWEBUI_BASE_URL.rstrip('/') + '/api/chat/completions'
        headers = _auth_headers(self.settings)
        async with httpx.AsyncClient(timeout=self.settings.LLM_TIMEOUT) as client:
            async with client.stream('POST', url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    token = _parse_sse_line(line)
                    if token:
                        yield ChatGenerationChunk(message=AIMessageChunk(content=token))


def get_openwebui_chat(settings: Settings) -> OpenWebUIChat:
    return OpenWebUIChat(settings=settings)


class OpenWebUIEmbeddings(Embeddings):
    def __init__(self, settings: Settings):
        self.settings = settings

    def _embed(self, texts: list[str]) -> list[list[float]]:
        result = post(self.settings, '/ollama/api/embed', {
            'model': self.settings.OPENWEBUI_EMBEDDING_MODEL, 'input': texts,
        })
        vectors = result.get('embeddings')
        if not isinstance(vectors, list) or len(vectors) != len(texts) or any(not v for v in vectors):
            raise RuntimeError('OpenWebUI retornou embeddings invalidos.')
        return vectors

    # Só a indexação espera: em uma pergunta do chat, é melhor mostrar o erro logo
    @retry(
        retry=retry_if_exception_type(RateLimitError), reraise=True,
        wait=wait_exponential(multiplier=5, max=60), stop=stop_after_attempt(5),
        before_sleep=lambda _: print('Servidor ocupado (HTTP 429). Aguardando para tentar de novo.',
                                     flush=True),
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._embed(['search_document: ' + text for text in texts])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), 32):
            vectors.extend(self._embed_batch(texts[start:start + 32]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed(['search_query: ' + text])[0]
