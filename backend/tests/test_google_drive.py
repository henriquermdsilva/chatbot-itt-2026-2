import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import fitz
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from openpyxl import Workbook

from src.config import Settings
from src.index_documents import main
from src.services.google_drive import DriveService, DOC_MIME, FOLDER_MIME, PDF_MIME, XLSX_MIME
from src.services.vectorDB import AmbiguousPersonError, VectorDB


class TestEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class GoogleDriveTest(unittest.TestCase):
    def drive(self, folder):
        drive = DriveService.__new__(DriveService)
        drive.folder_id = 'root-folder'
        drive.download_path = Path(folder)
        drive.service = Mock()
        drive.service.files.return_value.get.return_value.execute.return_value = {'mimeType': FOLDER_MIME}
        return drive

    def test_pagination_subfolders_and_unsupported_files(self):
        drive = self.drive('.')
        pdf = {'id': 'pdf1', 'name': 'Manual.pdf', 'mimeType': PDF_MIME}
        doc = {'id': 'doc1', 'name': 'Normas', 'mimeType': DOC_MIME}
        excel = {'id': 'excel1', 'name': 'Perfil.xlsx', 'mimeType': XLSX_MIME}
        api = drive.service.files.return_value
        api.list.return_value.execute.side_effect = [
            {'files': [], 'nextPageToken': 'page2'},
            {'files': [pdf, {'id': 'child', 'mimeType': FOLDER_MIME}]},
            {'files': [doc, excel, {'id': 'image', 'mimeType': 'image/png'}]},
        ]
        self.assertEqual(drive.list_files(), [pdf, doc, excel])
        self.assertEqual(api.list.call_args_list[1].kwargs['pageToken'], 'page2')
        self.assertIn("'child' in parents", api.list.call_args.kwargs['q'])
        self.assertTrue(api.list.call_args.kwargs['includeItemsFromAllDrives'])

    @patch('src.services.google_drive.MediaIoBaseDownload')
    def test_download_export_duplicate_names_and_safe_paths(self, downloader):
        with tempfile.TemporaryDirectory() as folder:
            drive = self.drive(folder)
            drive.list_files = Mock(return_value=[
                {'id': 'pdf1', 'name': '../../Manual.pdf', 'mimeType': PDF_MIME},
                {'id': 'doc1', 'name': '../../Manual.pdf', 'mimeType': DOC_MIME},
                {'id': 'excel1', 'name': 'Perfil.xlsx', 'mimeType': XLSX_MIME},
            ])
            downloader.return_value.next_chunk.side_effect = [(None, False), (None, True), (None, True), (None, True)]
            paths = [Path(p) for p in drive.download_files()]
            self.assertEqual(len(set(paths)), 3)
            self.assertEqual(paths[-1].name, 'Perfil--excel1.xlsx')
            self.assertTrue(all(p.parent == Path(folder) and p.is_file() for p in paths))
            self.assertEqual([call.kwargs['fileId'] for call in drive.service.files.return_value.get_media.call_args_list], ['pdf1', 'excel1'])
            drive.service.files.return_value.export_media.assert_called_once_with(fileId='doc1', mimeType=PDF_MIME)
            self.assertTrue(all(c.args[0].closed for c in downloader.call_args_list))

    @patch('src.services.google_drive.build', new=Mock())
    @patch('src.services.google_drive.service_account.Credentials.from_service_account_info')
    def test_json_credentials_from_dotenv_are_passed_and_hidden(self, credentials):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text('GOOGLE_CREDENTIALS_JSON=\'{"private_key":"test-secret"}\'\n', encoding='utf-8')
            settings = Settings(_env_file=env)
            DriveService(str(Path(folder) / 'missing.json'), 'root-folder', folder,
                         settings.GOOGLE_CREDENTIALS_JSON.get_secret_value())
            self.assertEqual(credentials.call_args.args[0], {'private_key': 'test-secret'})
            self.assertNotIn('test-secret', repr(settings))

    def test_invalid_folder_and_empty_folder_fail(self):
        with self.assertRaisesRegex(ValueError, 'apenas o ID'):
            DriveService('missing.json', 'https://drive.google.com/drive/folders/abc', '.')
        drive = self.drive('.')
        drive.service.files.return_value.get.return_value.execute.return_value = {'mimeType': PDF_MIME}
        with self.assertRaisesRegex(ValueError, 'nao aponta para uma pasta'):
            drive.list_files()
        drive.list_files = Mock(return_value=[])
        with self.assertRaisesRegex(ValueError, 'Nenhum PDF, Google Doc ou Excel'):
            drive.download_files()

    @patch('src.services.vectorDB.OpenWebUIEmbeddings', new=Mock(return_value=TestEmbeddings()))
    def test_excel_index_keeps_sheet_cells_and_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Estudante Exémplo.xlsx'
            workbook = Workbook()
            sheet = workbook.worksheets[0]
            sheet.title = 'Perfil'
            sheet.append(['Area de interesse', 'Astronomia'])
            sheet.append(['Cursos concluidos', 0])
            workbook.create_sheet('Vazia')
            workbook.save(path)
            workbook.save(Path(folder) / 'Outro Estudante.xlsx')
            workbook.close()
            database = VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(Path(folder) / 'index')))
            database.create_faiss_index(folder)
            results = database.query('Qual o interesse de Estudante Exemplo?')
            self.assertEqual(len(results), 1)
            doc = results[0]
            self.assertIn('Arquivo: Estudante Exémplo.xlsx', doc.page_content)
            self.assertIn('A1: Area de interesse | B1: Astronomia', doc.page_content)
            self.assertIn('B2: 0', doc.page_content)
            self.assertEqual(doc.metadata['sheet'], 'Perfil')
            self.assertNotIn('page', doc.metadata)

    @patch('src.index_documents.VectorDB')
    @patch('src.index_documents.Settings')
    def test_cli_selects_drive_and_keeps_local_mode(self, settings, database):
        settings.return_value.GOOGLE_DRIVE_FOLDER_ID = 'root-folder'
        with patch('sys.argv', ['index_documents', '--drive']):
            main()
        database.return_value.refresh_knowledge_base.assert_called_once()
        database.return_value.create_faiss_index.assert_not_called()
        with patch('sys.argv', ['index_documents', 'manual.pdf']):
            main()
        database.return_value.create_faiss_index.assert_called_once_with('manual.pdf')
        settings.return_value.GOOGLE_DRIVE_FOLDER_ID = ''
        with patch('sys.argv', ['index_documents', '--drive']), self.assertRaises(SystemExit):
            main()
        with patch('sys.argv', ['index_documents', '--drive', 'manual.pdf']), self.assertRaises(SystemExit):
            main()

    @patch('src.services.vectorDB.OpenWebUIEmbeddings', new=Mock(return_value=TestEmbeddings()))
    @patch('src.services.vectorDB.DriveService')
    def test_sync_indexes_downloads_and_preserves_index_on_download_failure(self, service):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(_env_file=None, GOOGLE_DRIVE_FOLDER_ID='root-folder',
                                FAISS_INDEX_PATH=str(Path(folder) / 'index'))
            database = VectorDB(settings)

            def download():
                path = Path(service.call_args.kwargs['download_path']) / 'Manual--id.pdf'
                with fitz.open() as pdf:
                    pdf.new_page().insert_text((72, 72), 'O laboratorio abre as nove horas.')
                    pdf.save(path)
                return [str(path)]

            service.return_value.download_files.side_effect = download
            database.refresh_knowledge_base()
            self.assertFalse(Path(service.call_args.kwargs['download_path']).exists())
            self.assertIn('nove horas', database.query('Horario?')[0].page_content)
            index_path = Path(settings.FAISS_INDEX_PATH)
            before = {p.name: p.read_bytes() for p in index_path.glob('index.*')}
            service.return_value.download_files.side_effect = RuntimeError('Download falhou')
            with self.assertRaisesRegex(RuntimeError, 'Download falhou'):
                database.refresh_knowledge_base()
            self.assertEqual(before, {p.name: p.read_bytes() for p in index_path.glob('index.*')})

    @patch('src.services.vectorDB.OpenWebUIEmbeddings', new=Mock(return_value=TestEmbeddings()))
    def test_shared_first_name_asks_which_person(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('Fulano Silva', 'Fulano Souza', 'Fulano Souza Lima', 'Sicrana Lima', 
                         'Mentores 2026', '2026 Turma', 'Beltrana Clara Dias', 
                         'Beltrana Beatriz Reis'):
                workbook = Workbook()
                workbook.worksheets[0].append(['Acompanhamento', f'Notas de {name}'])
                workbook.save(Path(folder) / f'{name}--id{len(name)}.xlsx')
                workbook.close()
            database = VectorDB(Settings(_env_file=None, 
                                         FAISS_INDEX_PATH=str(Path(folder) / 'index')))
            database.create_faiss_index(folder)

            with self.assertRaises(AmbiguousPersonError) as error:
                database.query('Como está indo o Fulano?')
            self.assertEqual(error.exception.names, ['Fulano Silva', 'Fulano Souza', 
                                                     'Fulano Souza Lima'])
            for doc in database.query('Como está a Beltrana Clara?'):
                self.assertIn('Beltrana Clara Dias--', doc.metadata['source'])
            with self.assertRaises(AmbiguousPersonError):
                database.query('Como está a Beltrana?')

            for doc in database.query('E o Fulano Souza?'):
                self.assertIn('Fulano Souza--', doc.metadata['source'])

            self.assertIn('Fulano Silva', database.query('Como está o Fulano Silva?')[0].page_content)
            self.assertTrue(database.query('Como está a Sicrana?'))
            self.assertTrue(database.query('Quem compõe a diretoria?'))
            self.assertTrue(database.query('Quem são os mentores de 2026?'))

    @patch('src.services.vectorDB.OpenWebUIEmbeddings', new=Mock(return_value=TestEmbeddings()))
    def test_alura_sheet_keeps_only_the_owner_rows_with_summary(self):
        header = ['Id colaborador(a)', 'Colaborador(a)', 'Curso', 'Carga Horária', 'Data de início',
                  'Data de finalização', 'Progresso do Curso (%)', 'Carga Horária Consumida',
                  'Finalizou o curso?', 'Avaliação do aluno', 'Motivo da avaliação', 'Email', 
                  'Matrícula']
        with tempfile.TemporaryDirectory() as folder:
            workbook = Workbook()
            workbook.worksheets[0].title = 'Acompanhamento'
            workbook.worksheets[0].append(['Semana 1', 'Começou bem'])
            alura = workbook.create_sheet('DadosAlura')
            alura.append(header)
            alura.append([1, 'Beltrana Clara Dias', 'Python', 8.0, datetime(2026, 2, 1), 
                          datetime(2026, 3, 1), 100.0, 8.5, 'Sim', 9.0, None, 'beltrana@x.com', 'M1'])
            alura.append([1, 'BELTRANA CLARA DIAS', 'Git', 4.0, datetime(2026, 3, 5), None, 50.0, 
                          2.0, 'Não', None, None, 'beltrana@x.com', 'M1'])
            alura.append([2, 'Outra Pessoa', 'Java', 6.0, datetime(2026, 2, 1), None, 10.0, 1.0, 
                          'Não', None, None, 'outra@x.com', 'M2'])
            workbook.save(Path(folder) / 'Beltrana Clara Dias--id1.xlsx')
            alura.title = 'DadosAlura'
            alura['B2'] = 'Outra Pessoa'
            alura['B3'] = 'Outra Pessoa'
            workbook.save(Path(folder) / 'Sem Linhas--id2.xlsx')
            workbook.close()

            with patch('builtins.print') as printed:
                VectorDB(Settings(_env_file=None, FAISS_INDEX_PATH=str(Path(folder) / 'index'))).create_faiss_index(folder)
            messages = [str(call) for call in printed.call_args_list]
            self.assertEqual(sum('aluno do nome do arquivo não aparece' in m for m in messages), 1)

            store = FAISS.load_local(str(Path(folder) / 'index'), TestEmbeddings(), 
                                     allow_dangerous_deserialization=True)
            indexed = [store.docstore.search(doc_id) for doc_id in store.index_to_docstore_id.values()]
            alura_docs = [doc for doc in indexed
                          if isinstance(doc, Document) and doc.metadata.get('sheet') == 'DadosAlura']
            alura_text = '\n'.join(doc.page_content for doc in alura_docs)
            self.assertIn('Resumo da Alura: 2 cursos iniciados, 1 finalizados, 10.5 horas consumidas.', 
                          alura_text)
            self.assertIn('Curso: Python | Carga Horária: 8 | Data de início: 01/02/2026', alura_text)
            for absent in ('Java', 'Outra Pessoa', 'beltrana@x.com', 'M1', 'Id colaborador'):
                self.assertNotIn(absent, alura_text)
            self.assertNotIn('Sem Linhas', ' '.join(doc.metadata['source'] for doc in alura_docs))

    @patch('src.services.vectorDB.OpenWebUIEmbeddings', new=Mock(return_value=TestEmbeddings()))
    def test_alura_sheet_with_unknown_columns_is_indexed_whole(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = Workbook()
            sheet = workbook.worksheets[0]
            sheet.title = 'DadosAlura'
            sheet.append(['Aluno', 'Curso novo'])
            sheet.append(['Beltrana Clara Dias', 'Python'])
            workbook.save(Path(folder) / 'Beltrana Clara Dias--id1.xlsx')
            workbook.close()
            with patch('builtins.print') as printed:
                database = VectorDB(Settings(_env_file=None, 
                                             FAISS_INDEX_PATH=str(Path(folder) / 'index')))
                database.create_faiss_index(folder)
            self.assertIn('colunas diferentes do esperado', str(printed.call_args_list))
            self.assertIn('B2: Python', database.query('Python')[0].page_content)

    def test_interrupted_indexing_resumes_from_embeddings_cache(self):
        def sent(embedder: Mock) -> int:
            return sum(len(call.args[0]) for call in embedder.embed_documents.call_args_list)

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'docs'
            source.mkdir()
            workbook = Workbook()
            for number in range(40):
                workbook.worksheets[0].append([f'{number} ' + 'x' * 900])
            workbook.save(source / 'Longa.xlsx')
            workbook.close()
            # O nome padrão do modelo tem ':', que a chave do cache não aceita.
            settings = Settings(_env_file=None, FAISS_INDEX_PATH=str(Path(folder) / 'index'))

            # O primeiro lote passa e o segundo falha, como uma queda do servidor no meio.
            failing_server = Mock()
            failing_server.embed_documents.side_effect = [[[1.0, 0.0]] * 32,
                                                          RuntimeError('Servidor indisponível')]
            with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=failing_server):
                with self.assertRaisesRegex(RuntimeError, 'Servidor indisponível'):
                    VectorDB(settings).create_faiss_index(str(source))
            self.assertEqual(len(failing_server.embed_documents.call_args_list[0].args[0]), 32)
            self.assertFalse((Path(settings.FAISS_INDEX_PATH) / 'index.faiss').exists())

            resumed = Mock()
            resumed.embed_documents.side_effect = TestEmbeddings().embed_documents
            with patch('src.services.vectorDB.OpenWebUIEmbeddings', return_value=resumed):
                VectorDB(settings).create_faiss_index(str(source))
                self.assertEqual(sent(resumed), 8)
                self.assertTrue((Path(settings.FAISS_INDEX_PATH) / 'index.faiss').exists())

                VectorDB(settings).create_faiss_index(str(source))
                self.assertEqual(sent(resumed), 8)


if __name__ == '__main__':
    unittest.main()
