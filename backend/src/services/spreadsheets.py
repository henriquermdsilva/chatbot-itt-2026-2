"""Indexação de fichas de estudantes e de planilhas genéricas."""

from datetime import date, datetime, time
from pathlib import Path
import re
import unicodedata

from langchain_core.documents import Document
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def normalize(text: object) -> str:
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def display(cell):
    value = cell.value
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if isinstance(value, (float, int)) and '%' in cell.number_format:
        return f'{value * 100:g}%'
    return str(value).strip()


def numeric(value):
    try:
        return float(str(value).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return None


def as_date(cell):
    if cell is None:
        return None
    if isinstance(cell.value, datetime):
        return cell.value.date()
    if isinstance(cell.value, date):
        return cell.value
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y'):
        try:
            return datetime.strptime(str(cell.value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def populated_rows(sheet, **limits):
    for row in sheet.iter_rows(**limits):
        cells = {c.column: c for c in row if c.value is not None and str(c.value).strip()}
        if cells:
            yield cells


def span(cells):
    cells = list(cells)
    start, end = cells[0].coordinate, cells[-1].coordinate
    return start if start == end else f'{start}:{end}'


def record(kind, text, cells, **metadata):
    return Document(page_content=text, metadata={'kind': kind, 'cells': cells, **metadata})


OWNER_LABELS = {'nome do estudante', 'nome do aluno', 'nome da aluna', 'nome da estudante'}
ALURA_FIELDS = ('Curso', 'Carga Horária', 'Data de início', 'Data de finalização',
                'Progresso do Curso (%)', 'Carga Horária Consumida', 'Finalizou o curso?',
                'Avaliação do aluno', 'Motivo da avaliação')
ALIASES = {
    'Pessoa': ('Colaborador(a)', 'Nome do colaborador', 'Aluno', 'Estudante', *OWNER_LABELS),
    'Curso': ('Nome do curso',),
    'Carga Horária Consumida': ('Horas consumidas',),
    'Finalizou o curso?': ('Concluiu o curso?', 'Curso concluído', 'Concluído?'),
    'Data': ('Data da interação', 'Data do registro'),
    'Horário': ('Hora',),
    'Nota Mentor': ('Nota do mentor', 'Observação do mentor', 'Registro do mentor'),
    'Nota Coordenador': ('Nota Coordernador (Nome / Nota)', 'Nota Coordenador (Nome / Nota)',
                         'Nota do coordenador', 'Observação da coordenação'),
    'Resposta Mentor': ('Resposta Mentor (Nome / Nota)', 'Resposta do mentor'),
    'Nome da atividade': ('Atividade',),
    'Comentário do aluno': ('Comentário do estudante',),
}
HEADERS = {normalize(key): key for key in (*ALURA_FIELDS, 'Tipo de atividade', 'Nome do Mentor', 'Motivo')}
HEADERS.update({normalize(alias): key for key, aliases in ALIASES.items() for alias in (key, *aliases)})


def columns(row):
    return {HEADERS.get(normalize(c.value), display(c)): i for i, c in row.items()}


def named_cells(row, header):
    return {name: row[i] for name, i in header.items() if i in row}


def fields_text(fields):
    return ' | '.join(f'{label}: {display(c)}' for label, c in fields.items())


def alura(rows, header, owner, filename_owner):
    # Um mesmo nome pode representar pessoas diferentes na exportação da turma.
    person = normalize(owner)
    matching = []
    identifiers = {}
    other_filename_owner = False
    for row in rows:
        fields = named_cells(row, header)
        if 'Pessoa' not in fields:
            continue
        name = normalize(fields['Pessoa'].value)
        if name != person:
            other_filename_owner |= name == normalize(filename_owner)
            continue
        for key, cell in fields.items():
            if normalize(key) in ('id colaborador a', 'id colaborador', 'matricula', 'email'):
                identifiers.setdefault(normalize(key), set()).add(str(cell.value).strip().casefold())
        if 'Curso' in fields:
            matching.append(fields)
    ambiguous = other_filename_owner or any(len(values) > 1 for values in identifiers.values())
    if not matching or len(person.split()) < 2 or ambiguous:
        print('Aviso: aluno do nome do arquivo não aparece ou identificação ambígua na tabela de cursos.')
        return
    courses = {}
    refs = []
    for fields in matching:
        visible = {key: fields[key] for key in ALURA_FIELDS if key in fields}
        refs.append(span(sorted([fields['Pessoa'], *visible.values()], key=lambda c: c.column)))
        status = normalize(fields['Finalizou o curso?'].value) if 'Finalizou o curso?' in fields else ''
        course_name = display(fields['Curso'])
        course_id = next((str(c.value) for key, c in fields.items() if normalize(key) == 'id curso'), None)
        course = courses.setdefault(course_id or normalize(course_name),
                                    {'name': course_name, 'finished': set(), 'hours': set()})
        if status in {'sim', 'true', '1', 'concluido'} or as_date(fields.get('Data de finalização')):
            course['finished'].add(True)
        elif status in {'nao', 'false', '0', 'em andamento'}:
            course['finished'].add(False)
        if 'Carga Horária Consumida' in fields:
            consumed = numeric(fields['Carga Horária Consumida'].value)
            if consumed is not None:
                course['hours'].add(consumed)
        yield record('curso', fields_text(visible), refs[-1])
    completed = [c['name'] for c in courses.values() if c['finished'] == {True}]
    unknown_status = sum(len(c['finished']) != 1 for c in courses.values())
    hours = [next(iter(c['hours'])) for c in courses.values() if len(c['hours']) == 1]
    finished = f'{len(completed)} finalizados'
    if unknown_status:
        finished += f' confirmados ({unknown_status} sem situação informada)'
    workload = (f'{sum(hours):.1f} horas consumidas' if len(hours) == len(courses)
                else 'total de horas consumidas não informado')
    summary = f'Resumo da Alura: {len(courses)} cursos iniciados, {finished}, {workload}.'
    titles = ', '.join(c['name'] for c in courses.values())
    done = ', '.join(completed) or 'nenhum confirmado'
    yield record('resumo_cursos', f'{summary}\nCursos registrados: {titles}.\nCursos finalizados: {done}.',
                 ', '.join(refs))


def interactions(rows, header):
    for row in rows:
        fields = named_cells(row, header)
        notes = [k for k in ('Nota Mentor', 'Resposta Mentor', 'Nota Coordenador', 'Motivo') if k in fields]
        if not notes:
            continue
        day = as_date(fields.get('Data'))
        hour = display(fields['Horário']) if 'Horário' in fields else ''
        clock = re.fullmatch(r'(\d{1,2}):(\d{2})(?::\d{2})?\s*(?:hrs?|h)?', hour, re.I)
        timestamp = day.isoformat() if day else ''
        if timestamp and clock:
            timestamp += f' {int(clock[1]):02}:{clock[2]}'
        yield record('interacao', fields_text(fields), span(row.values()), data=timestamp,
                     mentor=any(k in notes for k in ('Nota Mentor', 'Resposta Mentor')),
                     coordenacao='Nota Coordenador' in notes)


def evaluations(rows, header):
    formation = module = ''
    for row in rows:
        fields = named_cells(row, header)
        if 'Nome da atividade' not in fields:
            continue
        raw_type = display(fields['Tipo de atividade']) if 'Tipo de atividade' in fields else ''
        activity = normalize(raw_type)
        name = display(fields['Nome da atividade'])
        if activity.startswith('formacao') or normalize(name).startswith('formacao '):
            formation, module = name, ''
        elif activity == 'modulo' or numeric(raw_type) is not None:
            module = name
        context = []
        if formation and formation != name:
            context.append(f'Formação: {formation}')
        if module and module != name:
            context.append(f'Módulo: {module}')
        yield record('avaliacao', ' | '.join([*context, fields_text(fields)]), span(row.values()),
                     curso_comentado=activity == 'curso' and 'Comentário do aluno' in fields)


def scorecard(rows):
    metrics = {}
    grade_ranges = []
    for row in rows:
        if len(row) == 1:
            value = display(next(iter(row.values())))
            band = re.fullmatch(r'(\d+)\s*a\s*(\d+)\s*[-–:]\s*(.+)', value, re.I)
            if band:
                grade_ranges.append((int(band[1]), int(band[2]), band[3]))
        for cell in row.values():
            label = normalize(cell.value)
            if label.startswith('semanas terminadas') or label in ('fim da semana', 'data da semana'):
                metrics['Semana terminada em'] = row
            elif label in ('nr da semana', 'numero da semana', 'semana'):
                metrics['Número da semana'] = row
            elif label in ('horas p sem acumulado', 'horas planejadas', 'horas previstas'):
                metrics['Horas planejadas (' + display(cell) + ')'] = row
            elif label in ('horas cursos estudadas', 'horas estudadas', 'horas realizadas'):
                metrics['Horas estudadas'] = row
            elif label in ('frequencia nas reunioes', 'presenca nas reunioes') or (
                label in ('frequencia', 'presenca') and len(row) > 1
            ):
                metrics['Frequência nas reuniões'] = row
            elif label in ('data da reuniao', 'desempenho', 'nota') and len(row) > 1:
                metrics.setdefault(display(cell).rstrip(' :'), row)
            # Os rótulos ficam à esquerda dos valores, inclusive nas linhas de legenda.
            if isinstance(cell.value, (int, float, date)):
                break
    metric_rows = [next(iter(row.values())).row for row in metrics.values()]
    for col, cell in metrics.get('Semana terminada em', {}).items():
        day = as_date(cell)
        week = metrics.get('Número da semana', {}).get(col)
        if not day or (week is not None and numeric(week.value) is None):
            continue
        fields = {key: row[col] for key, row in metrics.items() if col in row}
        frequency = fields.get('Frequência nas reuniões')
        text = fields_text(fields)
        grade = fields.get('Desempenho')
        if grade is not None and (score := numeric(grade.value)) is not None:
            for low, high, description in grade_ranges:
                if low <= score <= high:
                    text += f' | Classificação do desempenho: {description}'
                    break
        if not frequency:
            text += ' | Frequência nas reuniões: sem informação registrada'
        letter = get_column_letter(col)
        cells = f'{letter}{min(metric_rows)}:{letter}{max(metric_rows)}'
        hours = fields.get('Horas estudadas')
        yield record('semana', text, cells,
                     data=day.isoformat(), horas=hours is not None and numeric(hours.value) is not None,
                     frequencia=normalize(frequency.value) if frequency else '')


def profile(rows):
    section = 'Ficha do estudante'
    previous = 0
    for row in rows:
        label, *answers = row.values()
        text = display(label)
        if not answers and label.row > previous + 1 and '?' not in text:
            section = text
        elif normalize(section) not in {'nota', 'legenda'}:
            answer = ' | '.join(display(c) for c in answers) or 'sem informação registrada'
            yield record('perfil', f'{section} — {text}: {answer}', span(row.values()))
        previous = label.row


def course_table(title, rows):
    """Distingue uma exportação coletiva mesmo quando faltam colunas obrigatórias."""
    if any(name in title for name in ('dadosalura', 'dadosdaalura', 'exportacaoalura')):
        return True
    for row in rows:
        keys = columns(row)
        labels = {normalize(c.value) for c in row.values()}
        if 'Pessoa' in keys and (any('curso' in k for k in labels) or 'matricula' in labels):
            return True
        if 'Curso' in keys and ('Carga Horária Consumida' in keys or 'id curso' in labels):
            return True
    return False


def sheet_records(sheet, owner, filename_owner, profiles, collective):
    rows = list(populated_rows(sheet))
    if sheet.title in profiles:
        return profile(rows)
    for i, row in enumerate(rows[:40]):
        header = columns(row)
        if {'Pessoa', 'Curso'} <= header.keys():
            person_columns = sum(HEADERS.get(normalize(c.value)) == 'Pessoa' for c in row.values())
            if person_columns != 1:
                return ()
            return alura(rows[i + 1:], header, owner, filename_owner)
        if sheet.title in collective:
            continue
        if 'Data' in header and {'Nota Mentor', 'Nota Coordenador', 'Resposta Mentor'} & header.keys():
            return interactions(rows[i + 1:], header)
        if 'Nome da atividade' in header and {'Tipo de atividade', 'Comentário do aluno'} & header.keys():
            return evaluations(rows[i + 1:], header)

    if sheet.title in collective:
        print('Aviso: tabela de cursos com colunas diferentes do esperado, ignorada.')
        return ()
    if 'scorecard' in normalize(sheet.title).replace(' ', '') or any(
        normalize(c.value).startswith('semanas terminadas') for r in rows[:40] for c in r.values()
    ):
        return scorecard(rows)
    if profiles or not rows:
        return ()
    lines = [' | '.join(f'{c.coordinate}: {display(c)}' for c in row.values()) for row in rows]
    return [Document(page_content='\n'.join(lines))]


def workbook_documents(path: Path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        profiles = set()
        identities = {}
        collective = set()
        for sheet in workbook:
            preview = list(populated_rows(sheet, max_row=40))
            title = normalize(sheet.title).replace(' ', '')
            if course_table(title, preview):
                collective.add(sheet.title)
                continue
            for row in preview:
                label, *answers = row.values()
                if normalize(label.value) in OWNER_LABELS and len(answers) <= 1:
                    profiles.add(sheet.title)
                    if answers:
                        value = display(answers[0])
                        identities[normalize(value)] = value
        filename_owner = path.stem.split('--')[0]
        if profiles and len(identities) != 1:
            print('Aviso: ficha sem identidade individual inequívoca, ignorada.')
            return
        owner = next(iter(identities.values()), filename_owner)
        for sheet in workbook:
            title = normalize(sheet.title).replace(' ', '')
            if title.startswith('configficha'):
                continue
            for doc in sheet_records(sheet, owner, filename_owner, profiles, collective):
                doc.metadata.update(source=str(path), sheet=sheet.title, owner=owner)
                yield doc
    finally:
        workbook.close()
