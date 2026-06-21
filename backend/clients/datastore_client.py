"""
Google Cloud Datastore client — unified real / mock implementation.

When ``config.USE_REAL_GCP`` is *True* the official ``google-cloud-datastore``
SDK is used.  Otherwise a lightweight JSON-file-backed mock is provided so
the application can run locally without GCP credentials.

Only this module knows about the real/mock distinction.  Every other layer
interacts exclusively through :class:`DatastoreClient`.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend import config
from backend.common.logging import tech_logger


# ──────────────────────────────────────────────
#  Mock implementation (local JSON file backend)
# ──────────────────────────────────────────────

class _MockKey:
    """Mimics ``google.cloud.datastore.Key``."""

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
        return f"_MockKey({self.kind}, {self.id_or_name})"


class _MockEntity(dict):
    """Mimics ``google.cloud.datastore.Entity``."""

    def __init__(self, key: _MockKey, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._key = key

    @property
    def key(self):
        return self._key


class _MockQuery:
    """Mimics ``google.cloud.datastore.Query``."""

    def __init__(self, client: "_MockDatastoreClient", kind: str):
        self.client = client
        self.kind = kind
        self.filters: List[tuple] = []

    def add_filter(self, property_name: str, operator: str, value: Any):
        self.filters.append((property_name, operator, value))
        return self

    def fetch(self) -> List[_MockEntity]:
        db = self.client._read_db()
        entities: List[_MockEntity] = []

        for key_str, data in db.items():
            kind, _, id_or_name = key_str.partition(":")
            if kind != self.kind:
                continue

            if id_or_name.isdigit():
                id_or_name = int(id_or_name)

            key = _MockKey(kind, id_or_name)
            entity = _MockEntity(key, data)

            if self._matches(entity):
                entities.append(entity)

        return entities

    # ── private ──

    def _matches(self, entity: _MockEntity) -> bool:
        for prop, op, val in self.filters:
            actual = entity.get(prop)
            if actual is None:
                return False
            if op == "=" and actual != val:
                return False
            if op == ">" and actual <= val:
                return False
            if op == "<" and actual >= val:
                return False
        return True


class _MockDatastoreClient:
    """File-backed Datastore emulator."""

    def __init__(self):
        self.db_path = config.MOCK_DATASTORE_FILE
        if not os.path.exists(self.db_path):
            self._write_db({})

    def _read_db(self) -> Dict[str, Any]:
        try:
            with open(self.db_path, "r") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _write_db(self, db: Dict[str, Any]) -> None:
        with open(self.db_path, "w") as fh:
            json.dump(db, fh, indent=2)

    def key(self, kind: str, id_or_name: Any = None) -> _MockKey:
        if id_or_name is None:
            id_or_name = int(uuid.uuid4().int >> 64)
        return _MockKey(kind, id_or_name)

    def get(self, key: _MockKey) -> Optional[_MockEntity]:
        db = self._read_db()
        data = db.get(f"{key.kind}:{key.id_or_name}")
        if data:
            return _MockEntity(key, data)
        return None

    def put(self, entity: _MockEntity) -> None:
        db = self._read_db()
        db[f"{entity.key.kind}:{entity.key.id_or_name}"] = dict(entity)
        self._write_db(db)

    def delete(self, key: _MockKey) -> None:
        db = self._read_db()
        key_str = f"{key.kind}:{key.id_or_name}"
        if key_str in db:
            del db[key_str]
            self._write_db(db)

    def delete_multi(self, keys: list) -> None:
        db = self._read_db()
        for key in keys:
            key_str = f"{key.kind}:{key.id_or_name}"
            db.pop(key_str, None)
        self._write_db(db)

    def query(self, kind: str) -> _MockQuery:
        return _MockQuery(self, kind)


# ──────────────────────────────────────────────
#  Public façade
# ──────────────────────────────────────────────

class DatastoreClient:
    """
    Thin wrapper that exposes the same interface regardless of whether the
    real GCP Datastore or the local mock is used.
    """

    def __init__(self, db_name: str = "backuper-db"):
        if config.USE_REAL_GCP:
            from google.cloud import datastore
            tech_logger.info("Initialising REAL Datastore client (db=%s)", db_name)
            self._client = datastore.Client(database=db_name)
        else:
            tech_logger.info("Initialising MOCK Datastore client")
            self._client = _MockDatastoreClient()

    # ── delegated methods ──

    def key(self, kind: str, id_or_name: Any = None):
        return self._client.key(kind, id_or_name)

    def get(self, key):
        return self._client.get(key)

    def put(self, entity) -> None:
        self._client.put(entity)

    def delete(self, key) -> None:
        self._client.delete(key)

    def delete_multi(self, keys: list) -> None:
        """Batch-delete multiple keys in a single operation where possible."""
        if not keys:
            return
        if config.USE_REAL_GCP:
            self._client.delete_multi(keys)
        else:
            self._client.delete_multi(keys)

    def query(self, kind: str):
        return self._client.query(kind=kind)

    def create_entity(self, key, data: Dict[str, Any], exclude_from_indexes: tuple = ()):
        """
        Build an Entity instance appropriate for the active backend.
        """
        if config.USE_REAL_GCP:
            from google.cloud import datastore
            entity = datastore.Entity(key=key, exclude_from_indexes=exclude_from_indexes)
            entity.update(data)
            return entity
        return _MockEntity(key, data)
