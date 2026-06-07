import os
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from src import config

# ==========================================
# MOCK GCS IMPLEMENTATION
# ==========================================

class MockBlob:
    def __init__(self, bucket: 'MockBucket', name: str):
        self.bucket = bucket
        self.name = name
        self.metadata = {}
        self.storage_class = "STANDARD"

    @property
    def _file_path(self):
        # Escape path traversal and build safe local path
        safe_name = self.name.replace("/", "_DIRSEP_")
        return os.path.join(self.bucket._bucket_path, safe_name)

    def upload_from_file(self, file_obj):
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "wb") as f:
            f.write(file_obj.read())

    def download_to_file(self, file_obj):
        if not os.path.exists(self._file_path):
            raise Exception("Blob does not exist locally.")
        with open(self._file_path, "rb") as f:
            file_obj.write(f.read())

    def delete(self):
        if os.path.exists(self._file_path):
            os.remove(self._file_path)

    @property
    def size(self):
        if os.path.exists(self._file_path):
            return os.path.getsize(self._file_path)
        return 0

    @property
    def updated(self):
        if os.path.exists(self._file_path):
            mtime = os.path.getmtime(self._file_path)
            return datetime.fromtimestamp(mtime)
        return datetime.utcnow()

class MockBucket:
    def __init__(self, client: 'MockStorageClient', name: str):
        self.client = client
        self.name = name

    @property
    def _bucket_path(self):
        return os.path.join(config.MOCK_STORAGE_DIR, self.name)

    def blob(self, blob_name: str) -> MockBlob:
        return MockBlob(self, blob_name)

    def list_blobs(self) -> List[MockBlob]:
        if not os.path.exists(self._bucket_path):
            return []
        blobs = []
        for filename in os.listdir(self._bucket_path):
            if filename.startswith("."):
                continue
            # Restore directory separators
            blob_name = filename.replace("_DIRSEP_", "/")
            blobs.append(MockBlob(self, blob_name))
        return blobs

class MockStorageClient:
    def __init__(self):
        pass

    def create_bucket(self, bucket_name: str, location: str = None) -> MockBucket:
        bucket_path = os.path.join(config.MOCK_STORAGE_DIR, bucket_name)
        os.makedirs(bucket_path, exist_ok=True)
        # Store bucket metadata locally in a simple file inside the bucket directory
        meta_file = os.path.join(bucket_path, ".bucket_meta")
        with open(meta_file, "w") as f:
            json.dump({
                "name": bucket_name,
                "location": location or config.DEFAULT_REGION,
                "created": datetime.utcnow().isoformat()
            }, f)
        return MockBucket(self, bucket_name)

    def get_bucket(self, bucket_name: str) -> MockBucket:
        bucket_path = os.path.join(config.MOCK_STORAGE_DIR, bucket_name)
        if not os.path.exists(bucket_path):
            raise Exception("Bucket does not exist.")
        return MockBucket(self, bucket_name)

    def list_buckets(self) -> List[MockBucket]:
        if not os.path.exists(config.MOCK_STORAGE_DIR):
            return []
        buckets = []
        for d in os.listdir(config.MOCK_STORAGE_DIR):
            full_path = os.path.join(config.MOCK_STORAGE_DIR, d)
            if os.path.isdir(full_path):
                buckets.append(MockBucket(self, d))
        return buckets

# ==========================================
# GCS CLIENT INTERFACE
# ==========================================

class GCSClient:
    def __init__(self):
        if config.USE_REAL_GCP:
            from google.cloud import storage
            print("Using REAL Google Cloud Storage Client")
            self._client = storage.Client()
        else:
            print("Using MOCK Google Cloud Storage Client")
            self._client = MockStorageClient()

    def generate_bucket_name(self, email: str, region: str) -> str:
        """
        Generates a unique bucket name that conforms to GCS requirements.
        Rules: 3-63 characters, lowercase, numbers, hyphens.
        """
        clean_email = email.lower().strip()
        email_hash = hashlib.md5(clean_email.encode()).hexdigest()[:8]
        bucket_name = f"backuper-{email_hash}-{region}"
        return bucket_name

    def create_user_bucket(self, email: str, region: str, storage_class: str) -> str:
        """
        Creates a new GCS bucket in the selected region with the specified storage class.
        Returns the generated bucket name.
        """
        bucket_name = self.generate_bucket_name(email, region)
        
        if config.USE_REAL_GCP:
            from google.cloud import storage
            try:
                bucket = storage.Bucket(self._client, name=bucket_name)
                bucket.storage_class = storage_class
                self._client.create_bucket(bucket, location=region)
                print(f"GCS: Created real bucket {bucket_name} in {region} with class {storage_class}")
            except Exception as e:
                import uuid
                suffix = str(uuid.uuid4())[:6]
                bucket_name = f"backuper-{suffix}-{region}"
                bucket = storage.Bucket(self._client, name=bucket_name)
                bucket.storage_class = storage_class
                self._client.create_bucket(bucket, location=region)
                print(f"GCS: Created real fallback bucket {bucket_name} due to error: {e}")
        else:
            self._client.create_bucket(bucket_name, location=region)
            print(f"MOCK-GCS: Created mock bucket {bucket_name} in {region} with class {storage_class}")
            
        return bucket_name

    def upload_file(self, bucket_name: str, file_obj, destination_blob_name: str) -> bool:
        """
        Uploads a file object to GCS.
        """
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_file(file_obj)
            return True
        except Exception as e:
            print(f"GCS Upload Error: {e}")
            return False

    def delete_file(self, bucket_name: str, blob_name: str) -> bool:
        """
        Deletes an object from GCS.
        """
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.delete()
            return True
        except Exception as e:
            print(f"GCS Delete Error: {e}")
            return False

    def get_file_content(self, bucket_name: str, blob_name: str) -> Optional[bytes]:
        """
        Downloads object data from GCS and returns as bytes.
        """
        try:
            bucket = self._client.get_bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            if config.USE_REAL_GCP:
                return blob.download_as_bytes()
            else:
                import io
                f = io.BytesIO()
                blob.download_to_file(f)
                f.seek(0)
                return f.read()
        except Exception as e:
            print(f"GCS Download Error: {e}")
            return None

    def list_bucket_blobs(self, bucket_name: str) -> List[Dict[str, Any]]:
        """
        Lists all blobs in the bucket. Useful for force syncing cache.
        """
        try:
            bucket = self._client.get_bucket(bucket_name)
            blobs = bucket.list_blobs()
            
            result = []
            for blob in blobs:
                result.append({
                    "name": os.path.basename(blob.name),
                    "path": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat() if hasattr(blob.updated, 'isoformat') else str(blob.updated),
                    "storage_class": getattr(blob, 'storage_class', 'STANDARD')
                })
            return result
        except Exception as e:
            print(f"GCS List Blobs Error: {e}")
            return []
