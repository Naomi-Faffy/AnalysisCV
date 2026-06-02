import os
from typing import Optional

import requests


class BlobStorageClient:
    def __init__(self):
        self.token = os.getenv('BLOB_READ_WRITE_TOKEN', '').strip()
        self.base_url = os.getenv('VERCEL_BLOB_BASE_URL', 'https://blob.vercel-storage.com').rstrip('/')

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.token}'
        }

    def _blob_url(self, blob_path: str) -> str:
        safe_path = str(blob_path).strip('/').replace(' ', '%20')
        return f"{self.base_url}/{safe_path}"

    def download_file(self, blob_path: str, local_path: str, timeout: int = 25) -> bool:
        if not self.enabled:
            return False

        try:
            response = requests.get(self._blob_url(blob_path), headers=self._headers(), timeout=timeout)
            if response.status_code != 200:
                return False

            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as file_obj:
                file_obj.write(response.content)
            return True
        except Exception as error:
            print(f"Blob download failed for {blob_path}: {error}")
            return False

    def upload_file(
        self,
        blob_path: str,
        local_path: str,
        content_type: str = 'application/octet-stream',
        timeout: int = 40
    ) -> bool:
        if not self.enabled or not os.path.exists(local_path):
            return False

        try:
            with open(local_path, 'rb') as file_obj:
                data = file_obj.read()

            headers = self._headers()
            headers['Content-Type'] = content_type
            response = requests.put(self._blob_url(blob_path), headers=headers, data=data, timeout=timeout)
            return response.status_code in [200, 201]
        except Exception as error:
            print(f"Blob upload failed for {blob_path}: {error}")
            return False

    def get_status_message(self) -> Optional[str]:
        if self.enabled:
            return 'Vercel Blob sync enabled'
        return 'Vercel Blob sync disabled (BLOB_READ_WRITE_TOKEN missing)'