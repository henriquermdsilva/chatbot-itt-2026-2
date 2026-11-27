Fork do repositório [github.com/chraujo/chatbot-itt-2026-1](https://github.com/chraujo/chatbot-itt-2026-1). Aqui, são documentados os avanços obtidos no desenvolvimento do chatbot para o Instituto Tadao Takahashi (ITT) durante o segundo semestre de 2026.

Guilherme de Godoi Monteiro - 237031
    
Henrique Ribeiro Medeiros da Silva - 243172

Renilson Conceição de Luna Júnior - 247358

Vitor Ferreira dos Santos de Lacerda - 231524

## Como rodar

Requer Python 3.12, [uv](https://docs.astral.sh/uv/) e Node.js.

1. Em `backend/`, copie `.env.example` para `.env` e preencha `OPENWEBUI_API_KEY` e `GOOGLE_DRIVE_FOLDER_ID`
2. Salve o JSON da Service Account em `backend/credentials/service_account.json`
3. Em `frontend/`, copie `.env.example` para `.env`
4. Na raiz: `npm install` e `npm run dev`. Ctrl+C encerra os dois.

**Separadamente:**
- Backend, em `backend/`: `uv sync` e `uv run uvicorn src.api:app --reload --port 8000`
- Frontend, em `frontend/`: `npm install` e `npm run dev`


## Executar com a API da Unicamp

Veja o [guia para executar o chatbot com Google Drive](RUN_CHATBOT.md) para configurar
o acesso à pasta do projeto, indexar os documentos e iniciar o backend e a interface.

Veja o [setup completo da API](backend/README.md) para configurar sua chave, indexar PDFs locais e iniciar o backend e a interface.

## Endpoints e variáveis de ambiente

### Endpoints principais

| Endpoint | Método | Descrição |
| --- | --- | --- |
| `/` | GET | Informações básicas da API. |
| `/health` | GET | Liveness probe usada pelo Docker Compose. |
| `/chat/query` | POST | Pergunta com resposta JSON e fontes. |
| `/chat/stream` | POST | Pergunta com resposta em NDJSON e streaming. |
| `/admin/sync-knowledge` | POST | Sincronização restrita a administradores. |
| `/docs` | GET | Swagger UI. |
| `/redoc` | GET | ReDoc. |

### Variáveis de ambiente do backend

| Variável | Função |
| --- | --- |
| `OPENWEBUI_API_KEY` | Chave da API da Unicamp/OpenWebUI. |
| `OPENWEBUI_BASE_URL` | URL base do serviço. |
| `LLM_PROVIDER` | `openwebui` ou `google`. |
| `LLM_MODEL` | Modelo de chat. |
| `OPENWEBUI_EMBEDDING_MODEL` | Modelo de embeddings. |
| `LLM_TIMEOUT` | Tempo limite das chamadas ao modelo. |
| `RETRIEVAL_LANGUAGE` | Idioma opcional para traduzir a consulta de busca. |
| `FAISS_INDEX_PATH` | Caminho do índice FAISS. |
| `GOOGLE_DRIVE_FOLDER_ID` | ID da pasta do Drive. |
| `SYNC_ON_STARTUP` | Ativa ou desativa a sincronização no boot. |
| `GOOGLE_CREDENTIALS_PATH` | Caminho do JSON da conta de serviço. |
| `GOOGLE_CREDENTIALS_JSON` | Alternativa ao arquivo, com o JSON em uma linha. |
| `GOOGLE_CLIENT_ID` | Client ID usado na validação do token. |
| `ALLOWED_EMAIL_DOMAIN` | Domínio de e-mail permitido. |
| `AUTH_DEV_MODE` | Aceita `dev-token` apenas em desenvolvimento. |
| `ADMIN_EMAILS` | E-mails autorizados a sincronizar documentos. |
| `FRONTEND_URL` | Origem permitida pelo CORS em produção. |
| `FRONTEND_DEV_URL` | Origem permitida pelo CORS em desenvolvimento. |

### Variáveis do frontend

| Variável | Função |
| --- | --- |
| `VITE_API_URL` | URL do backend usada pelo frontend. |
| `VITE_GOOGLE_CLIENT_ID` | Client ID do botão Google, quando configurado. |

## Comandos de execução e testes

### Backend em desenvolvimento

```bash
cd backend
uv sync
uv run uvicorn src.api:app --reload --port 8000
```

### Frontend em desenvolvimento

```bash
cd frontend
npm install
npm run dev
```

### Indexação local

```bash
cd backend
uv run python -m src.index_documents
```

### Indexação do Google Drive

```bash
cd backend
uv run python -m src.index_documents --drive
```

### Testes automatizados

```bash
cd backend
uv run pytest -q
```

### Docker Compose

```bash
cp -n backend/.env.example backend/.test.env
docker compose build
docker compose run --rm backend /app/.venv/bin/python -m src.index_documents --drive
docker compose up -d
```
