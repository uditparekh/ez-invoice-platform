"""Document-storage abstraction for retained invoice PDFs.

The hosted pilot keeps structured invoice data in the database and stores the
original PDF only for the configured review window. Local storage remains for
development; Supabase Storage is the hosted private-bucket option.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class StoredDocument:
    backend: str
    storage_key: str
    local_path: str
    source_path: str


def _safe_filename(filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    return safe_name or "invoice.pdf"


def _record_storage_key(target: Any) -> str:
    if isinstance(target, StoredDocument):
        return target.storage_key
    if isinstance(target, str):
        return target
    storage_key = getattr(target, "storage_key", "")
    if storage_key:
        return str(storage_key)
    local_path = getattr(target, "local_path", "")
    if local_path:
        return str(local_path)
    return str(target)


class LocalDocumentStorage:
    backend = "local"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        organization_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/pdf",
    ) -> StoredDocument:
        del content_type
        safe_name = _safe_filename(filename)
        destination = self.root / organization_id / f"{uuid.uuid4()}-{safe_name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return StoredDocument(
            backend=self.backend,
            storage_key=self.storage_key(destination),
            local_path=str(destination),
            source_path=str(destination),
        )

    def storage_key(self, path: Path | StoredDocument) -> str:
        if isinstance(path, StoredDocument):
            return path.storage_key
        try:
            return str(Path(path).relative_to(self.root))
        except ValueError:
            return Path(path).name

    def read(self, target: Any) -> bytes:
        path = Path(getattr(target, "local_path", "") or str(target))
        return path.read_bytes()

    def delete(self, target: Any) -> None:
        path_value = getattr(target, "local_path", "") or str(target)
        try:
            Path(path_value).unlink(missing_ok=True)
        except OSError:
            pass


class SupabaseDocumentStorage:
    backend = "supabase"

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        bucket: str,
        timeout_seconds: float = 20.0,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket = bucket.strip()
        self.timeout = httpx.Timeout(timeout_seconds)
        if not self.supabase_url or not self.service_role_key or not self.bucket:
            raise RuntimeError(
                "Supabase storage requires EZ_SUPABASE_URL, "
                "EZ_SUPABASE_SERVICE_ROLE_KEY, and EZ_SUPABASE_STORAGE_BUCKET."
            )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    def _object_url(self, key: str) -> str:
        encoded_key = quote(key, safe="/")
        return f"{self.supabase_url}/storage/v1/object/{self.bucket}/{encoded_key}"

    def save(
        self,
        organization_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/pdf",
    ) -> StoredDocument:
        safe_name = _safe_filename(filename)
        key = f"{organization_id}/{uuid.uuid4()}-{safe_name}"
        headers = {
            **self._headers,
            "Content-Type": content_type or "application/pdf",
            "x-upsert": "false",
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self._object_url(key), content=content, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase Storage upload failed ({response.status_code}): "
                f"{response.text[:240]}"
            )
        return StoredDocument(
            backend=self.backend,
            storage_key=key,
            local_path="",
            source_path=f"supabase://{self.bucket}/{key}",
        )

    def storage_key(self, target: Any) -> str:
        return _record_storage_key(target)

    def read(self, target: Any) -> bytes:
        key = _record_storage_key(target)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(self._object_url(key), headers=self._headers)
        if response.status_code == 404:
            raise FileNotFoundError(key)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase Storage download failed ({response.status_code}): "
                f"{response.text[:240]}"
            )
        return response.content

    def delete(self, target: Any) -> None:
        key = _record_storage_key(target)
        if not key:
            return
        delete_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    "DELETE",
                    delete_url,
                    headers={**self._headers, "Content-Type": "application/json"},
                    json={"prefixes": [key]},
                )
        except httpx.HTTPError:
            return
        if response.status_code in {200, 204, 404}:
            return


DocumentStorage = LocalDocumentStorage | SupabaseDocumentStorage


def build_document_storage(settings: Any) -> DocumentStorage:
    backend = str(getattr(settings, "storage_backend", "local") or "local").lower()
    if backend == "supabase":
        return SupabaseDocumentStorage(
            supabase_url=getattr(settings, "supabase_url", ""),
            service_role_key=getattr(settings, "supabase_service_role_key", ""),
            bucket=getattr(settings, "supabase_storage_bucket", ""),
            timeout_seconds=float(getattr(settings, "storage_timeout_seconds", 20.0)),
        )
    if backend == "local":
        return LocalDocumentStorage(Path(getattr(settings, "upload_directory")))
    raise RuntimeError(f"Unsupported document storage backend: {backend}")
