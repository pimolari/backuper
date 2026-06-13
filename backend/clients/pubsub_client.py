"""
Google Cloud Pub/Sub client — unified real / mock implementation.

When ``config.USE_REAL_GCP`` is *True* the official ``google-cloud-pubsub``
SDK is used. Otherwise a lightweight JSON-file-backed mock is provided so
the application can run locally without GCP credentials.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from backend import config
from backend.common.logging import tech_logger

# ──────────────────────────────────────────────
#  Mock implementation (local JSON file backend)
# ──────────────────────────────────────────────

class _MockPubSubClient:
    """File-backed Pub/Sub emulator for topics and subscriptions."""

    def __init__(self):
        self.mock_file = os.path.join(config.BASE_DIR, "mock_pubsub.json")
        if not os.path.exists(self.mock_file):
            self._write_state({})

    def _read_state(self) -> Dict[str, Any]:
        try:
            with open(self.mock_file, "r") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _write_state(self, state: Dict[str, Any]) -> None:
        with open(self.mock_file, "w") as fh:
            json.dump(state, fh, indent=2)

    def publish(self, topic: str, data: bytes, **attributes) -> str:
        state = self._read_state()
        if topic not in state:
            state[topic] = []

        message_id = str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "data": data.decode("utf-8"),
            "attributes": attributes,
            "publish_time": datetime.utcnow().isoformat(),
        }
        state[topic].append(message)
        self._write_state(state)
        tech_logger.info("MOCK-PUBSUB: published message %s to topic %s", message_id, topic)
        return message_id

    def pull(self, subscription: str, max_messages: int = 10) -> list:
        # In mock mode, we assume topic == subscription name for simplicity,
        # or we just map the subscription to its underlying topic queue.
        # We will use the subscription string directly as the topic key here.
        state = self._read_state()
        # Fallback to looking for the topic with the same name if subscription is missing
        queue = state.get(subscription, [])
        
        pulled = queue[:max_messages]
        # remove pulled messages from queue
        state[subscription] = queue[max_messages:]
        self._write_state(state)
        
        return pulled


class _MockMessage:
    def __init__(self, msg_data: dict):
        self.message_id = msg_data["message_id"]
        self.data = msg_data["data"].encode("utf-8")
        self.attributes = msg_data.get("attributes", {})
        self._acked = False

    def ack(self):
        self._acked = True

    def nack(self):
        # We don't implement nack/re-queue in the simple mock
        pass


# ──────────────────────────────────────────────
#  Public façade
# ──────────────────────────────────────────────

class PubSubClient:
    """
    Thin wrapper that exposes the same interface regardless of whether the
    real GCP Pub/Sub or the local mock is used.
    """

    def __init__(self):
        self.use_real = config.USE_REAL_GCP
        if self.use_real:
            from google.cloud import pubsub_v1
            import google.auth
            tech_logger.info("Initialising REAL Pub/Sub client")
            self._publisher = pubsub_v1.PublisherClient()
            self._subscriber = pubsub_v1.SubscriberClient()
            
            # Try to get project ID from environment, otherwise fallback to ADC
            env_project = os.getenv("GOOGLE_CLOUD_PROJECT")
            if env_project:
                self.project_id = env_project
            else:
                _, auth_project = google.auth.default()
                self.project_id = auth_project or "backuper-project"
        else:
            tech_logger.info("Initialising MOCK Pub/Sub client")
            self._client = _MockPubSubClient()

    def publish_message(self, topic_name: str, payload: dict) -> str:
        """
        Publish a dictionary payload as JSON to the given topic.
        Returns the message ID.
        """
        data_bytes = json.dumps(payload).encode("utf-8")

        if self.use_real:
            topic_path = self._publisher.topic_path(self.project_id, topic_name)
            future = self._publisher.publish(topic_path, data=data_bytes)
            message_id = future.result()
            tech_logger.info("PUBSUB: published message %s to %s", message_id, topic_name)
            return message_id
        else:
            message_id = self._client.publish(topic_name, data=data_bytes)
            
            # Simulate Push Subscription delivery locally
            if topic_name == "generate-snapshot":
                import threading
                def _push_snap():
                    try:
                        from backend.services.file_service import process_snapshot_message
                        process_snapshot_message(payload)
                    except Exception as e:
                        tech_logger.error("Mock snapshot push delivery failed: %s", e)
                threading.Thread(target=_push_snap).start()
            elif topic_name == "bulk-delete":
                import threading
                def _push_bulk():
                    try:
                        from backend.services.file_service import process_bulk_delete_message
                        process_bulk_delete_message(payload)
                    except Exception as e:
                        tech_logger.error("Mock bulk delete push delivery failed: %s", e)
                threading.Thread(target=_push_bulk).start()
                
            return message_id

    def pull_messages(self, subscription_name: str, callback: Callable) -> None:
        """
        Pull messages from the subscription and invoke the callback.
        In real GCP, this runs continuously in the background (returns a future).
        In mock GCP, this pulls synchronously (so it should be called in a loop by the worker).
        The callback should accept a single argument: the message object (which has `.data`, `.attributes`, and `.ack()`).
        """
        if self.use_real:
            subscription_path = self._subscriber.subscription_path(self.project_id, subscription_name)
            future = self._subscriber.subscribe(subscription_path, callback=callback)
            tech_logger.info("PUBSUB: listening to subscription %s", subscription_name)
            return future
        else:
            # Synchronous pull for mock mode
            messages = self._client.pull(subscription_name, max_messages=10)
            for msg_data in messages:
                mock_msg = _MockMessage(msg_data)
                try:
                    callback(mock_msg)
                except Exception as e:
                    tech_logger.error("MOCK-PUBSUB callback error: %s", e)
