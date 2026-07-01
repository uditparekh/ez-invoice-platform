"""Local object-storage abstraction used until cloud blob storage is configured."""

from __future__ import annotations

import re
import uuid
from pathlib import Path


class LocalDocumentStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, organization_id: str, filename: str, content: bytes) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
        safe_name = safe_name or "invoice.pdf"
        destination = self.root / organization_id / f"{uuid.uuid4()}-{safe_name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    def storage_key(self, path: Path) -> str:
        try:
            return str(Path(path).relative_to(self.root))
        except ValueError:
            return Path(path).name

    def delete(self, path: Path) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
