"""Transforma as abas das planilhas .xlsx em texto para indexar."""

from datetime import datetime
import re
from typing import Any
import unicodedata

def normalize(text: object) -> str:
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


# A aba DadosAlura é uma exportação da turma inteira, igual em todas as fichas. Indexa só
# as linhas do dono da ficha, sem IDs, e-mail e matrícula, e com um resumo já calculado.
ALURA_SHEET = 'DadosAlura'
ALURA_PERSON = 'Colaborador(a)'
ALURA_COLUMNS = ['Curso', 'Carga Horária', 'Data de início', 'Data de finalização', 
                 'Progresso do Curso (%)', 'Carga Horária Consumida', 'Finalizou o curso?', 
                 'Avaliação do aluno', 'Motivo da avaliação']


def _alura_lines(sheet: Any, owner: str) -> list[str] | None:
    """Linhas do dono da ficha: [] se ele não aparece, ou None se o formato mudou."""
    rows = sheet.iter_rows(values_only=True)
    header = [str(value).strip() if value is not None else '' for value in next(rows, ())]
    if ALURA_PERSON not in header or not set(ALURA_COLUMNS) <= set(header):
        return None
    lines: list[str] = []
    finished, hours = 0, 0.0
    for row in rows:
        values: dict[str, Any] = dict(zip(header, row))
        if normalize(values.get(ALURA_PERSON) or '') != normalize(owner):
            continue
        cells: list[str] = []
        for column in ALURA_COLUMNS:
            value = values.get(column)
            if value is None or not str(value).strip():
                continue
            if isinstance(value, datetime):
                cells.append(f'{column}: {value.strftime("%d/%m/%Y")}')
            else:
                cells.append(f'{column}: {value}')
        lines.append(' | '.join(cells))
        finished += str(values['Finalizou o curso?']).strip().lower().startswith('s')
        if isinstance(values['Carga Horária Consumida'], (int, float)):
            hours += values['Carga Horária Consumida']
    if lines:
        lines.insert(0, f'Resumo da Alura: {len(lines)} cursos iniciados, {finished} finalizados, '
                        f'{hours:.1f} horas consumidas.')
    return lines


def sheet_lines(sheet: Any, owner: str) -> list[str]:
    """Texto da aba: cada linha como "A1: valor | B1: valor", exceto a DadosAlura."""
    if sheet.title == ALURA_SHEET:
        alura = _alura_lines(sheet, owner)
        if alura is not None:
            if not alura:
                print(f"Aviso: aluno do nome do arquivo não aparece na aba {ALURA_SHEET} de uma ficha.")
            return alura
        print(f"Aviso: aba {ALURA_SHEET} com colunas diferentes do esperado; indexada inteira.")
    lines: list[str] = []
    for row in sheet.iter_rows():
        cells = [f'{cell.coordinate}: {cell.value}' for cell in row
                 if cell.value is not None and str(cell.value).strip()]
        if cells:
            lines.append(' | '.join(cells))
    return lines
