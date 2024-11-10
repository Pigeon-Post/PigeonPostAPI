# database/google_drive.py
from typing import Optional, Dict, Any, List
import os
from dotenv import load_dotenv
from config.config import Config
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload 

load_dotenv()

class GoogleDriveUploader:
    def __init__(self):
        private_key = os.getenv("PRIVATE_KEY")
        if private_key:
            private_key = private_key.replace('\\n', '\n')
            private_key = private_key.strip('"\'')

        self.service_account_info = {
            "type": os.getenv("SERVICE_ACCOUNT_TYPE"),
            "project_id": os.getenv("PROJECT_ID"),
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": private_key,
            "client_email": os.getenv("CLIENT_EMAIL"),
            "client_id": os.getenv("CLIENT_ID"),
            "auth_uri": os.getenv("AUTH_URI"),
            "token_uri": os.getenv("TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
            "universe_domain": os.getenv("UNIVERSE_DOMAIN")
        }
        
        self.SCOPES = ['https://www.googleapis.com/auth/drive']
        self.creds = service_account.Credentials.from_service_account_info(
            self.service_account_info,
            scopes=self.SCOPES
        )
        self.service = build('drive', 'v3', credentials=self.creds)

    def create_folder(self, folder_name: str) -> Optional[str]:
        """Create a folder in Google Drive and return its ID"""
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            file = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            return file.get('id')
        except Exception as e:
            print(f"Error creating folder: {str(e)}")
            return None

    def share_file(self, file_id: str, email: str = None) -> None:
        """Share the file with specific email or make it viewable by anyone with the link"""
        try:
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            
            if email:
                permission.update({
                    'type': 'user',
                    'emailAddress': email
                })

            self.service.permissions().create(
                fileId=file_id,
                body=permission,
                fields='id',
                sendNotificationEmail=False
            ).execute()
        except Exception as e:
            print(f"Error sharing file: {str(e)}")

    def upload_stream(self, content_stream, filename: str, mime_type: str, folder_id: Optional[str] = None, email: Optional[str] = None) -> Dict[str, Any]:
        """Upload a stream directly to Google Drive and share it"""
        try:
            file_metadata = {
                'name': filename
            }
            
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaIoBaseUpload(
                content_stream,
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            # Share the file
            self.share_file(file.get('id'), email)

            return {
                "status": "success",
                "file_id": file.get('id'),
                "web_link": file.get('webViewLink'),
                "message": f"File uploaded successfully to Google Drive and shared"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to upload to Google Drive: {str(e)}"
            }

    def upload_batch(self, files: List[Dict[str, Any]], folder_id: Optional[str] = None, email: Optional[str] = None) -> Dict[str, Any]:
        """Upload multiple files to Google Drive"""
        try:
            results = []
            for file_info in files:
                result = self.upload_stream(
                    file_info['content'],
                    file_info['filename'],
                    file_info['mime_type'],
                    folder_id,
                    email
                )
                results.append(result)

            return {
                "status": "success",
                "results": results,
                "message": "All files uploaded successfully"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to upload batch: {str(e)}"
            }