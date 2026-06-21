import os

# Security
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-backuper-key-for-jwt-tokens-12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

# GCP Emulation config
# Default to mock unless USE_REAL_GCP is explicitly "true"
USE_REAL_GCP = os.getenv("USE_REAL_GCP", "false").lower() == "true"

# Storage Regions & Classes
DEFAULT_REGION = "us-central1"
ALLOWED_REGIONS = ["europe-west1", "us-central1", "us-east1", "asia-east1"]

DEFAULT_STORAGE_CLASS = "STANDARD"
ALLOWED_STORAGE_CLASSES = ["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"]

# Directories for mock storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_STORAGE_DIR = os.path.join(BASE_DIR, "mock_gcs")
MOCK_DATASTORE_FILE = os.path.join(BASE_DIR, "mock_datastore.json")

# Ensure mock storage dir exists
if not USE_REAL_GCP:
    os.makedirs(MOCK_STORAGE_DIR, exist_ok=True)
