import os
import json
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

# Load config
from backend import config

class MockKey:
    def __init__(self, kind: str, id_or_name: Any):
        self.kind = kind
        self.id_or_name = id_or_name

    @property
    def name(self):
        return self.id_or_name if isinstance(self.id_or_name, str) else None

    @property
    def id(self):
        return self.id_or_name if isinstance(self.id_or_name, int) else None

    def __repr__(self):
        return f"MockKey({self.kind}, {self.id_or_name})"

class MockEntity(dict):
    def __init__(self, key: MockKey, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._key = key

    @property
    def key(self):
        return self._key

class MockQuery:
    def __init__(self, client: 'MockDatastoreClient', kind: str):
        self.client = client
        self.kind = kind
        self.filters = []

    def add_filter(self, property_name: str, operator: str, value: Any):
        self.filters.append((property_name, operator, value))
        return self

    def fetch(self) -> List[MockEntity]:
        db = self.client._read_db()
        entities = []
        for key_str, data in db.items():
            # key_str is kind:id_or_name
            kind, _, id_or_name = key_str.partition(":")
            if kind != self.kind:
                continue

            # check id type
            if id_or_name.isdigit():
                id_or_name = int(id_or_name)

            key = MockKey(kind, id_or_name)
            entity = MockEntity(key, data)

            # Apply filters
            match = True
            for prop, op, val in self.filters:
                if prop not in entity:
                    match = False
                    break
                
                actual_val = entity[prop]
                if op == "=":
                    if actual_val != val:
                        match = False
                        break
                elif op == ">":
                    if actual_val <= val:
                        match = False
                        break
                elif op == "<":
                    if actual_val >= val:
                        match = False
                        break
                else:
                    # Generic operator match
                    if actual_val != val:
                        match = False
                        break

            if match:
                entities.append(entity)

        return entities

class MockDatastoreClient:
    def __init__(self):
        self.db_path = config.MOCK_DATASTORE_FILE
        if not os.path.exists(self.db_path):
            self._write_db({})

    def _read_db(self) -> Dict[str, Any]:
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_db(self, db: Dict[str, Any]):
        with open(self.db_path, "w") as f:
            json.dump(db, f, indent=2)

    def key(self, kind: str, id_or_name: Any = None) -> MockKey:
        if id_or_name is None:
            # Generate a numeric ID
            id_or_name = int(uuid.uuid4().int >> 64)
        return MockKey(kind, id_or_name)

    def get(self, key: MockKey) -> Optional[MockEntity]:
        db = self._read_db()
        key_str = f"{key.kind}:{key.id_or_name}"
        data = db.get(key_str)
        if data:
            return MockEntity(key, data)
        return None

    def put(self, entity: MockEntity):
        db = self._read_db()
        key_str = f"{entity.key.kind}:{entity.key.id_or_name}"
        db[key_str] = dict(entity)
        self._write_db(db)

    def delete(self, key: MockKey):
        db = self._read_db()
        key_str = f"{key.kind}:{key.id_or_name}"
        if key_str in db:
            del db[key_str]
            self._write_db(db)

    def query(self, kind: str) -> MockQuery:
        return MockQuery(self, kind)

# GCS Mocks
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
