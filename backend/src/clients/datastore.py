import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from src import config

# ==========================================
# MOCK DATASTORE IMPLEMENTATION
# ==========================================

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

# ==========================================
# DATASTORE CLIENT INTERFACE
# ==========================================

class DatastoreClient:
    def __init__(self, db_name="backuper-db"):
        
        if config.USE_REAL_GCP:
            from google.cloud import datastore
            print("Using REAL Google Cloud Datastore Client")
            self._client = datastore.Client(database=db_name)
            
        else:
            print("Using MOCK Datastore Client")
            self._client = MockDatastoreClient()

    def get_client(self):
        return self._client

    def key(self, kind: str, id_or_name: Any = None):
        return self._client.key(kind, id_or_name)

    def get(self, key):
        return self._client.get(key)

    def put(self, entity):
        return self._client.put(entity)

    def delete(self, key):
        return self._client.delete(key)

    def query(self, kind: str):
        return self._client.query(kind)

    def create_entity(self, key, data: Dict[str, Any]):
        """
        Creates an appropriate Entity instance based on whether real or mock Datastore is used.
        """
        if config.USE_REAL_GCP:
            from google.cloud import datastore
            entity = datastore.Entity(key=key)
            entity.update(data)
            return entity
        else:
            return MockEntity(key, data)
