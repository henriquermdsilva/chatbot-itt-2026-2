Fork do repositório [github.com/chraujo/chatbot-itt-2026-1](https://github.com/chraujo/chatbot-itt-2026-1). Aqui, são documentados os avanços obtidos no desenvolvimento do chatbot para o Instituto Tadao Takahashi (ITT) durante o segundo semestre de 2026.

Guilherme de Godoi Monteiro - 237031
    
Henrique Ribeiro Medeiros da Silva - 243172

Renilson Conceição de Luna Júnior - 247358

Vitor Ferreira dos Santos de Lacerda - 231524

## Como rodar

Requer Python 3.12, [uv](https://docs.astral.sh/uv/) e Node.js.

1. Em `backend/`, copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY` e `GOOGLE_DRIVE_FOLDER_ID`
2. Salve o JSON da Service Account em `backend/credentials/service_account.json`
3. Em `frontend/`, copie `.env.example` para `.env`
4. Na raiz: `npm install` e `npm run dev`. Ctrl+C encerra os dois.

**Separadamente:**
- Backend, em `backend/`: `uv sync` e `uv run uvicorn src.api:app --reload --port 8000`
- Frontend, em `frontend/`: `npm install` e `npm run dev`
