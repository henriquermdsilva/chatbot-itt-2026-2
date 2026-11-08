# Executar o chatbot com documentos do Google Drive

Este guia usa a API da Unicamp para o modelo e os embeddings, com documentos
da pasta do projeto no Drive (peça o ID a quem administra o projeto).
Execute os comandos a partir deste repositório, na branch `guilhermegodoi/test_api`.
Não é necessário publicar a aplicação para testar localmente.

## 1. Instalar o backend

Requisitos: Python 3.12 (ou 3.11), Node.js/npm e uma chave da API da Unicamp
com acesso a `gemma3:12b` e `nomic-embed-text:latest`.

```powershell
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Se o ambiente `.venv` já estiver instalado, reutilize-o. No Linux/macOS,
crie-o com `python3.12 -m venv .venv` e use `.venv/bin/python` nos próximos comandos.

## 2. Dar acesso de leitura ao Drive

1. No Google Cloud, habilite a **Google Drive API** em um projeto.
2. Crie uma **conta de serviço**, gere uma chave JSON e salve-a como
   `backend/credentials/service_account.json` (crie a pasta `credentials`).
3. Abra a pasta do projeto no Drive e compartilhe-a como **Leitor** com o
   endereço `client_email` que está nesse JSON. A conta precisa conseguir
   ler e baixar os documentos, inclusive os das subpastas.

O login da interface e a conexão do Drive no ChatGPT não autenticam este backend.
O backend usa a conta de serviço com o escopo `drive.readonly`.
O diretório `credentials/` já é ignorado pelo Git; mantenha a chave somente nele
ou em uma variável de ambiente do backend.

## 3. Configurar o backend

Se ainda não houver `backend/.test.env`, copie o exemplo, dentro de `backend`:

```powershell
Copy-Item .env.example .test.env
```

Se o arquivo já existir, edite-o sem sobrescrever sua chave. Configure:

```dotenv
OPENWEBUI_API_KEY=sua-chave-da-unicamp
OPENWEBUI_BASE_URL=https://llm.ic.unicamp.br
LLM_PROVIDER=openwebui
LLM_MODEL=gemma3:12b
OPENWEBUI_EMBEDDING_MODEL=nomic-embed-text:latest
GOOGLE_DRIVE_FOLDER_ID=id-da-pasta-do-projeto
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
FAISS_INDEX_PATH=faiss_index_openwebui
RETRIEVAL_LANGUAGE=
```

O nome antigo `api_key` também funciona: mantenha apenas um nome para a chave.
`GOOGLE_DRIVE_FOLDER_ID` recebe o ID, não a URL inteira. Execute os comandos
dentro de `backend` para resolver os caminhos relativos deste exemplo.

Alternativa ao arquivo JSON: defina `GOOGLE_CREDENTIALS_JSON` com o JSON completo
em uma linha no ambiente do processo ou entre aspas simples no `.test.env`.
Se o arquivo indicado por `GOOGLE_CREDENTIALS_PATH` existir, ele tem preferência.
Variáveis do processo prevalecem sobre `backend/.env`, que prevalece sobre
`backend/.test.env`. Não coloque credenciais em variáveis `VITE_` do frontend.

## 4. Baixar e indexar os documentos

> **Atenção:** use `--drive` e **Atualizar Docs** apenas com pastas autorizadas pelo ITT.
> Todo o conteúdo, inclusive dados pessoais, é enviado ao servidor de embeddings
> (`OPENWEBUI_BASE_URL`), fica no índice e pode aparecer para qualquer pessoa logada,
> pois não há permissão por perfil. Não compartilhe o índice nem o cache de embeddings.

Ainda em `backend`:

```powershell
.venv/Scripts/python.exe -u -m src.index_documents --drive
```

Aguarde `Indice salvo em:` antes de iniciar uma conversa. O comando percorre
a pasta e suas subpastas, baixa PDFs e arquivos Excel `.xlsx`, e exporta Google Docs como PDF. A listagem
continua além dos primeiros 100 itens. Outros formatos e atalhos são ignorados;
converta arquivos Word em Google Docs ou PDF antes de indexar. As abas do Excel são
lidas com os valores salvos no arquivo, preservando os endereços das células.
Fórmulas não são recalculadas; salve os resultados no Excel antes de sincronizar.
Arquivos `.xls` e Google Sheets nativos ainda não são suportados. PDFs digitalizados
precisam de OCR prévio. A exportação de Google Docs tem limite de 10 MB por arquivo.

Os downloads usam uma pasta temporária removida ao final. O índice FAISS fica
em `FAISS_INDEX_PATH`. Os nomes das fontes incluem o ID do Drive para distinguir
documentos com títulos iguais. O texto é enviado à Unicamp para embeddings e
os trechos recuperados são enviados para gerar as respostas.

Se a pasta estiver vazia ou um download falhar, a sincronização falha sem
substituir o índice anterior. Reexecute ao alterar os documentos ou o modelo
de embeddings. Use somente índices locais de confiança.

Os embeddings ficam em cache em `FAISS_INDEX_PATH/embeddings_cache`: só os trechos
novos vão ao servidor, e uma execução interrompida retoma de onde parou. Trate
esse cache como o próprio índice. Ele não é limpo quando um documento sai da pasta;
apague a pasta para limpá-lo.

## 5. Iniciar o backend e a interface

No terminal do backend:

```powershell
.venv/Scripts/python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Com Drive configurado e chave do modelo disponível, o backend também sincroniza
ao iniciar, em segundo plano. Aguarde `Auto-Sync: Memória recriada com sucesso!`
antes de usar a base atualizada. Falhas aparecem no terminal; um índice anterior
pode continuar respondendo com os documentos da última indexação bem-sucedida.
Para reutilizar o índice ao reiniciar, configure `SYNC_ON_STARTUP=false`;
o botão **Atualizar Docs** e o comando `--drive` continuam disponíveis.

Em outro terminal, partindo da raiz do repositório:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --host localhost
```

Se `frontend/.env` já existir, confira `VITE_API_URL=http://localhost:8000`
sem sobrescrever as outras configurações. Abra http://localhost:5173 e use
**Skip Login (Dev)**. Faça uma pergunta sobre um documento e confira as fontes.
O botão **Atualizar Docs** sincroniza novamente a pasta configurada.

O navegador envia as últimas 12 mensagens para resolver continuações como
“qual a área de interesse dela?”. O histórico fica separado por usuário no navegador.
As fontes de planilhas mostram o arquivo e a aba, sem inventar números de página.

Para testar só a API, com `AUTH_DEV_MODE=true`:

1. Abra http://localhost:8000/docs.
2. Clique em **Authorize**, digite apenas `dev-token` e confirme.
3. Em `POST /chat/query`, clique em **Try it out** e depois em **Execute**.

Com login real, só entram contas do domínio em `ALLOWED_EMAIL_DOMAIN` (padrão:
`institutotadao-itt.org.br`); as demais recebem 403. Para trocar o Client ID do Google,
defina o mesmo valor em `GOOGLE_CLIENT_ID` (backend) e `VITE_GOOGLE_CLIENT_ID` (frontend).

## 6. Alternativa: rodar tudo com Docker

Requisitos: Docker com Compose v2. As credenciais e o `backend/.test.env` ficam
fora da imagem; o Compose os injeta/monta em tempo de execução.

Na raiz do repositório:

```bash
cp -n backend/.env.example backend/.test.env   # se ainda não existir; preencha a chave
docker compose build
docker compose run --rm backend /app/.venv/bin/python -m src.index_documents --drive
docker compose up -d
```

- Interface: http://localhost:5173 (o **Skip Login (Dev)** continua disponível).
- API e Swagger: http://localhost:8000/docs.

O índice FAISS fica no volume nomeado `faiss_index` e persiste entre reinícios.
A indexação não roda no boot (`SYNC_ON_STARTUP=false`); repita o comando
`docker compose run --rm backend ...` quando os documentos mudarem, ou use o
botão **Atualizar Docs**, seguindo a atenção da seção 4. Sem índice, o chat
responde que a base ainda não foi indexada. Para parar, use `docker compose down` (mantém o índice) ou `docker compose down -v` (apaga o índice).

## Diagnóstico e testes

| Problema | Como resolver |
| --- | --- |
| Credenciais não encontradas | Confira o arquivo JSON ou `GOOGLE_CREDENTIALS_JSON`. |
| Drive retorna 403/404 | Confira o ID, habilite a Drive API e compartilhe a pasta com o `client_email` da conta de serviço. |
| Nenhum PDF, Google Doc ou Excel | Confira os formatos, o conteúdo das subpastas e o acesso da conta. Atalhos não são seguidos. |
| Nenhum PDF com texto | Use documentos com texto selecionável ou execute OCR antes. |
| Exportação excede 10 MB | Exporte o documento manualmente e coloque o PDF na pasta. |
| OpenWebUI retorna 401/403 | Confira a chave e o acesso aos modelos e às rotas de chat/embeddings. |
| Documentos em inglês | Use `RETRIEVAL_LANGUAGE=English` para traduzir a consulta de busca. |
| Falha de sincronização com respostas antigas | Corrija o erro e reindexe; o índice anterior permanece disponível. |

Dentro de `backend`, execute os testes sem chamadas externas:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Para voltar a PDFs locais, deixe `GOOGLE_DRIVE_FOLDER_ID=` vazio, configure
`local_data_path` e execute `python -m src.index_documents` sem `--drive`.
Mais detalhes no [README do backend](backend/README.md).

Referências: [downloads e exportações da Drive API](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
e [listagem paginada de arquivos](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list).
