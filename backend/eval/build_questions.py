"""
Gera eval/questions.csv com as perguntas de avaliação do chatbot.

Uso, dentro de backend/:
    uv run python -m eval.build_questions

As perguntas dos PDFs institucionais são fixas, com resposta e página esperadas.
As perguntas das planilhas são montadas a partir das fichas em eval_docs/, e as respostas
esperadas são calculadas aqui, na sua máquina: nenhum dado de aluno sai dela.
"""
import csv
import glob
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

DOCS = Path("eval_docs")
OUTPUT = Path("eval/questions.csv")

ESTATUTO = "Estatuto ITT versao registrada 2022-08-20.pdf"
CONTRATO = "ALN-384 Contrato Parceria Social ITT-Instituto-Tadao-Takahashi pdf-D4Sign (1).pdf"
INTRANET = "Relátorio_Intranet_no_site_WIX_ITT.pdf"
PLANO = "ITT-Alura 2026 - Plan - 16.Jan.26.pdf"

# (pergunta, resposta esperada, fonte esperada, tem resposta nos documentos?)
PDF_QUESTIONS = [
    ("Qual é a natureza jurídica do ITT?",
     "Associação civil sem fins econômicos, filantrópica, sem vinculação política ou partidária, "
     "de duração indeterminada.", f"{ESTATUTO} p.1", "yes"),
    ("Onde fica a sede do ITT?",
     "Em Campinas, na Rua Menotti Arthur Grigol, 113, Barão Geraldo, CEP 13085-485.",
     f"{ESTATUTO} p.1", "yes"),
    ("Qual é o público-alvo das ações do ITT?",
     "Crianças, jovens e adultos, com ênfase nos que estão em situação de vulnerabilidade; também "
     "pesquisadores, acadêmicos, educadores, gestores e instituições.", f"{ESTATUTO} p.1", "yes"),
    ("Como o ITT se mantém financeiramente?",
     "Contribuições de associados, doações e legados, rendas de contratos e licenciamentos, "
     "subvenções públicas, rendimentos de bens, patrocínio de eventos e outras receitas lícitas.",
     f"{ESTATUTO} p.2", "yes"),
    ("Quais são as categorias de associados do ITT?",
     "Fundadores, Titulares, Colaboradores e Honorários.", f"{ESTATUTO} p.3", "yes"),
    ("Depois de quanto tempo sem pagar a contribuição um associado é excluído?",
     "Três meses após o vencimento.", f"{ESTATUTO} p.3", "yes"),
    ("Quais são os cargos da Diretoria do ITT?",
     "Diretor Presidente, Primeiro Diretor Assistente, Segundo Diretor Assistente e Diretor Suplente.",
     f"{ESTATUTO} p.4", "yes"),
    ("Qual é a duração do mandato da Diretoria?",
     "2 anos, com reeleição permitida.", f"{ESTATUTO} p.4", "yes"),
    ("Quantos diretores precisam assinar contratos e cheques do ITT?",
     "Dois diretores em conjunto, ou seus procuradores.", f"{ESTATUTO} p.6", "yes"),
    ("Quando a Assembleia Geral ordinária se reúne?",
     "Em abril ou maio de cada ano.", f"{ESTATUTO} p.7", "yes"),
    ("Quando o estatuto atual do ITT foi aprovado?",
     "Em Assembleia Geral de 8 de agosto de 2022, em Campinas.", f"{ESTATUTO} p.10", "yes"),
    ("Quantos acessos gratuitos à plataforma Alura o contrato concede?",
     "85 acessos.", f"{CONTRATO} p.1", "yes"),
    ("Qual é a vigência do contrato com a Alura? Em qual documento isso aparece?",
     "6 meses, prorrogáveis por termo aditivo. Deve citar o contrato de parceria.",
     f"{CONTRATO} p.1", "yes"),
    ("O que o ITT oferece à Alura em troca da parceria?",
     "A logomarca da Alura nos materiais promocionais e depoimentos dos participantes ao final do projeto.",
     f"{CONTRATO} p.1", "yes"),
    ("Em quanto tempo a Alura deve liberar os acessos?",
     "Em até 48 horas após receber a lista de beneficiários.", f"{CONTRATO} p.2", "yes"),
    ("Qual app do Wix é usado para criar a área de login da intranet?",
     "O Wix Members Area (Área de Membros).", f"{INTRANET} p.3", "yes"),
    ("Como impedir que pessoas de fora se cadastrem na intranet do Wix?",
     "Mudar 'Quem pode ser membro?' para 'Pessoas que eu aprovo', com aprovação manual.",
     f"{INTRANET} p.3", "yes"),
    ("Qual é a duração prevista do Curso trilhas Alura no plano de 2026?",
     "120 dias.", f"{PLANO} p.1", "yes"),
    ("Em que ano o ITT foi fundado?", "", "", "no"),
    ("Quem é o atual Diretor Presidente do ITT?", "", "", "no"),
    ("Quantos funcionários o ITT tem?", "", "", "no"),
    ("Qual é o orçamento anual do ITT?", "", "", "no"),
]


def normalize(text: object) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def owner_of(path: str) -> str:
    return Path(path).stem.split("--")[0]


def alura_summary(path: str) -> dict | None:
    """Cursos e horas do dono da ficha, pela aba DadosAlura, como a indexação lê."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "DadosAlura" not in workbook.sheetnames:
            return None
        rows = workbook["DadosAlura"].iter_rows(values_only=True)
        header = [str(v).strip() if v is not None else "" for v in next(rows, ())]
        if "Colaborador(a)" not in header:
            return None
        owner = normalize(owner_of(path))
        started = finished = 0
        hours = 0.0
        for row in rows:
            values = dict(zip(header, row))
            if normalize(values.get("Colaborador(a)") or "") != owner:
                continue
            started += 1
            finished += str(values.get("Finalizou o curso?")).strip().lower().startswith("s")
            if isinstance(values.get("Carga Horária Consumida"), (int, float)):
                hours += values["Carga Horária Consumida"]
        return {"started": started, "finished": finished, "hours": round(hours, 1)}
    finally:
        workbook.close()


def sheet_questions() -> list[tuple[str, str, str, str]]:
    fichas = {}
    for path in sorted(glob.glob(str(DOCS / "*.xlsx"))):
        summary = alura_summary(path)
        if summary is not None:
            fichas[owner_of(path)] = summary
    if not fichas:
        print("Nenhuma ficha com aba DadosAlura encontrada; perguntas de planilha ficaram de fora.")
        return []

    questions = []
    with_data = {name: s for name, s in fichas.items() if s["started"]}

    # Perguntas sobre uma pessoa: a ficha com mais cursos, pelo nome completo.
    if with_data:
        name = max(with_data, key=lambda n: (with_data[n]["started"], n))
        s = with_data[name]
        questions += [
            (f"Quantos cursos da Alura {name} finalizou?", str(s["finished"]), name, "yes"),
            (f"Quantas horas de curso na Alura {name} consumiu?", f"{s['hours']} horas", name, "yes"),
        ]

    # Nome repetido: o chatbot deve perguntar de qual pessoa se trata.
    by_first = defaultdict(list)
    for name in fichas:
        by_first[normalize(name).split()[0]].append(name)
    repeated = sorted((names for names in by_first.values() if len(names) > 1), key=len, reverse=True)
    if repeated:
        names = sorted(repeated[0])
        first = names[0].split()[0]
        questions.append((f"Quais cursos da Alura o(a) {first} fez?",
                          "Deve perguntar de qual pessoa se trata: " + "; ".join(names), "", "yes"))

    # Agregação: dependem de todas as fichas, não de um trecho só.
    questions.append(("Quantos alunos estão no programa?",
                      f"{len(fichas)} (número de fichas individuais)", "várias fichas", "yes"))
    if with_data:
        done = sum(1 for s in with_data.values() if s["finished"])
        top = max(with_data, key=lambda n: with_data[n]["hours"])
        questions += [
            ("Quantos alunos finalizaram pelo menos um curso na Alura?", str(done), "várias fichas", "yes"),
            ("Qual aluno consumiu mais horas de curso na Alura?",
             f"{top} ({with_data[top]['hours']} horas)", "várias fichas", "yes"),
        ]
    questions.append(("Quantos mentores participam do programa em 2026?",
                      "", "Mentores 2026.xlsx", "yes"))
    return questions


def main() -> None:
    rows = PDF_QUESTIONS + sheet_questions()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "question", "expected_answer", "expected_source", "has_answer"])
        for i, row in enumerate(rows, start=1):
            writer.writerow([i, *row])
    print(f"{len(rows)} perguntas gravadas em {OUTPUT.resolve()}")
    blank = [i for i, row in enumerate(rows, start=1) if row[3] == "yes" and not row[1]]
    if blank:
        print(f"Preencha à mão a resposta esperada das perguntas {blank} (ex.: contar os mentores na planilha).")


if __name__ == "__main__":
    main()
