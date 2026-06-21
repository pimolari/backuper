"""
Google Cloud Storage client — unified real / mock implementation.

When ``config.USE_REAL_GCP`` is *True* the official ``google-cloud-storage``
SDK is used.  Otherwise a lightweight filesystem-backed mock is provided so
the application can run locally without GCP credentials.

Only this module knows about the real/mock distinction.  Every other layer
interacts exclusively through :class:`GCSClient`.
"""

import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend import config
from backend.common.logging import tech_logger


# ──────────────────────────────────────────────
#  Mock implementation (local filesystem backend)
# ──────────────────────────────────────────────

class _MockBlob:
    """Mimics ``google.cloud.storage.Blob``."""

    def __init__(self, bucket: "_MockBucket", name: str):
        self.bucket = bucket
        self.name = name
        self.metadata: dict = {}
        self.storage_class = "STANDARD"

    @property
    def _file_path(self) -> str:
        safe_name = self.name.replace("/", "_DIRSEP_")
        return os.path.join(self.bucket._bucket_path, safe_name)

    def upload_from_file(self, file_obj, **_kwargs) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "wb") as fh:
            fh.write(file_obj.read())

    def download_to_file(self, file_obj) -> None:
        if not os.path.exists(self._file_path):
            raise FileNotFoundError("Blob does not exist locally.")
        with open(self._file_path, "rb") as fh:
            file_obj.write(fh.read())

    def download_as_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.download_to_file(buf)
        buf.seek(0)
        return buf.read()

    def delete(self) -> None:
        if os.path.exists(self._file_path):
            os.remove(self._file_path)

    @property
    def size(self) -> int:
        if os.path.exists(self._file_path):
            return os.path.getsize(self._file_path)
        return 0

    @property
    def updated(self) -> datetime:
        if os.path.exists(self._file_path):
            return datetime.fromtimestamp(os.path.getmtime(self._file_path))
        return datetime.now(tz=timezone.utc)


class _MockBucket:
    """Mimics ``google.cloud.storage.Bucket``."""

    def __init__(self, client: "_MockStorageClient", name: str):
        self.client = client
        self.name = name

    @property
    def _bucket_path(self) -> str:
        return os.path.join(config.MOCK_STORAGE_DIR, self.name)

    def blob(self, blob_name: str) -> _MockBlob:
        return _MockBlob(self, blob_name)

    def list_blobs(self, prefix: str | None = None) -> List[_MockBlob]:
        if not os.path.exists(self._bucket_path):
            return []
        blobs: List[_MockBlob] = []
        for filename in os.listdir(self._bucket_path):
            if filename.startswith("."):
                continue
            blob_name = filename.replace("_DIRSEP_", "/")
            if prefix and not blob_name.startswith(prefix):
                continue
            blobs.append(_MockBlob(self, blob_name))
        return blobs


class _MockStorageClient:
    """Filesystem-backed GCS emulator."""

    def create_bucket(self, bucket_name: str, location: str | None = None) -> _MockBucket:
        bucket_path = os.path.join(config.MOCK_STORAGE_DIR, bucket_name)
        os.makedirs(bucket_path, exist_ok=True)
        meta_file = os.path.join(bucket_path, ".bucket_meta")
        with open(meta_file, "w") as fh:
            json.dump(
                {
                    "name": bucket_name,
                    "location": location or config.DEFAULT_REGION,
                    "created": datetime.now(tz=timezone.utc).isoformat(),
                },
                fh,
            )
        return _MockBucket(self, bucket_name)

    def get_bucket(self, bucket_name: str) -> _MockBucket:
        bucket_path = os.path.join(config.MOCK_STORAGE_DIR, bucket_name)
        if not os.path.exists(bucket_path):
            raise FileNotFoundError(f"Bucket {bucket_name} does not exist.")
        return _MockBucket(self, bucket_name)


# ──────────────────────────────────────────────
#  Public façade
# ──────────────────────────────────────────────

class GCSClient:
    """
    Thin wrapper that exposes the same interface regardless of whether the
    real GCP Cloud Storage or the local mock is used.
    """

    def __init__(self):
        if config.USE_REAL_GCP:
            from google.cloud import storage
            tech_logger.info("Initialising REAL GCS client")
            self._client = storage.Client()
        else:
            tech_logger.info("Initialising MOCK GCS client")
            self._client = _MockStorageClient()

    # ── bucket operations ──

    @staticmethod
    def generate_bucket_name(email: str, region: str) -> str:
        """
        Generate a GCS-compliant bucket name from an email + region.

        Rules: 3-63 chars, lowercase, numbers, hyphens.
        """
        clean = email.lower().strip()
        email_hash = hashlib.md5(clean.encode()).hexdigest()[:8]
        return f"backuper-{email_hash}-{region}"

    def create_user_bucket(
        self, email: str, region: str, storage_class: str
    ) -> str:
        """
        Create a new GCS bucket and return the generated bucket name.
        """
        bucket_name = self.generate_bucket_name(email, region)

        if config.USE_REAL_GCP:
            from google.cloud import storage
            try:
                bucket = storage.Bucket(self._client, name=bucket_name)
                bucket.storage_class = storage_class
                bucket.iam_configuration.public_access_prevention = "enforced"
                self._client.create_bucket(bucket, location=region)
                tech_logger.info(
                    "GCS: created bucket %s in %s (%s)",
                    bucket_name, region, storage_class,
                )
            except Exception as exc:
                suffix = str(uuid.uuid4())[:6]
                bucket_name = f"backuper-{suffix}-{region}"
                bucket = storage.Bucket(self._client, name=bucket_name)
                bucket.storage_class = storage_class
                bucket.iam_configuration.public_access_prevention = "enforced"
                self._client.create_bucket(bucket, location=region)
                tech_logger.warning(
                    "GCS: fallback bucket %s created (original error: %s)",
                    bucket_name, exc,
                )
        else:
            self._client.create_bucket(bucket_name, location=region)
            tech_logger.info(
                "MOCK-GCS: created bucket %s in %s (%s)",
                bucket_name, region, storage_class,
            )

        return bucket_name

    # ── blob operations ──

    def upload_file(
        self,
        bucket_name: str,
        file_obj,
        destination_blob_name: str,
        file_size: int | None = None,
    ) -> bool:
        """Upload a file object to GCS.  Returns *True* on success."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            if config.USE_REAL_GCP:
                blob.chunk_size = 10 * 1024 * 1024  # 10 MB — triggers resumable
                blob.upload_from_file(file_obj, size=file_size)
            else:
                blob.upload_from_file(file_obj)

            return True
        except Exception as exc:
            tech_logger.error("GCS upload error: %s", exc)
            return False

    def generate_signed_upload_url(
        self,
        bucket_name: str,
        blob_name: str,
        content_type: str = "application/octet-stream",
        expiration_seconds: int = 900,
    ) -> str | None:
        """
        Generate a V4 signed PUT URL so the browser can upload directly to
        GCS without routing the file body through Cloud Run.

        For the local mock this returns a sentinel URL pointing at the
        backend's ``/api/files/mock-upload`` endpoint so development works
        without GCP credentials.

        Returns the signed URL string, or *None* on failure.
        """
        try:
            if config.USE_REAL_GCP:
                from datetime import timedelta
                bucket = self._client.get_bucket(bucket_name)
                blob = bucket.blob(blob_name)
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(seconds=expiration_seconds),
                    method="PUT",
                    content_type=content_type,
                )
                tech_logger.info(
                    "GCS: generated signed upload URL for %s/%s",
                    bucket_name, blob_name,
                )
                return url
            else:
                # In mock mode return a local PUT endpoint that the backend
                # handles directly (no GCS credentials required).
                import urllib.parse
                params = urllib.parse.urlencode({
                    "bucket": bucket_name,
                    "blob": blob_name,
                })
                return f"/api/files/mock-upload?{params}"
        except Exception as exc:
            tech_logger.error("GCS signed URL error: %s", exc)
            return None

    def initiate_resumable_upload(
        self,
        bucket_name: str,
        blob_name: str,
        file_size: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Initiate a GCS resumable upload session.
        In production, returns the GCS session URI.
        In mock mode, returns a local temporary file path under mock_gcs/tmp.
        """
        try:
            if config.USE_REAL_GCP:
                bucket = self._client.get_bucket(bucket_name)
                blob = bucket.blob(blob_name)
                session_url = blob.create_resumable_upload_session(
                    content_type=content_type,
                    size=file_size,
                )
                tech_logger.info(
                    "GCS: initiated resumable upload session for %s/%s",
                    bucket_name, blob_name,
                )
                return session_url
            else:
                temp_id = str(uuid.uuid4())
                temp_file_path = os.path.join(config.MOCK_STORAGE_DIR, "tmp", temp_id)
                tech_logger.info(
                    "MOCK GCS: initiated resumable upload for %s/%s at %s",
                    bucket_name, blob_name, temp_file_path,
                )
                return temp_file_path
        except Exception as exc:
            tech_logger.error("GCS initiate resumable upload error: %s", exc)
            raise exc


    def mock_upload_from_stream(
        self,
        bucket_name: str,
        blob_name: str,
        file_obj,
    ) -> bool:
        """Used by the mock-upload endpoint in local development."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_file(file_obj)
            return True
        except Exception as exc:
            tech_logger.error("MOCK GCS upload error: %s", exc)
            return False

    def delete_file(self, bucket_name: str, blob_name: str) -> bool:
        """Delete a single blob.  Returns *True* on success."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            bucket.blob(blob_name).delete()
            return True
        except Exception as exc:
            tech_logger.error("GCS delete error: %s", exc)
            return False

    def get_file_content(self, bucket_name: str, blob_name: str) -> Optional[bytes]:
        """Download blob data and return as *bytes* (or *None* on failure)."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if config.USE_REAL_GCP:
                return blob.download_as_bytes()

            buf = io.BytesIO()
            blob.download_to_file(buf)
            buf.seek(0)
            return buf.read()
        except Exception as exc:
            tech_logger.error("GCS download error: %s", exc)
            return None

    def list_bucket_blobs(self, bucket_name: str) -> List[Dict[str, Any]]:
        """List all blobs in *bucket_name*.  Used by the cache-sync flow."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            blobs = bucket.list_blobs()
            return [
                {
                    "name": os.path.basename(blob.name),
                    "path": blob.name,
                    "size": blob.size,
                    "updated": (
                        blob.updated.isoformat()
                        if hasattr(blob.updated, "isoformat")
                        else str(blob.updated)
                    ),
                    "storage_class": getattr(blob, "storage_class", "STANDARD"),
                }
                for blob in blobs
            ]
        except Exception as exc:
            tech_logger.error("GCS list-blobs error: %s", exc)
            return []

    def delete_folder(self, bucket_name: str, folder_prefix: str) -> bool:
        """Delete all blobs under *folder_prefix/* recursively."""
        try:
            bucket = self._client.get_bucket(bucket_name)
            prefix = folder_prefix.strip("/")
            if not prefix:
                return False
            prefix += "/"

            if config.USE_REAL_GCP:
                for blob in bucket.list_blobs(prefix=prefix):
                    blob.delete()
            else:
                for blob in bucket.list_blobs():
                    if blob.name == prefix or blob.name.startswith(prefix):
                        blob.delete()

            return True
        except Exception as exc:
            tech_logger.error("GCS delete-folder error: %s", exc)
            return False
