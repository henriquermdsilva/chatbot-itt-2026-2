# Setup da API — OpenWebUI da Unicamp

Para usar a pasta compartilhada do projeto, siga o [guia do chatbot com Google Drive](../RUN_CHATBOT.md).
As instruções abaixo descrevem o uso com PDFs locais.

O chatbot usa `gemma3:12b` para triagem e respostas e `nomic-embed-text:latest`
para embeddings em `https://llm.ic.unicamp.br`. A mesma chave autentica as duas
chamadas. Não é necessário ter GPU local, instalar Ollama ou obter chave Gemini.

Fluxo: navegador → FastAPI local → busca nos PDFs com FAISS → modelo remoto.
O texto dos PDFs é enviado à Unicamp para calcular embeddings; os trechos
recuperados são enviados para gerar a resposta. O índice fica no computador local.
As últimas 12 mensagens da conversa são enviadas para contextualizar perguntas
de continuação. O histórico é separado por usuário no navegador e não é mantido
em memória compartilhada no backend. As respostas continuam baseadas nos documentos.

## 1. Instalar o backend

Use **Python 3.12** (3.11 também é suportado). As versões de LangChain e NumPy
estão fixadas para compatibilidade com o projeto. Python 3.13 não é suportado
por este conjunto de dependências.

A partir da raiz do repositório:

```powershell
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Alternativa com [uv](https://docs.astral.sh/uv/), também dentro de `backend`:

```powershell
uv sync --locked --python 3.12
```

No Linux/macOS, use `.venv/bin/python` nos comandos abaixo.

## 2. Configurar a chave e os documentos

```powershell
Copy-Item .env.example .test.env
```

Se `.test.env` já existir, edite-o sem sobrescrever sua chave. Exemplo:

```dotenv
OPENWEBUI_API_KEY=sua-chave-do-openwebui
OPENWEBUI_BASE_URL=https://llm.ic.unicamp.br
LLM_PROVIDER=openwebui
LLM_MODEL=gemma3:12b
OPENWEBUI_EMBEDDING_MODEL=nomic-embed-text:latest
LLM_TIMEOUT=120
RETRIEVAL_LANGUAGE=
local_data_path="C:/caminho/para/documentos"
FAISS_INDEX_PATH=faiss_index_openwebui
GOOGLE_DRIVE_FOLDER_ID=
AUTH_DEV_MODE=true
```

`local_data_path` aceita uma pasta com PDFs/Excel `.xlsx` ou um único arquivo desses formatos.
Deixe `GOOGLE_DRIVE_FOLDER_ID` vazio, como acima, para desativar a sincronização
do Drive no modo local.
Use barras `/` nos caminhos Windows. A busca em pastas não é recursiva.
Os PDFs precisam conter texto selecionável; este projeto não executa OCR.

Para PDFs em inglês, configure `RETRIEVAL_LANGUAGE=English`. A triagem traduz
somente a consulta de busca; a pergunta original é usada para gerar a resposta
em português. Isso ajuda a recuperação com Nomic quando pergunta e documento
estão em idiomas diferentes. Deixe vazio para pesquisar no idioma da pergunta.
Não é necessário reindexar ao mudar essa opção.

O nome antigo `api_key=...` também é aceito. Não defina a chave com os dois nomes.
A precedência é: variáveis do processo > `backend/.env` > `backend/.test.env`.
Os arquivos de configuração são localizados pela pasta do backend. Caminhos
relativos dos documentos e índice usam o diretório atual; execute estes comandos
dentro de `backend`.

Crie a chave em **OpenWebUI → Configurações → Conta → Chaves de API**.
Sua conta precisa acessar os modelos e as rotas `/api/chat/completions` e
`/ollama/api/embed`. Mantenha a chave somente no backend; nunca use uma variável
`VITE_` para ela. `.test.env`, `.env` e o índice padrão são ignorados pelo Git.

## 3. Indexar os PDFs

```powershell
.venv/Scripts/python.exe -u -m src.index_documents
```

Ou forneça um caminho explicitamente:

```powershell
.venv/Scripts/python.exe -u -m src.index_documents "C:/documentos/livro.pdf"
```

A indexação de um PDF grande pode levar alguns minutos. Aguarde `Indice salvo em:`.
Reexecute ao alterar os PDFs ou trocar o modelo de embeddings. Não reutilize
índices gerados com Gemini: os vetores são incompatíveis com Nomic.
Carregue somente índices FAISS locais e de confiança.

## 4. Iniciar e testar a API

```powershell
.venv/Scripts/python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

As rotas exigem login. Com `AUTH_DEV_MODE=true`, use o token `dev-token`: abra
http://localhost:8000/docs, clique em **Authorize** e use `POST /chat/query`, ou execute em outro terminal:

```powershell
$body = @{ message = "Qual é o assunto principal do documento?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/chat/query -Method Post -Headers @{ Authorization = "Bearer dev-token" } -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

O retorno contém `response` e `source_documents`, com arquivo, página e trecho
recuperado. A página é contada a partir de 1 no PDF e pode diferir da numeração
impressa. O limite é de 5 perguntas por minuto por IP.

## 5. Iniciar a interface

Em outro terminal, a partir da raiz do repositório:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --host localhost
```

Abra http://localhost:5173. O botão existente **Skip Login (Dev)** permite testar
em `localhost`. A variável `VITE_API_URL` aponta para `http://localhost:8000`.
Para outro ambiente, ajuste-a antes do build e configure o CORS do backend
com `FRONTEND_URL` / `FRONTEND_DEV_URL`.

**Atualizar Docs** reindexa a origem configurada. Sem `GOOGLE_DRIVE_FOLDER_ID`,
usa os PDFs locais. Para Drive, configure essa variável e as credenciais da conta
de serviço em `GOOGLE_CREDENTIALS_PATH`. Drive não é necessário para PDFs locais.
O comando `python -m src.index_documents --drive` também sincroniza o Drive,
incluindo PDFs, Google Docs e Excel `.xlsx` em subpastas. Consulte o [guia de acesso e execução](../RUN_CHATBOT.md).
Reindexar é uma operação longa; use apenas quando os documentos mudarem.

## Testes e diagnóstico

```powershell
uv run pytest -q
```

Os testes automatizados simulam a API. O teste via `/chat/query` acima faz
chamadas reais de triagem, embeddings e resposta.

| Problema | Verificação |
| --- | --- |
| HTTP 401/403 | Chave válida e acesso aos modelos e às duas rotas do OpenWebUI. |
| Modelo inexistente | Use o ID exato retornado por `GET /api/models` com a mesma chave. |
| Índice não encontrado | Execute a indexação e confira `FAISS_INDEX_PATH`. |
| Dimensão de vetores incompatível | Recrie o índice após trocar o modelo de embeddings. |
| Tempo limite | Servidor ocupado ou carregando o modelo; ajuste `LLM_TIMEOUT`. |
| Nenhum PDF com texto | Confira o caminho e se o PDF precisa de OCR. |
| Busca ruim em outro idioma | Configure `RETRIEVAL_LANGUAGE` com o idioma dos documentos. |
| Interface usa outro servidor | Confira `VITE_API_URL` e reinicie o Vite. |

O fluxo legado Gemini continua disponível com `LLM_PROVIDER=google`,
`GOOGLE_API_KEY`, `LLM_MODEL=gemini-2.5-flash` e um `FAISS_INDEX_PATH` separado.
O setup OpenWebUI não depende do modelo customizado `chatbot-itt` do servidor:
o backend faz o RAG sobre os PDFs configurados localmente.

Referências: [OpenWebUI](https://docs.openwebui.com/reference/api-endpoints/),
[Ollama embeddings](https://docs.ollama.com/api/embed) e
[prefixos de busca do Nomic](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5).
