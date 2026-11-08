Documentação da API Backend - Instituto Tadao Takahashi (ITT) Chatbot

1. Visão Geral

A API backend do ITT Chatbot é uma aplicação construída com FastAPI que oferece capacidades de processamento de linguagem natural através de um assistente inteligente baseado em RAG (Retrieval-Augmented Generation). O sistema utiliza LangGraph para orquestração de fluxos de trabalho e LangChain para integração com modelos de IA.

O propósito principal é responder perguntas dos usuários sobre o estatuto e políticas do Instituto Tadao Takahashi, triando automaticamente as solicitações e respondendo com base em documentos indexados.

2. Arquitetura

2.1 Estrutura de Pastas

O projeto segue uma arquitetura modular e bem organizada:

src/
├── api.py                    # Aplicação FastAPI principal
├── dependencies.py           # Injeção de dependências
├── schemas.py               # Modelos Pydantic para validação
├── config/
│   ├── __init__.py
│   └── settings.py          # Configurações baseadas em ambiente
├── routers/
│   ├── __init__.py
│   └── chat.py              # Endpoints de conversação
└── services/
    ├── __init__.py
    ├── chains.py            # Definição de chains LangChain
    ├── graph.py             # Orquestração com LangGraph
    └── vectorDB.py          # Gerenciamento de vetores FAISS

2.2 Fluxo Arquitetural

Requisição do Cliente
    ↓
Router (chat.py)
    ↓
Dependency Injection (get_graph)
    ↓
ITTGraph (state machine)
    ├─ Triage Node (decisão)
    └─ Auto-Resolve Node (RAG)
        ├─ VectorDB Query
        └─ RAG Chain Response
    ↓
Response (JSON)

3. Componentes Principais

3.1 API (api.py)

Responsabilidade: Configuração central da aplicação FastAPI.

Características:
- Aplicação FastAPI com metadados completos (título, versão, descrição)
- Middleware CORS configurado com URL do frontend
- Importação e registro de routers
- Documentação interativa disponível em /docs e /redoc

Endpoint Raiz:
GET /
Retorna informações sobre a API

3.2 Configurações (config/settings.py)

Responsabilidade: Gerenciar todas as configurações da aplicação.

Variáveis de Ambiente:
FRONTEND_URL: URL do frontend para CORS (padrão: http://localhost:3000)
GOOGLE_API_KEY: Chave de API do Google para acesso ao Gemini
LLM_MODEL: Modelo de IA a utilizar (padrão: gemini-2.5-flash)
LLM_TEMPERATURE: Temperatura do modelo para controle de criatividade (padrão: 0.3)
FAISS_INDEX_PATH: Caminho para o índice FAISS (padrão: faiss_index)

Implementação:
Utiliza Pydantic BaseSettings para validação e carregamento automático de variáveis de ambiente através do arquivo .env.
Suporta valores padrão e validação de tipos.

3.3 Schemas de Validação (schemas.py)

Responsabilidade: Definir modelos Pydantic para validação de requisições e respostas.

Modelos Principais:

QueryRequest:
- message (str, obrigatório): Pergunta do usuário com validação de comprimento (1-5000 caracteres)

QueryResponse:
- response (str): Resposta gerada pela IA
- source_documents (List[str]): Lista de documentos utilizados como contexto

ErrorResponse:
- detail (str): Descrição do erro
- error_code (str, opcional): Código de erro para rastreamento

3.4 Injeção de Dependências (dependencies.py)

Responsabilidade: Centralizar a criação e gerenciamento de instâncias com caching.

Dependências Principais:

get_settings():
- Retorna instância única e cacheada de Settings
- Utilizado em toda a aplicação para acessar configurações

get_vector_db(settings):
- Cria instância de VectorDB com configurações injetadas
- Responsável pela busca em vetores

get_graph(settings, vector_db):
- Cria instância de ITTGraph com todas as dependências
- Gerencia o fluxo de processamento da pergunta

Padrão: Dependency Injection com caching LRU para eficiência.

3.5 Routers (routers/chat.py)

Responsabilidade: Definir os endpoints da API.

Endpoints:

POST /chat/query
Descricao: Processa uma pergunta do usuário através do pipeline RAG
Parametros:
  - Corpo da requisição: QueryRequest
  - graph: ITTGraph (injetado via Depends)
Resposta: QueryResponse com resposta e documentos fonte
Códigos HTTP:
  - 200: Sucesso
  - 422: Erro de validação
  - 500: Erro interno do servidor

Processamento:
1. Recebe QueryRequest validado
2. Passa pergunta para ITTGraph.invoke()
3. Retorna QueryResponse com response e source_documents

3.6 Chains (services/chains.py)

Responsabilidade: Definir e configurar as chains de LangChain para processamento.

Chains Implementadas:

1. Triage Chain
   Função: get_triage_chain(settings)
   Responsabilidade: Classificar a pergunta em dois tipos
   Saída: TriageOutput (Pydantic model)
   
   Formato esperado do LLM:
   {
     "decisao": "AUTO_RESOLVER" | "PEDIR_INFO",
     "campos_faltantes": ["campo1", "campo2"]
   }
   
   Decisões:
   - AUTO_RESOLVER: Pergunta clara, pode ser respondida com contexto
   - PEDIR_INFO: Pergunta vaga, requer esclarecimento do usuário

2. RAG Chain
   Função: get_rag_chain(settings)
   Responsabilidade: Gerar resposta baseada em contexto
   Entrada: {input: pergunta, context: documentos}
   Saída: texto em linguagem natural
   
   O prompt do RAG está em português e fornece instruções detalhadas ao modelo sobre como responder
   levando em consideração o contexto fornecido.

3.7 Graph (services/graph.py)

Responsabilidade: Orquestrar o fluxo de processamento através de uma máquina de estados.

Classe: ITTGraph

Estrutura:
- Recebe Settings e VectorDB na inicialização
- Carrega chains de triage e RAG
- Constrói grafo com StateGraph de LangGraph

Estado (AgentState):
question (str): A pergunta do usuário
triage (dict): Resultado da triagem
answer (str): Resposta final
citations (List[dict]): Documentos utilizados
rag_success (bool): Se a RAG foi bem-sucedida
final_action (str): Ação executada

Nós do Grafo:

1. Nó Triage (_node_triage)
   Entrada: question
   Processamento: Invoca triage_chain para classificar a pergunta
   Saída: triage dict com decisao e campos_faltantes
   
2. Nó Auto-Resolve (_node_auto_resolve)
   Entrada: question, resultado de triage
   Processamento:
     a. Busca documentos relacionados via VectorDB.query()
     b. Se documentos encontrados, invoca rag_chain
     c. Valida resposta (verifica se não é "Não sei")
   Saída: answer e citations
   
3. Nó Request Info (_node_request_info)
   Entrada: campos_faltantes da triagem
   Processamento: Formata mensagem pedindo ao usuário que forneça informações
   Saída: answer em português

Roteamento Condicional:

Após triage, o grafo segue um dos caminhos:
- AUTO_RESOLVER -> nó auto_resolve -> END
- PEDIR_INFO -> nó request_info -> END

Método invoke(question):
Executa o grafo completo e retorna resposta formatada

3.8 VectorDB (services/vectorDB.py)

Responsabilidade: Gerenciar indexação e busca em vetores FAISS.

Métodos Principais:

query(message: str) -> List[Document]
Busca documentos relacionados à pergunta
Parâmetros de busca:
- similarity_score_threshold: 0.3 (threshold mínimo de relevância)
- k: 4 (número de documentos a retornar)

create_faiss_index(parent_folder: str)
Cria índice FAISS a partir de PDFs em uma pasta
Processamento:
1. Carrega PDFs usando PyMuPDFLoader
2. Divide documentos em chunks (1000 caracteres com 200 de sobreposição)
3. Gera embeddings usando Google Generative AI
4. Salva índice em disco

4. Fluxo de Requisição

Passo 1: Cliente envia requisição POST /chat/query

{
  "message": "Como solicitar certificado?"
}

Passo 2: Router (chat.py) valida a requisição

- QueryRequest é validado contra o schema
- FastAPI retorna erro 422 se inválido

Passo 3: Dependency Injection (get_graph)

- Settings é carregado (cacheado se já existe)
- VectorDB é criado com Settings
- ITTGraph é criado com Settings e VectorDB

Passo 4: ITTGraph.invoke(message)

a) Node Triage:
   - Mensagem é enviada para triage_chain
   - LLM retorna JSON com decisão
   - JSON é parseado em TriageOutput object
   - object.model_dump() converte para dict
   
b) Roteamento:
   - Se AUTO_RESOLVER: próximo = nó auto_resolve
   - Se PEDIR_INFO: próximo = nó request_info

c) Node Auto-Resolve (se AUTO_RESOLVER):
   - Busca documentos via VectorDB.query(message)
   - Passa documentos + pergunta para rag_chain
   - RAG Chain formata prompt e chama LLM
   - LLM retorna resposta em texto natural
   - Resposta é validada
   
d) Node Request-Info (se PEDIR_INFO):
   - Formata mensagem pedindo esclarecimento
   - Inclui lista de campos faltantes

Passo 5: Formatação da Resposta

{
  "response": "resposta do assistente",
  "source_documents": ["documento1", "documento2", ...]
}

Passo 6: Cliente recebe JSON validado

- FastAPI serializa resposta como QueryResponse
- Retorna HTTP 200 com JSON

5. Validação de Dados

5.1 Validação de Entrada

QueryRequest:
- message: requerido, 1-5000 caracteres, sem espaços em branco apenas

5.2 Validação de Saída

QueryResponse:
- response: string não vazia
- source_documents: lista de strings

FastAPI valida automaticamente contra os modelos Pydantic.

6. Tratamento de Erros

6.1 Erros de Validação (422)

Quando a requisição não passa na validação:
{
  "detail": [
    {
      "type": "string_too_long",
      "loc": ["body", "message"],
      "msg": "String should have at most 5000 characters",
      "input": "..."
    }
  ]
}

6.2 Erros de Processamento (500)

Quando ocorre erro durante processamento:
{
  "detail": "Error processing query: <mensagem de erro>"
}

6.3 Tipos de Exceção

HTTPException: Levantada para erros conhecidos durante processamento
Exception geral: Capturada e convertida em erro 500

7. Configuração de Ambiente

7.1 Arquivo .env

Exemplo de configuração:

FRONTEND_URL=http://localhost:3000
GOOGLE_API_KEY=sua_chave_api_aqui
LLM_MODEL=gemini-2.5-flash
LLM_TEMPERATURE=0.3
FAISS_INDEX_PATH=faiss_index

7.2 Variáveis Obrigatórias

GOOGLE_API_KEY: Deve estar preenchida para funcionamento da API

7.3 Variáveis Opcionais

As demais possuem valores padrão e podem ser omitidas.

8. Dependências Externas

8.1 Pacotes Python Principais

fastapi: Framework web assíncrono
uvicorn: Servidor ASGI
pydantic: Validação de dados
pydantic-settings: Gerenciamento de configurações
langchain: Orquestração de chains de IA
langchain-google-genai: Integração com Gemini
langgraph: Orquestração de máquinas de estado
faiss-cpu: Busca vetorial em CPU
langchain-community: Ferramentas comunitárias do LangChain

8.2 Versões Recomendadas

Ver arquivo pyproject.toml para versões exatas.

9. Execução

9.1 Desenvolvimento

python -m uvicorn src.api:app --reload --host 0.0.0.0 --port 8000

9.2 Produção

gunicorn src.api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

9.3 Docker

docker build -t itt-chatbot-api .
docker run -p 8000:8000 -e GOOGLE_API_KEY=sua_chave itt-chatbot-api

10. Endpoints de Administração

GET /
Retorna informações gerais da API

GET /docs
Documentação interativa com Swagger UI

GET /redoc
Documentação com ReDoc

GET /openapi.json
Schema OpenAPI em JSON

11. Performance e Escalabilidade

11.1 Caching

- Settings: cacheado com @lru_cache()
- VectorDB: reutiliza conexão com FAISS
- ITTGraph: instância nova por requisição (necessário para thread-safety)

11.2 Índice FAISS

- Carregado sob demanda via VectorDB
- Mantém-se em memória durante a execução
- Tamanho limitado pela RAM disponível

11.3 Requisições Concorrentes

FastAPI/Uvicorn suporta múltiplas workers em produção.
VectorDB.query() é thread-safe.
ITTGraph é instanciado por requisição para segurança.

12. Segurança

12.1 CORS

Apenas requisições de FRONTEND_URL são aceitas.
Deve ser configurado corretamente em produção.

12.2 Validação de Entrada

Todos os inputs são validados com Pydantic antes de processamento.
Rejeita requests malformadas automaticamente.

12.3 Chaves de API

GOOGLE_API_KEY deve ser protegida e nunca commitada no repositório.
Usar arquivo .env ou variáveis de ambiente.

13. Monitoramento e Logging

13.1 Logs Estruturados

logging é configurado em cada router para rastrear:
- Requisições recebidas
- Processamento bem-sucedido
- Erros durante execução

13.2 Rastreamento de Usuários

O e-mail validado no login é registrado em logs para correlação de requisições.

14. Exemplos de Uso

14.1 Request Simples

curl -X POST "http://localhost:8000/chat/query" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quais são os horários de funcionamento?"
  }'

14.2 Request com Python

import requests

response = requests.post(
    "http://localhost:8000/chat/query",
    json={
        "message": "Como faço para renovar minha matrícula?"
    }
)

print(response.json())

14.3 Resposta Esperada

{
  "response": "Para renovar sua matrícula no ITT, você deve...",
  "source_documents": [
    "Capítulo 3, Seção 2 do Estatuto do ITT...",
    "Procedimentos Administrativos, Página 15..."
  ]
}

15. Manutenção

15.1 Atualizar Índice FAISS

Quando novos documentos são adicionados, o índice deve ser recriado:

from src.services.vectorDB import VectorDB
from src.config import Settings

settings = Settings()
db = VectorDB(settings)
db.create_faiss_index("documentos_novos")

15.2 Limpar Cache

Reinicie a aplicação para limpar cache de Settings e embeddings.

15.3 Monitoramento

Verifique logs para:
- Taxa de erro
- Tempo de resposta
- Padrões de uso

16. Troubleshooting

16.1 Erro: "O índice FAISS não foi encontrado"

Solução: Execute create_faiss_index() com pasta de PDFs

16.2 Erro: "GOOGLE_API_KEY não configurada"

Solução: Configure GOOGLE_API_KEY no arquivo .env

16.3 Resposta vazia

Verifique:
- Se FAISS_INDEX_PATH aponta para índice correto
- Se documentos no índice cobrem o tópico da pergunta
- Se LLM_TEMPERATURE é apropriada (0-1)

16.4 Lentidão

Possíveis causas:
- Índice FAISS muito grande (limite de RAM)
- Muitas requisições simultâneas (adicione workers)
- Rede lenta com Google API

17. Conclusão

A API backend do ITT Chatbot implementa uma solução robusta e escalável para processamento de perguntas em linguagem natural, combinando boas práticas de engenharia de software com capacidades modernas de inteligência artificial. A arquitetura modular permite fácil manutenção e extensão futura.
