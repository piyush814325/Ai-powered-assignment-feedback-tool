import os
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from supabase import Client, create_client


class FileStorage(Protocol):
    def save(self, filename: str, content: bytes, content_type: str) -> str: ...

    def read(self, object_key: str) -> bytes: ...

    def stream(self, object_key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]: ...

    def delete(self, object_key: str) -> None: ...

    def signed_url(self, object_key: str, expires_in: int = 60) -> str: ...


class FileCleanupError(RuntimeError):
    pass


def delete_storage_objects(storage: FileStorage, object_keys: Iterable[str]) -> None:
    errors: list[Exception] = []
    for object_key in dict.fromkeys(object_keys):
        try:
            storage.delete(object_key)
        except Exception as error:
            errors.append(error)
    if errors:
        raise FileCleanupError(
            f"{len(errors)} stored file(s) could not be removed"
        ) from errors[0]


class SupabaseStorage:
    def __init__(
        self,
        client: Client,
        bucket: str,
        max_upload_bytes: int,
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.max_upload_bytes = max_upload_bytes

    def save(self, filename: str, content: bytes, content_type: str) -> str:
        if len(content) > self.max_upload_bytes:
            raise ValueError(f"Uploaded file exceeds the {self.max_upload_bytes}-byte limit")
        suffix = Path(filename).suffix.lower()
        object_key = f"submissions/{uuid.uuid4().hex}{suffix}"
        self.client.storage.from_(self.bucket).upload(
            object_key,
            content,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        return object_key

    def read(self, object_key: str) -> bytes:
        return self.client.storage.from_(self.bucket).download(object_key)

    def stream(self, object_key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        content = self.read(object_key)
        for offset in range(0, len(content), chunk_size):
            yield content[offset : offset + chunk_size]

    def delete(self, object_key: str) -> None:
        self.client.storage.from_(self.bucket).remove([object_key])

    def signed_url(self, object_key: str, expires_in: int = 60) -> str:
        response = self.client.storage.from_(self.bucket).create_signed_url(object_key, expires_in)
        signed_url = response.get("signedURL")
        if signed_url is None:
            raise RuntimeError("Supabase did not return a signed URL")
        return signed_url


_storage: SupabaseStorage | None = None


def get_storage() -> SupabaseStorage:
    global _storage
    if _storage is None:
        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        bucket = os.getenv("SUPABASE_BUCKET", "").strip()
        if not supabase_url or not service_role_key or not bucket:
            raise RuntimeError(
                "SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and SUPABASE_BUCKET are required for file storage"
            )
        max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        _storage = SupabaseStorage(
            create_client(supabase_url, service_role_key),
            bucket,
            max_upload_bytes,
        )
    return _storage
