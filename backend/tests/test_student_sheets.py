import asyncio
from unittest.mock import Mock, patch

import pytest

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from openpyxl import Workbook, load_workbook

from src.config import Settings
from src.services.chains import TriageOutput
from src.services.spreadsheets import explicit_sheet_query, workbook_documents
from src.services.graph import ITTGraph
from src.services.vectorDB import StudentQueryError, VectorDB
from test_google_drive import TestEmbeddings


def example(path):
    wb = Workbook()
    profile = wb.active
    profile.title = 'Entrevista 2026'
    profile.append(['Ficha do estudante'])
    profile.append(['Nome do estudante', 'Ana Silva'])
    profile.append([])
    profile.append(['Sobre o aluno'])
    profile.append(['O que deseja aprender?'])
    notes = wb.create_sheet('Histórico')
    notes.append(['Histórico dos atendimentos'])
    notes.append(['Nota Coordernador (Nome / Nota)', 'Data', 'Nota do mentor'])
    notes.append(['Pergunta', '12/03/2026', 'Observação mais recente do mentor'])
    notes.append(['Cobrança posterior', '20/03/2026'])
    for i in range(1, 8):
        notes.append([None, f'0{i}/03/2026', 'Nota mais antiga'])
    score = wb.create_sheet('Indicadores')
    score.append(['Nr. da Semana', 1, 2, 3, 4, 'Data Final'])
    score.append(['Semanas terminadas em', '01/03/2026', '08/03/2026', '15/03/2026', '22/03/2026', '30/03/2026'])
    score.append(['Horas planejadas', 2, 4, 6, 8])
    score.append(['Horas estudadas', 2, 0, None, 'N/A'])
    score.append(['Frequência nas reuniões', 'Falta', None, 'N/A', 'Presente'])
    score.append(['Legenda'])
    score.append(['Falta'])
    courses = wb.create_sheet('Exportação de cursos')
    courses.append(['Dados da plataforma'])
    courses.append(['HORAS CONSUMIDAS', 'Nome do Curso', 'Nome do aluno', 'Concluiu o curso?'])
    for i in range(7):
        courses.append(['2,5', f'Curso {i}', 'ANA SILVA', 'Sim' if i < 4 else 'Não'])
    courses.append(['2,5', 'Curso 0', 'Ana Silva', 'Sim'])  # Linha repetida na exportação.
    courses.append([99, 'Curso de outra aluna', 'Ana Souza', 'Sim'])
    evaluations = wb.create_sheet('Opiniões')
    evaluations.append(['ATIVIDADE', 'TIPO DE ATIVIDADE', 'COMENTÁRIO DO ESTUDANTE', 'Status'])
    evaluations.append(['Formação A', 'Formação'])
    evaluations.append(['Módulo A', 1])
    evaluations.append(['Curso A', 'Curso', 'Gostei'])
    evaluations.append(['Curso B', 'Curso'])
    evaluations.append([None, None, None, 'Ok'])
    wb.create_sheet('Config Ficha').append(['Opção de teste'])
    wb.save(path)
    wb.close()


def test_index_and_queries_by_identity_author_date_and_cell(tmp_path):
    path = tmp_path / 'Ficha 17--drive.xlsx'
    example(path)
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index')))
    db.create_faiss_index(path)

    def lookup(kind, student='Ana Silva'):
        return db.query('consulta traduzida', lookup=kind, student=student)

    assert lookup('ultima_interacao')[0].metadata['cells'] == 'A4:B4'
    mentor, = lookup('ultima_nota_mentor')
    assert 'Observação mais recente do mentor' in mentor.page_content
    assert mentor.metadata['data'] == '2026-03-12'
    assert ITTGraph._build_citations([mentor])[0]['cells'] == 'A3:C3'
    assert lookup('ultima_nota_coordenacao')[0].metadata['data'] == '2026-03-20'
    assert not lookup('ultima_interacao', student='Ana Souza')
    week, = lookup('ultima_semana_com_horas')
    assert 'Horas estudadas: 0' in week.page_content
    assert 'sem informação registrada' in week.page_content
    absence, = lookup('semanas_com_falta')
    assert absence.metadata['data'] == '2026-03-01'
    summary, = lookup('resumo_cursos')
    assert '7 cursos iniciados, 4 finalizados, 17.5 horas consumidas' in summary.page_content
    assert 'Curso 6' in summary.page_content
    evaluated, = lookup('cursos_comentados')
    assert 'Curso A' in evaluated.page_content and 'Módulo: Módulo A' in evaluated.page_content
    docs = list(workbook_documents(path))
    assert any('Sobre o aluno — O que deseja aprender?: sem informação registrada' in d.page_content for d in docs)
    assert all('outra aluna' not in d.page_content and d.metadata['sheet'] != 'Config Ficha' for d in docs)


def test_ambiguous_identity_or_unrecognized_roster_never_falls_back_to_whole_sheet(tmp_path):
    for title, rows in [
        ('dados ALURA', [['Curso', 'Colaborador(a)', 'Matrícula'],
                         ['Curso A', 'Ana Silva', '1'], ['Curso B', 'Ana Silva', '2']]),
        ('Exportação', [['Nome do estudante', 'Curso novo'], ['Ana Silva', 'Curso A'], ['Ana Souza', 'Curso B']]),
        ('Dados-Alura', [['Curso', 'Colaborador(a)', 'Aluno'], ['Curso A', 'Ana Silva', 'Ana Souza']]),
    ]:
        path = tmp_path / 'Ana Silva.xlsx'
        wb = Workbook()
        wb.active.title = title
        for row in rows:
            wb.active.append(row)
        wb.save(path)
        wb.close()
        assert list(workbook_documents(path)) == []


def test_both_chat_endpoints_ground_followup_in_the_same_dated_record(tmp_path):
    path = tmp_path / 'Ficha 17.xlsx'
    example(path)
    settings = Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index'))
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(settings)
    db.create_faiss_index(path)
    triage = Mock()
    triage.invoke.return_value = TriageOutput(decisao='AUTO_RESOLVER', aluno='Ana Silva',
                                              consulta_ficha='ultima_nota_mentor',
                                              pergunta_contextualizada='Última observação do mentor de Ana Silva?')

    def answer(payload):
        doc, = payload['context']
        assert 'Observação mais recente do mentor' in doc.page_content
        assert 'Cobrança posterior' not in doc.page_content
        return 'Observação mais recente do mentor'

    with (patch('src.services.graph.get_triage_chain', return_value=triage),
          patch('src.services.graph.get_rag_chain', return_value=RunnableLambda(answer))):
        graph = ITTGraph(settings, db)
    history = [{'role': 'user', 'content': 'Como está Ana Silva?'}]
    question = 'E a última nota do mentor dela?'
    result = graph.invoke(question, history)
    assert result['source_documents'][0]['cells'] == 'A3:C3'

    async def collect():
        return [event async for event in graph.astream_response(question, history)]

    events = asyncio.run(collect())
    assert events[0]['data'] == result['source_documents']
    assert events[1]['data'] == result['response']


def test_checked_absences_and_comments_with_no_matches_keep_source_cells(tmp_path):
    path = tmp_path / 'Ficha.xlsx'
    example(path)
    wb = load_workbook(path)
    wb['Indicadores']['B5'] = None
    wb['Opiniões']['C4'] = None
    wb.save(path)
    wb.close()
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index')))
    db.create_faiss_index(path)
    absences, = db.query('faltas', student='Ana Silva', lookup='semanas_com_falta')
    assert 'Nenhuma falta registrada' in absences.page_content
    assert absences.metadata['cells'] == 'B1:E5'
    courses, = db.query('comentários', student='Ana Silva', lookup='cursos_comentados')
    assert 'Nenhum curso com comentário' in courses.page_content


def test_education_question_finds_schooling_outside_semantic_top_four(tmp_path):
    path = tmp_path / 'Ficha.xlsx'
    example(path)
    wb = load_workbook(path)
    profile = wb['Entrevista 2026']
    profile.append(['Expectativa', 'Melhorar minha formação escolar'])
    profile.append(['1.Formação escolar (concluída ou em andamento)?', '2º ano do ensino médio'])
    wb.save(path)
    wb.close()
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index')))
    db.create_faiss_index(path)
    for student, lookup in [('', ''), ('Ana', ''), ('Ana', 'perfil')]:
        docs = db.query('qual o nivel de formacao da aluna Ana', student=student, lookup=lookup)
        assert [d.metadata.get('cells') for d in docs] == ['A7:B7']
        assert '2º ano do ensino médio' in docs[0].page_content
    with patch('src.services.graph.get_triage_chain'), patch('src.services.graph.get_rag_chain'):
        graph = ITTGraph(db.settings, db)
    docs = graph._search('Qual o nível de formação da aluna Ana?', {
        'consulta_busca': 'academic background', 'consulta_ficha': 'resumo_cursos', 'aluno': 'Ana',
    })
    assert [d.metadata['cells'] for d in docs] == ['A7:B7']
    assert not db.query('Qual a escolaridade?', student='Ana Souza')
    assert not db.query('Qual a escolaridade da aluna Isabela?')
    assert db.query('Quais cursos Ana concluiu na Alura?', student='Ana',
                    lookup='resumo_cursos')[0].metadata['kind'] == 'resumo_cursos'


def test_excel_lock_file_does_not_prevent_indexing(tmp_path):
    example(tmp_path / 'Ficha.xlsx')
    (tmp_path / '~$Ficha.xlsx').write_bytes(b'Excel owner file')
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index')))
    db.create_faiss_index(tmp_path)
    assert db.query('Ana Silva')


def test_shared_notes_and_evaluations_are_filtered_before_lookup(tmp_path):
    path = tmp_path / 'Ficha.xlsx'
    example(path)
    wb = load_workbook(path)
    notes = wb['Histórico']
    notes['D2'] = 'Nome do aluno'
    notes.append([None, '15/04/2026', 'Nota de Ana', 'Ana Silva'])
    notes.append([None, '16/04/2026', 'Nota de Bruna', 'Bruna Rocha'])
    sheet = wb.create_sheet('Outras avaliações')
    sheet.append(['Nome do aluno', 'Atividade', 'Comentário do estudante'])
    sheet.append(['Bruna Rocha', 'Atividade B', 'Comentário de Bruna'])
    sheet.append(['Ana Silva', 'Atividade A', 'Comentário de Ana'])
    wb.save(path)
    wb.close()
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index')))
    db.create_faiss_index(path)
    note, = db.query('última observação', student='Ana Silva', lookup='ultima_nota_mentor')
    assert 'Nota de Ana' in note.page_content
    comments = db.query('comentários', student='Ana Silva', lookup='cursos_comentados')
    assert any('Tipo de atividade: não informado' in d.page_content for d in comments)
    assert all('Bruna' not in d.page_content for d in workbook_documents(path))


def test_exact_pdf_and_legacy_sheet_queries_remain_scoped(tmp_path):
    embeddings = TestEmbeddings()
    docs = [Document(page_content='Astronomia', metadata={'source': 'Ana Silva.pdf'}),
            Document(page_content='Entrevista', metadata={'source': 'Bia Dias.xlsx', 'sheet': 'Perfil'})]
    FAISS.from_documents(docs, embeddings).save_local(str(tmp_path))
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=embeddings):
        db = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path)))
    assert db.query('Área de interesse?', student='Ana Silva')[0].page_content == 'Astronomia'
    assert not db.query('Qual a escolaridade de Isabela?')
    assert db.query('Entrevista', student='Bia', lookup='perfil')[0].page_content == 'Entrevista'
    with pytest.raises(StudentQueryError, match='Atualizar Docs'):
        db.query('Cursos concluídos', student='Bia', lookup='resumo_cursos')


@pytest.mark.parametrize('question, expected, sheet, blank_attendance', [
    ('Segundo a aba DadosAlura, quantos cursos a Ana iniciou, quantos finalizou e quantas horas consumiu?',
     '7 cursos iniciados, 4 finalizados, 17,5 horas consumidas', 'Exportação de cursos', False),
    ('Em quais semanas o scorecard registra explicitamente uma falta da Ana nas reuniões?',
     '01/03/2026', 'Indicadores', False),
    ('Em quais semanas a Ana faltou às reuniões?',
     'Nenhuma falta registrada nas semanas da ficha. Semanas em branco têm presença desconhecida.', 'Indicadores', True),
])
def test_chat_answers_sheet_questions_without_model_routing(tmp_path, question, expected, sheet, blank_attendance):
    path = tmp_path / 'Ficha.xlsx'
    example(path)
    if blank_attendance:
        wb = load_workbook(path)
        wb['Indicadores']['B5'] = None
        wb.save(path)
        wb.close()
    settings = Settings(_env_file=None, FAISS_INDEX_PATH=str(tmp_path / 'index'))
    with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=TestEmbeddings()):
        db = VectorDB(settings)
    db.create_faiss_index(path)
    triage = Mock()
    triage.invoke.return_value = TriageOutput(decisao='AUTO_RESOLVER')
    with (patch('src.services.graph.get_triage_chain', return_value=triage),
          patch('src.services.graph.get_rag_chain', return_value=RunnableLambda(lambda _: 'NAO_ENCONTRADO'))):
        graph = ITTGraph(settings, db)
    result = graph.invoke(question)
    assert expected in result['response']
    source, = result['source_documents']
    assert source['sheet'] == sheet and source['cells']

    async def collect():
        return [event async for event in graph.astream_response(question)]

    events = asyncio.run(collect())
    assert events[0]['data'] == [source]
    assert ''.join(e['data'] for e in events if e['type'] == 'token') == result['response']
    assert events[-1]['type'] == 'done'

    triage.invoke.assert_not_called()


@pytest.mark.parametrize('question', [
    'Em quais semanas ela faltou às reuniões?',
    'Quantos cursos de Python a Ana iniciou na Alura?',
    'Em quais semanas o scorecard registra uma falta da Ana em maio?',
])
def test_followups_and_filtered_questions_keep_normal_triage(question):
    assert explicit_sheet_query(question) is None
