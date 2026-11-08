"""Execute no backend: python -m src.index_documents [pasta-ou-pdf | --drive]."""

import argparse
from .config import Settings
from .services.vectorDB import VectorDB


def main():
    parser = argparse.ArgumentParser(description='Indexa documentos locais ou do Google Drive para o chatbot.')
    parser.add_argument('path', nargs='?', help='Pasta com PDFs/Excel ou um arquivo PDF/XLSX')
    parser.add_argument('--drive', action='store_true', help='Baixa e indexa a pasta GOOGLE_DRIVE_FOLDER_ID')
    args = parser.parse_args()
    if args.drive and args.path:
        parser.error('Use --drive ou um caminho local, nao os dois.')
    settings = Settings()
    if args.drive and not settings.GOOGLE_DRIVE_FOLDER_ID:
        parser.error('Defina GOOGLE_DRIVE_FOLDER_ID no backend/.test.env.')
    database = VectorDB(settings)
    if args.drive:
        database.refresh_knowledge_base()
    else:
        database.create_faiss_index(args.path or settings.local_data_path)
    print(f'Indice salvo em: {settings.FAISS_INDEX_PATH}')


if __name__ == '__main__':
    main()
