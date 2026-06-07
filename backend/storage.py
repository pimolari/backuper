import os
import hashlib
from typing import Optional, List
from backend import config

if config.USE_REAL_GCP:
    from google.cloud import storage
    print("Using REAL Google Cloud Storage Client")
else:
    from backend.mock_services import MockStorageClient as storage_mock
    print("Using MOCK Google Cloud Storage Client")

def get_client():
    if config.USE_REAL_GCP:
        return storage.Client()
    else:
        return storage_mock()

def generate_bucket_name(email: str, region: str) -> str:
    """
    Generates a unique bucket name that conforms to GCS requirements.
    Rules: 3-63 characters, lowercase, numbers, hyphens.
    """
    clean_email = email.lower().strip()
    email_hash = hashlib.md5(clean_email.encode()).hexdigest()[:8]
    # Keep it simple and safe
    bucket_name = f"backuper-{email_hash}-{region}"
    return bucket_name

def create_user_bucket(email: str, region: str, storage_class: str) -> str:
    """
    Creates a new GCS bucket in the selected region with the specified storage class.
    Returns the generated bucket name.
    """
    client = get_client()
    bucket_name = generate_bucket_name(email, region)
    
    if config.USE_REAL_GCP:
        try:
            bucket = storage.Bucket(client, name=bucket_name)
            bucket.storage_class = storage_class
            client.create_bucket(bucket, location=region)
            print(f"GCS: Created real bucket {bucket_name} in {region} with class {storage_class}")
        except Exception as e:
            # If bucket already exists or another error, we try a fallback suffix
            import uuid
            suffix = str(uuid.uuid4())[:6]
            bucket_name = f"backuper-{suffix}-{region}"
            bucket = storage.Bucket(client, name=bucket_name)
            bucket.storage_class = storage_class
            client.create_bucket(bucket, location=region)
            print(f"GCS: Created real fallback bucket {bucket_name} due to error: {e}")
    else:
        client.create_bucket(bucket_name, location=region)
        print(f"MOCK-GCS: Created mock bucket {bucket_name} in {region} with class {storage_class}")
        
    return bucket_name

def upload_file_to_gcs(bucket_name: str, file_obj, destination_blob_name: str, file_size: int = None) -> bool:
    """
    Uploads a file object to GCS.  For large files the GCS client uses
    resumable uploads automatically when `size` is provided to
    upload_from_file.  We also set a 10 MB chunk_size so multi-GB files
    are uploaded in manageable parts.
    """
    try:
        client = get_client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        if config.USE_REAL_GCP:
            # 10 MB chunks — triggers resumable upload for files > 5 MB
            blob.chunk_size = 10 * 1024 * 1024
            blob.upload_from_file(file_obj, size=file_size)
        else:
            blob.upload_from_file(file_obj)

        return True
    except Exception as e:
        print(f"GCS Upload Error: {e}")
        return False

def delete_file_from_gcs(bucket_name: str, blob_name: str) -> bool:
    """
    Deletes an object from GCS.
    """
    try:
        client = get_client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        return True
    except Exception as e:
        print(f"GCS Delete Error: {e}")
        return False

def get_file_content_gcs(bucket_name: str, blob_name: str) -> Optional[bytes]:
    """
    Downloads object data from GCS and returns as bytes.
    """
    try:
        client = get_client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Read the file content
        if config.USE_REAL_GCP:
            return blob.download_as_bytes()
        else:
            # MockBlob fallback
            import io
            f = io.BytesIO()
            blob.download_to_file(f)
            f.seek(0)
            return f.read()
    except Exception as e:
        print(f"GCS Download Error: {e}")
        return None

def list_bucket_blobs(bucket_name: str) -> List[dict]:
    """
    Lists all blobs in the bucket. Useful for force syncing cache.
    """
    try:
        client = get_client()
        bucket = client.get_bucket(bucket_name)
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

def delete_folder_from_gcs(bucket_name: str, folder_prefix: str) -> bool:
    """
    Deletes all objects in GCS matching the folder prefix recursively.
    """
    try:
        client = get_client()
        bucket = client.get_bucket(bucket_name)
        
        prefix = folder_prefix.strip("/")
        if not prefix:
            return False
        prefix = prefix + "/"
            
        if config.USE_REAL_GCP:
            blobs = bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                blob.delete()
        else:
            # MockGCS
            blobs = bucket.list_blobs()
            for blob in blobs:
                if blob.name == prefix or blob.name.startswith(prefix):
                    blob.delete()
        return True
    except Exception as e:
        print(f"GCS Delete Folder Error: {e}")
        return False
