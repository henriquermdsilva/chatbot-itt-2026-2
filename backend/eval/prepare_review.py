"""
Prepara a avaliação das respostas sem expor dados de alunos.

Uso, dentro de backend/:
    uv run python -m eval.prepare_review

1. Grava eval/results/para_revisao.csv só com as perguntas dos PDFs institucionais
   (sem fontes nem dados das planilhas), para revisão manual ou por outra pessoa.
2. Dá nota, aqui mesmo, às perguntas sobre as planilhas, comparando números e nomes
   com a resposta esperada, e mostra só as notas (C = certa, E = errada).
"""
import csv
import re
import unicodedata
from pathlib import Path

RESULTS = Path("eval/results")
NOT_FOUND = "nao encontrei essa informacao"
AMBIGUOUS = "mais de uma pessoa"


def normalize(text: object) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9.,]+", text))


def numbers(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)]


def is_pdf_question(row: dict) -> bool:
    return ".pdf" in row["expected_source"] or row["has_answer"].strip().lower() == "no"


def grade_sheet(expected: str, answer: str) -> str:
    """Nota objetiva para as perguntas de planilha."""
    answer_n = normalize(answer)
    if not answer.strip() or NOT_FOUND in answer_n:
        return "E"
    if expected.startswith("Deve perguntar"):
        return "C" if AMBIGUOUS in answer_n else "E"
    name = re.match(r"\s*([^\d(]+?)\s*\(", expected)
    if name:  # "Nome (253.0 horas)": vale o nome certo
        return "C" if normalize(name.group(1)) in answer_n else "E"
    target = numbers(expected)
    if target:
        return "C" if any(abs(n - target[0]) < 0.05 for n in numbers(answer)) else "E"
    return "?"


def main() -> None:
    with (RESULTS / "comparacao.csv").open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        models = [c.split(" | ")[0] for c in reader.fieldnames if c.endswith(" | resposta")]

    review = [r for r in rows if is_pdf_question(r)]
    sheets = [r for r in rows if not is_pdf_question(r)]

    columns = ["id", "question", "expected_answer", "has_answer"] + [f"{m} | resposta" for m in models]
    with (RESULTS / "para_revisao.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(review)
    print(f"{len(review)} perguntas dos PDFs em {(RESULTS / 'para_revisao.csv').resolve()}\n")

    print("Notas das perguntas de planilha (C = certa, E = errada):")
    print("id  " + "  ".join(f"{m:>16}" for m in models))
    totals = {m: 0 for m in models}
    for row in sheets:
        grades = [grade_sheet(row["expected_answer"], row[f"{m} | resposta"]) for m in models]
        for m, g in zip(models, grades):
            totals[m] += g == "C"
        print(f"{row['id']:<4}" + "  ".join(f"{g:>16}" for g in grades))
    print("acertos " + "  ".join(f"{m}: {totals[m]}/{len(sheets)}" for m in models))


if __name__ == "__main__":
    main()
