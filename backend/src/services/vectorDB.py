from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path
from tempfile import TemporaryDirectory
from langchain_core.documents import Document
from openpyxl.utils.cell import get_column_letter, range_boundaries
import re

from ..config import Settings
from .google_drive import DriveService
from .openwebui import OpenWebUIEmbeddings
from .spreadsheets import normalize, workbook_documents


class IndexNotFoundError(ValueError):
    pass


class AmbiguousPersonError(ValueError):
    def __init__(self, names: list[str]):
        super().__init__(f'Mais de uma pessoa corresponde a pergunta: {len(names)}')
        self.names = names


def _student_lookup(docs, lookup):
    if lookup == 'resumo_cursos':
        return [d for d in docs if d.metadata['kind'] == 'resumo_cursos']
    if lookup == 'cursos_comentados':
        evaluations = [d for d in docs if d.metadata['kind'] == 'avaliacao']
        selected = [d for d in evaluations if d.metadata['curso_comentado']]
        evidence = evaluations
        empty = 'Nenhum curso com comentário do aluno entre as atividades registradas.'
    elif lookup == 'semanas_com_falta':
        evidence = [d for d in docs if d.metadata['kind'] == 'semana']
        selected = [d for d in evidence if d.metadata['frequencia'] in ('falta', 'faltou', 'ausente')]
        empty = 'Nenhuma falta registrada nas semanas da ficha. Semanas em branco têm presença desconhecida.'
    else:
        latest = {
            'ultima_interacao': ('interacao', None),
            'ultima_nota_mentor': ('interacao', 'mentor'),
            'ultima_nota_coordenacao': ('interacao', 'coordenacao'),
            'ultima_semana_com_horas': ('semana', 'horas'),
        }
        if lookup not in latest:
            return []
        kind, required = latest[lookup]
        dated = [d for d in docs if d.metadata['kind'] == kind and d.metadata['data']
                 and (not required or d.metadata[required])]
        last = max((d.metadata['data'] for d in dated), default=None)
        return [d for d in dated if d.metadata['data'] == last]
    if selected or not evidence:
        return selected
    # A ausência é verificada sobre todos os registros, inclusive os que a busca vetorial omitiria.
    result = []
    for sheet in dict.fromkeys(d.metadata['sheet'] for d in evidence):
        rows = [d for d in evidence if d.metadata['sheet'] == sheet]
        bounds = [range_boundaries(d.metadata['cells']) for d in rows]
        left, top = min(r[0] for r in bounds), min(r[1] for r in bounds)
        right, bottom = max(r[2] for r in bounds), max(r[3] for r in bounds)
        cells = f'{get_column_letter(left)}{top}:{get_column_letter(right)}{bottom}'
        metadata = {**rows[0].metadata, 'cells': cells}
        result.append(Document(page_content=empty, metadata=metadata))
    return result


class VectorDB:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedder = OpenWebUIEmbeddings(settings) if settings.LLM_PROVIDER == 'openwebui' else GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GOOGLE_API_KEY
        )

    def query(self, message: str, *, student: str = "", lookup: str = "") -> list[Document]:
        # A pasta pode existir vazia: no Docker, o volume do índice começa assim.
        if not (Path(self.settings.FAISS_INDEX_PATH) / 'index.faiss').exists():
            raise IndexNotFoundError("O índice FAISS não foi encontrado. " \
            "Certifique-se de que o índice foi criado e salvo corretamente.")
        
        vectorstore = FAISS.load_local(self.settings.FAISS_INDEX_PATH, self.embedder, allow_dangerous_deserialization=True)

        # Fichas de alunos usam formularios parecidos: um nome de arquivo explicito
        # deve restringir a busca antes de comparar os trechos por similaridade.
        student_name = normalize(student)
        query = f' {student_name or normalize(message)} '
        student_docs = {}
        matches = {}
        people = {}
        people_sources = {}
        # ponytail: varredura linear de titulos; criar catalogo se o indice crescer.
        for doc_id in vectorstore.index_to_docstore_id.values():
            doc = vectorstore.docstore.search(doc_id)
            # A busca devolve um texto de erro se o ID não existir (índice inconsistente).
            if not isinstance(doc, Document):
                continue
            source = doc.metadata.get('source', '')
            if student and not source.lower().endswith('.xlsx'):
                continue
            if doc.metadata.get('kind') and lookup:
                student_docs.setdefault(source, []).append(doc)
            name = doc.metadata.get('owner') or Path(source).stem.split('--')[0]
            title = normalize(name)
            exact = title == student_name if student_name else f' {title} ' in query
            if len(title) >= 5 and exact:
                matches[source] = len(title)
            # Planilhas individuais têm o nome da pessoa: conta quantas palavras iniciais
            # do nome aparecem na pergunta ("Pedro" = 1, "Pedro Henrique" = 2).
            words = title.split()
            if source.lower().endswith('.xlsx') and words and len(words[0]) >= 3 and words[0].isalpha():
                matched = 0
                while matched < len(words) and f' {" ".join(words[:matched + 1])} ' in query:
                    matched += 1
                if matched and (not student or matched == len(student_name.split())):
                    people[name] = max(matched, people.get(name, 0))
                    people_sources.setdefault(name, set()).add(source)

        if not matches and people:
            best = max(people.values())
            candidates = sorted(name for name, matched in people.items() if matched == best)
            if len(candidates) > 1:
                raise AmbiguousPersonError(candidates)
            matches = {source: best for source in people_sources[candidates[0]]}

        if matches:
            longest = max(matches.values())
            sources = {source for source, length in matches.items() if length == longest}
            if (student or lookup) and len(sources) != 1:
                return []
            if lookup:
                return _student_lookup(student_docs.get(next(iter(sources)), []), lookup)
            return vectorstore.similarity_search(
                message, k=4, filter=lambda metadata: metadata.get('source') in sources,
                fetch_k=vectorstore.index.ntotal,
            )

        if student or lookup:
            return []

        retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
        
        docs = retriever.invoke(message)

        return docs
        
    def create_faiss_index(self, parent_folder : str):

        folder_path = Path(parent_folder)
        if not folder_path.exists():
            raise ValueError(f"O diretório {parent_folder} não existe. Verifique o caminho e tente novamente.")


        docs = []
        files = [folder_path] if folder_path.is_file() else folder_path.iterdir()
        for file_path in files:
            if not file_path.is_file() or file_path.suffix.lower() not in ('.pdf', '.xlsx'):
                continue
            try:
                if file_path.suffix.lower() == '.xlsx':
                    docs.extend(workbook_documents(file_path))
                else:
                    loader = PyMuPDFLoader(str(file_path))
                    docs.extend(loader.load())
                print(f"Carregado com sucesso o arquivo {file_path.name}")

            except Exception as e:
                raise ValueError(f'Erro ao carregar {file_path.name}. O indice nao foi alterado.') from e

        print(f"Total de documentos carregados: {len(docs)}")

        if not docs:
            raise ValueError('Nenhum documento com texto foi encontrado. O indice nao foi alterado.')
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )

        split_docs = []
        for doc in docs:
            if doc.metadata.get('kind'):
                split_docs.append(doc)
            else:
                split_docs.extend(splitter.split_documents([doc]))
        for doc in split_docs:
            heading = f"Arquivo: {Path(doc.metadata['source']).name}\n"
            if doc.metadata.get('sheet'):
                heading += f"Aba: {doc.metadata['sheet']}\n"
            if doc.metadata.get('kind'):
                heading += f"Aluno: {doc.metadata['owner']}\n"
            if doc.metadata.get('cells'):
                heading += f"Células: {doc.metadata['cells']}\n"
            doc.page_content = heading + doc.page_content

        if not split_docs:
            raise ValueError('Nenhum documento com texto foi encontrado. O indice nao foi alterado.')

        cached_embedder = self._cached_embedder()
        texts = [doc.page_content for doc in split_docs]
        for start in range(0, len(texts), 32):
            cached_embedder.embed_documents(texts[start:start + 32])
            print(f'Embeddings: {min(start + 32, len(texts))} de {len(texts)} trechos', flush=True)

        vectorstore = FAISS.from_documents(split_docs, cached_embedder)

        vectorstore.save_local(self.settings.FAISS_INDEX_PATH)

    def _cached_embedder(self):
        # Dentro da pasta do índice para usar o mesmo volume no Docker. Cada modelo
        # tem seu namespace, e a chave do LocalFileStore não aceita caracteres como ':'.
        if self.settings.LLM_PROVIDER == 'openwebui':
            model = self.settings.OPENWEBUI_EMBEDDING_MODEL
        else:
            model = 'gemini-embedding-001'
        namespace = re.sub(r'[^a-zA-Z0-9_.-]', '_', model) + '-'
        store = LocalFileStore(Path(self.settings.FAISS_INDEX_PATH) / 'embeddings_cache')
        return CacheBackedEmbeddings.from_bytes_store(self.embedder, store, namespace=namespace)


    def refresh_knowledge_base(self):
        """
        Método Mestre: Baixa do Drive e recria o índice.
        """
        # 1. Configurar caminhos
        # Vamos assumir que data/ fica na raiz do backend
        if not self.settings.GOOGLE_DRIVE_FOLDER_ID:
            self.create_faiss_index(self.settings.local_data_path)
            return {"status": "success", "message": "PDFs locais indexados com sucesso!"}

        # Cada sincronizacao usa somente os arquivos atuais; PDFs locais ficam intactos.
        with TemporaryDirectory(prefix='itt-drive-') as download_path:
            print("Iniciando download do Google Drive...")
            drive_service = DriveService(
                credentials_path=self.settings.GOOGLE_CREDENTIALS_PATH,
                folder_id=self.settings.GOOGLE_DRIVE_FOLDER_ID,
                download_path=download_path,
                credentials_json=self.settings.GOOGLE_CREDENTIALS_JSON.get_secret_value(),
            )
            drive_service.download_files()
            print("Recriando indice vetorial...")
            self.create_faiss_index(download_path)
        
        return {"status": "success", "message": "Base de conhecimento atualizada com sucesso!"}
