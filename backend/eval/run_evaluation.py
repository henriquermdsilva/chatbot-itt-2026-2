"""
Roda as perguntas de avaliação pelo fluxo do chatbot e salva as respostas em CSV.

Uso, dentro de backend/ (precisa só de GOOGLE_API_KEY no .env):
    uv run python -m eval.run_evaluation --docs eval_docs
"""
import argparse
import csv
import io
import os
import sys
import time
from pathlib import Path

from src.config import Settings
from src.dependencies import get_graph, get_vector_db
from src.services import VectorDB

INPUT_COLUMNS = ["id", "question", "expected_answer", "expected_source", "has_answer"]
OUTPUT_COLUMNS = INPUT_COLUMNS + ["model", "model_answer", "returned_sources", "time_s", "error"]


def read_questions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in INPUT_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"Colunas faltando em {path}: {', '.join(missing)}")
        return list(reader)


def read_results(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def save_results(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def prepare_index(vector_db: VectorDB, settings: Settings, docs: Path, reindex: bool) -> None:
    if os.path.exists(settings.FAISS_INDEX_PATH) and not reindex:
        print(f"Usando o índice existente em {settings.FAISS_INDEX_PATH} (use --reindex para recriar)")
        return
    if not docs.is_dir():
        sys.exit(f"Pasta de PDFs não encontrada: {docs}")
    print(f"Indexando os PDFs de {docs}...")
    vector_db.create_faiss_index(str(docs))
    if not os.path.exists(settings.FAISS_INDEX_PATH):
        sys.exit("Nenhum PDF foi indexado. Confira a pasta indicada em --docs.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Roda o conjunto de avaliação pelo fluxo do chatbot.")
    parser.add_argument("--questions", type=Path, default=Path("eval/questions.csv"), help="CSV com as perguntas")
    parser.add_argument("--docs", type=Path, default=Path("eval_docs"), help="Pasta com os PDFs a indexar")
    parser.add_argument("--index", default="faiss_index_eval", help="Pasta do índice FAISS da avaliação")
    parser.add_argument("--reindex", action="store_true", help="Recria o índice mesmo que ele já exista")
    parser.add_argument("--model", help="Modelo do Gemini (padrão: LLM_MODEL do .env ou gemini-2.5-flash)")
    parser.add_argument("--output", type=Path, help="CSV de saída (padrão: eval/results/<modelo>.csv)")
    parser.add_argument("--pause", type=float, default=10.0, help="Segundos entre perguntas, para não estourar a cota")
    parser.add_argument("--only-errors", action="store_true",
                        help="Repete só as perguntas com erro no CSV de saída, mantendo as demais respostas")
    parser.add_argument("--overwrite", action="store_true", help="Substitui o CSV de saída, se ele já existir")
    args = parser.parse_args()

    overrides = {"FAISS_INDEX_PATH": args.index}
    if args.model:
        overrides["LLM_MODEL"] = args.model
    settings = Settings(**overrides)
    if not settings.GOOGLE_API_KEY:
        sys.exit("GOOGLE_API_KEY vazia. Crie backend/.env a partir do .env.example.")

    output = args.output or Path("eval/results") / f"{settings.LLM_MODEL}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not (args.only_errors or args.overwrite):
        sys.exit(f"{output} já existe. Use --only-errors para completar, --overwrite para substituir "
                 "ou --output para gravar em outro arquivo.")

    all_questions = read_questions(args.questions)
    results = read_results(output) if args.only_errors else {}
    if args.only_errors:
        if not results:
            sys.exit(f"Nenhum resultado anterior em {output}. Rode primeiro sem --only-errors.")
        questions = [q for q in all_questions if q["id"] not in results or results[q["id"]]["error"]]
        if not questions:
            sys.exit(f"Nenhuma pergunta com erro em {output}.")
    else:
        questions = all_questions

    vector_db = get_vector_db(settings)
    prepare_index(vector_db, settings, args.docs, args.reindex)
    graph = get_graph(settings, vector_db)

    for i, row in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {row['question']}")
        start = time.perf_counter()
        answer, sources, error = "", "", ""
        try:
            result = graph.invoke(row["question"])
            answer = result["response"]
            sources = "; ".join(
                f"{d['source']} p.{d['page']}" if d.get("page") else d["source"]
                for d in result["source_documents"]
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"    erro: {error}")

        results[row["id"]] = {
            **{c: row[c] for c in INPUT_COLUMNS},
            "model": settings.LLM_MODEL,
            "model_answer": answer,
            "returned_sources": sources,
            "time_s": f"{time.perf_counter() - start:.1f}",
            "error": error,
        }
        save_results(output, [results[q["id"]] for q in all_questions if q["id"] in results])

        if i < len(questions):
            time.sleep(args.pause)

    error_count = sum(1 for r in results.values() if r["error"])
    print(f"Resultados salvos em {output.resolve()} ({error_count} com erro)")


if __name__ == "__main__":
    main()
