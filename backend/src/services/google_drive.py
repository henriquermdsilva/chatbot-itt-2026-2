import json
import logging
import os
from pathlib import Path
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

FOLDER_MIME = 'application/vnd.google-apps.folder'
DOC_MIME = 'application/vnd.google-apps.document'
PDF_MIME = 'application/pdf'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class DriveService:
    def __init__(self, credentials_path: str, folder_id: str, download_path: str,
                 credentials_json: str = ''):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', folder_id):
            raise ValueError('GOOGLE_DRIVE_FOLDER_ID deve conter apenas o ID da pasta, nao a URL.')
        self.folder_id = folder_id
        self.download_path = Path(download_path)
        scopes = ['https://www.googleapis.com/auth/drive.readonly']
        if Path(credentials_path).is_file():
            self.creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=scopes,
            )
        else:
            credentials_json = credentials_json or os.getenv('GOOGLE_CREDENTIALS_JSON', '')
            if not credentials_json:
                raise FileNotFoundError(
                    'Configure GOOGLE_CREDENTIALS_PATH ou GOOGLE_CREDENTIALS_JSON e '
                    'compartilhe a pasta com o client_email da conta de servico.'
                )
            try:
                credentials = json.loads(credentials_json)
            except json.JSONDecodeError:
                raise ValueError('GOOGLE_CREDENTIALS_JSON deve conter um JSON valido.') from None
            self.creds = service_account.Credentials.from_service_account_info(credentials, scopes=scopes)
        self.service = build('drive', 'v3', credentials=self.creds)
        self.download_path.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> list[dict]:
        """Lista PDFs, Google Docs e Excel em todas as paginas e subpastas."""
        root = self.service.files().get(
            fileId=self.folder_id, fields='mimeType', supportsAllDrives=True,
        ).execute()
        if root['mimeType'] != FOLDER_MIME:
            raise ValueError('GOOGLE_DRIVE_FOLDER_ID nao aponta para uma pasta.')
        files = []
        folders = [self.folder_id]
        while folders:
            folder_id = folders.pop()
            page_token = None
            while True:
                result = self.service.files().list(
                    q=(f"'{folder_id}' in parents and trashed=false and "
                       f"(mimeType='{PDF_MIME}' or mimeType='{DOC_MIME}' or "
                       f"mimeType='{XLSX_MIME}' or mimeType='{FOLDER_MIME}')"),
                    pageSize=100,
                    pageToken=page_token,
                    fields='nextPageToken, files(id, name, mimeType)',
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                for file in result.get('files', []):
                    if file['mimeType'] == FOLDER_MIME:
                        folders.append(file['id'])
                    elif file['mimeType'] in (PDF_MIME, DOC_MIME, XLSX_MIME):
                        files.append(file)
                page_token = result.get('nextPageToken')
                if not page_token:
                    break
        return files

    def download_files(self) -> list[str]:
        """Baixa PDFs e exporta Google Docs como PDF para o leitor existente."""
        files = self.list_files()
        if not files:
            raise ValueError(
                'Nenhum PDF, Google Doc ou Excel encontrado na pasta e subpastas. '
                'Confira o ID e o acesso da conta de servico. O indice nao foi alterado.'
            )
        downloaded = []
        for file in files:
            # Nomes do Drive podem conter caminhos, caracteres Windows e duplicatas.
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', file['name']).strip(' .')[:120] or 'documento'
            file_id = file['id']
            if not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
                raise ValueError('ID de arquivo invalido retornado pelo Drive.')
            suffix = '.xlsx' if file['mimeType'] == XLSX_MIME else '.pdf'
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
            file_path = self.download_path / f'{name}--{file_id}{suffix}'
            if file['mimeType'] == DOC_MIME:
                request = self.service.files().export_media(fileId=file_id, mimeType=PDF_MIME)
            else:
                request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
            with file_path.open('wb') as output:
                downloader = MediaIoBaseDownload(output, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            logger.info('Download concluido: %s', file['name'])
            downloaded.append(str(file_path))
        return downloaded
