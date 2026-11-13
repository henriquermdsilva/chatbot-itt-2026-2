"""
Roda a avaliação em vários modelos e junta os resultados num CSV comparativo.

Uso, dentro de backend/:
    uv run python -m eval.compare_models --list
    uv run python -m eval.compare_models gemma3:12b gemma3:4b llama3.1:8b
    uv run python -m eval.compare_models --only-summary gemma3:12b gemma3:4b

Cada modelo grava eval/results/<modelo>.csv pelo run_evaluation. Depois este script gera:
    eval/results/comparacao.csv  uma linha por pergunta, com a resposta e o tempo de cada modelo
    eval/results/resumo.csv      uma linha por modelo, com tempos, erros e sinais de acerto
"""
import argparse
import csv
import statistics
import subprocess
import sys
from pathlib import Path

import httpx

from src.config import Settings

RESULTS = Path("eval/results")
NOT_FOUND = "não encontrei essa informação"


def file_name(model: str) -> str:
    # Mesmo nome que o run_evaluation usa para o CSV de cada modelo.
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in model)


def list_models(settings: Settings) -> None:
    response = httpx.get(
        settings.OPENWEBUI_BASE_URL.rstrip("/") + "/api/models",
        headers={"Authorization": f"Bearer {settings.OPENWEBUI_API_KEY.get_secret_value()}"},
        timeout=30,
    )
    response.raise_for_status()
    for model in sorted(m["id"] for m in response.json().get("data", [])):
        print(model)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def summarize(models: list[str]) -> None:
    results = {}
    for model in models:
        path = RESULTS / f"{file_name(model)}.csv"
        if path.exists():
            results[model] = {row["id"]: row for row in read(path)}
        else:
            print(f"Sem resultados para {model} ({path}); ficou fora da comparação.")
    if not results:
        sys.exit("Nenhum resultado para comparar.")

    # Perguntas na ordem do primeiro modelo, com as que só aparecem nos outros no fim.
    ids = list(dict.fromkeys(i for rows in results.values() for i in rows))
    base = {i: next(rows[i] for rows in results.values() if i in rows) for i in ids}

    columns = ["id", "question", "expected_answer", "expected_source", "has_answer"]
    for model in results:
        columns += [f"{model} | resposta", f"{model} | fontes", f"{model} | tempo_s",
                    f"{model} | nota (preencher)"]
    with (RESULTS / "comparacao.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for i in ids:
            line = {c: base[i].get(c, "") for c in columns[:5]}
            for model, rows in results.items():
                row = rows.get(i, {})
                line[f"{model} | resposta"] = row.get("error") or row.get("model_answer", "")
                line[f"{model} | fontes"] = row.get("returned_sources", "")
                line[f"{model} | tempo_s"] = row.get("time_s", "")
            writer.writerow(line)

    summary = []
    for model, rows in results.items():
        valid = [r for r in rows.values() if not r["error"]]
        times = [float(r["time_s"]) for r in valid if r["time_s"]]
        has = [r for r in valid if r["has_answer"].strip().lower() == "yes"]
        has_not = [r for r in valid if r["has_answer"].strip().lower() == "no"]
        said_not_found = lambda r: NOT_FOUND in r["model_answer"].lower()
        summary.append({
            "modelo": model,
            "perguntas": len(rows),
            "erros": len(rows) - len(valid),
            "tempo_medio_s": f"{statistics.mean(times):.1f}" if times else "",
            "tempo_mediano_s": f"{statistics.median(times):.1f}" if times else "",
            "tempo_max_s": f"{max(times):.1f}" if times else "",
            # Sinais automáticos; a nota de qualidade ainda é manual, no comparacao.csv.
            "tinha_resposta_mas_disse_nao_encontrei": f"{sum(map(said_not_found, has))}/{len(has)}",
            "nao_tinha_resposta_e_respondeu_algo": f"{sum(not said_not_found(r) for r in has_not)}/{len(has_not)}",
        })
    with (RESULTS / "resumo.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    for row in summary:
        print(" | ".join(f"{k}: {v}" for k, v in row.items()))
    print(f"\nComparação em {(RESULTS / 'comparacao.csv').resolve()}")
    print(f"Resumo em {(RESULTS / 'resumo.csv').resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia vários modelos e compara os resultados.")
    parser.add_argument("models", nargs="*", help="Modelos a avaliar, como gemma3:12b")
    parser.add_argument("--list", action="store_true", help="Lista os modelos disponíveis no OpenWebUI")
    parser.add_argument("--only-summary", action="store_true",
                        help="Não roda nada; só junta os CSVs já existentes")
    parser.add_argument("--docs", default="eval_docs", help="Pasta com os documentos de avaliação")
    parser.add_argument("--questions", default="eval/questions.csv", help="CSV com as perguntas")
    parser.add_argument("--pause", default="10", help="Segundos entre perguntas")
    args = parser.parse_args()

    if args.list:
        list_models(Settings())
        return
    if not args.models:
        sys.exit("Informe ao menos um modelo, ou use --list para ver os disponíveis.")

    if not args.only_summary:
        for model in args.models:
            print(f"\n=== {model} ===")
            output = RESULTS / f"{file_name(model)}.csv"
            command = [sys.executable, "-m", "eval.run_evaluation", "--model", model,
                       "--docs", args.docs, "--questions", args.questions, "--pause", args.pause]
            # Retoma um modelo interrompido em vez de começar do zero.
            command.append("--only-errors" if output.exists() else "--overwrite")
            if subprocess.run(command).returncode != 0:
                print(f"{model} terminou com erro ou não tinha nada a repetir; seguindo para o próximo.")

    summarize(args.models)


if __name__ == "__main__":
    main()
