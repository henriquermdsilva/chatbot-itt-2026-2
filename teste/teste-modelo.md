# Teste de Modelo – Instituto (ONG)

## 1. Conjunto de Perguntas

A seguir estão **10 perguntas genéricas** que podem ser feitas ao modelo usando os documentos que compõem o conhecimento da ONG. Não há necessidade de preencher gabaritos ou indicar documentos‑fonte neste momento – essas informações podem ser adicionadas posteriormente.

| # | Pergunta |
|---|-----------|
| 1 | Qual é o nome completo da ONG? |
| 2 | Qual é a missão principal da ONG? |
| 3 | Em que ano a ONG foi fundada? |
| 4 | Quem fundou a ONG? |
| 5 | Em quais regiões geográficas a ONG atua? |
| 6 | Qual é o principal programa de educação ambiental da ONG? |
| 7 | Quantos projetos ativos a ONG tem atualmente? |
| 8 | Qual parceria internacional a ONG mantém para pesquisa de biodiversidade? |
| 9 | Como a ONG financia suas atividades? |
|10| Qual foi o maior desafio enfrentado pela ONG nos últimos cinco anos? |

---

## 2. Script de Avaliação

O script abaixo (`run_evaluation.py`) lê as perguntas acima, as envia ao modelo **Gemini** (ou ao modelo configurado localmente) e grava as respostas em um CSV chamado `baseline.csv`. Como ainda não há gabaritos nem fontes, o CSV contém apenas a pergunta, a resposta do modelo e um identificador.

```python
"""run_evaluation.py

Script de avaliação automática para uma ONG.

Requisitos:
- python>=3.8
- google-generativeai (ou biblioteca equivalente)
- pandas

Uso:
    python run_evaluation.py
"""

import csv
import os
from pathlib import Path

# Import da biblioteca Gemini. Ajuste se usar outro modelo.
try:
    import google.generativeai as genai
except ImportError:
    raise RuntimeError("Instale a biblioteca google-generativeai: pip install google-generativeai")

# Configuração da API – a chave deve estar na variável de ambiente GEMINI_API_KEY
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("Defina a variável de ambiente GEMINI_API_KEY com sua chave de API Gemini")

genai.configure(api_key=api_key)

# Modelo a ser usado (pode ser alterado para outro modelo local, se necessário)
model = genai.GenerativeModel('gemini-1.5-flash')

# Lista de perguntas (id, texto)
QUESTIONS = [
    (1, "Qual é o nome completo da ONG?"),
    (2, "Qual é a missão principal da ONG?"),
    (3, "Em que ano a ONG foi fundada?"),
    (4, "Quem fundou a ONG?"),
    (5, "Em quais regiões geográficas a ONG atua?"),
    (6, "Qual é o principal programa de educação ambiental da ONG?"),
    (7, "Quantos projetos ativos a ONG tem atualmente?"),
    (8, "Qual parceria internacional a ONG mantém para pesquisa de biodiversidade?"),
    (9, "Como a ONG financia suas atividades?"),
    (10, "Qual foi o maior desafio enfrentado pela ONG nos últimos cinco anos?"),
]

def ask_gemini(question: str) -> str:
    """Envia a pergunta ao modelo Gemini e devolve a resposta em texto bruto."""
    response = model.generate_content(question)
    return str(response.text).strip()

def main():
    output_path = Path("baseline.csv")
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id", "pergunta", "resposta_modelo"])  # colunas básicas
        for qid, qtext in QUESTIONS:
            print(f"Consultando modelo para a pergunta {qid} …")
            modelo_resp = ask_gemini(qtext)
            writer.writerow([qid, qtext, modelo_resp])
    print(f"Avaliação concluída. Resultados gravados em {output_path.resolve()}")

if __name__ == "__main__":
    main()
```

### Como Executar
1. Instale as dependências:
   ```bash
   pip install google-generativeai pandas
   ```
2. Defina a chave de API Gemini (substitua `YOUR_KEY` pelo seu token):
   ```bash
   export GEMINI_API_KEY=YOUR_KEY
   ```
3. Rode o script:
   ```bash
   python run_evaluation.py
   ```
   O arquivo `baseline.csv` será criado na raiz do projeto contendo as respostas do modelo.

---

## 3. Linha de Base

O CSV `baseline.csv` gerado na primeira execução representa a **linha de base** da performance do modelo ao responder estas perguntas sobre a ONG. Quando desejar, você pode acrescentar gabaritos e documentos‑fonte ao documento e ao CSV para análises de acurácia.

---

*Documento gerado automaticamente por Antigravity.*
