"""Chat e embeddings do OpenWebUI, usando a mesma chave de usuario."""

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableLambda
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings


class RateLimitError(RuntimeError):
    pass


def post(settings: Settings, path: str, payload: dict) -> dict:
    key = settings.OPENWEBUI_API_KEY.get_secret_value()
    if not key:
        raise ValueError('Defina OPENWEBUI_API_KEY (ou api_key) no backend/.test.env.')
    try:
        response = httpx.post(
            settings.OPENWEBUI_BASE_URL.rstrip('/') + path,
            headers={'Authorization': f'Bearer {key}'},
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


def get_openwebui_chat(settings: Settings):
    def invoke(prompt):
        roles = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
        result = post(settings, '/api/chat/completions', {
            'model': settings.LLM_MODEL,
            'messages': [{'role': roles[m.type], 'content': m.content} for m in prompt.to_messages()],
            'temperature': settings.LLM_TEMPERATURE,
            'max_tokens': 1024,
            'stream': False,
        })
        try:
            content = result['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError('OpenWebUI retornou uma resposta de chat vazia ou invalida.') from None

    return RunnableLambda(invoke)


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
