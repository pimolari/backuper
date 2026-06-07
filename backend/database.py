from datetime import datetime
from typing import Optional, List, Dict, Any
from backend import config

if config.USE_REAL_GCP:
    from google.cloud import datastore
    print("Using REAL Google Cloud Datastore Client")
else:
    from backend.mock_services import MockDatastoreClient as datastore_mock
    print("Using MOCK Datastore Client")

def get_client():
    if config.USE_REAL_GCP:
        return datastore.Client(database='backuper-db')
    else:
        return datastore_mock()

# User Helpers
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    query = client.query(kind="User")
    query.add_filter("email", "=", email.lower().strip())
    results = list(query.fetch())
    if results:
        user = dict(results[0])
        user["id"] = results[0].key.name or str(results[0].key.id)
        return user
    return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    key = client.key("User", user_id)
    entity = client.get(key)
    if entity:
        user = dict(entity)
        user["id"] = user_id
        return user
    return None

def create_user(name: str, email: str, hashed_password: str, default_bucket: str, default_region: str, default_storage_class: str) -> Dict[str, Any]:
    client = get_client()
    user_id = email.lower().strip() # Use email as primary key to prevent duplication
    key = client.key("User", user_id)
    
    # Initialize user structure
    user_data = {
        "name": name,
        "email": email.lower().strip(),
        "hashed_password": hashed_password,
        "active_bucket": default_bucket,
        "buckets": [
            {
                "name": default_bucket,
                "region": default_region,
                "storage_class": default_storage_class
            }
        ]
    }
    
    if config.USE_REAL_GCP:
        entity = datastore.Entity(key=key)
        entity.update(user_data)
        client.put(entity)
    else:
        # MockEntity takes key
        from backend.mock_services import MockEntity
        entity = MockEntity(key, user_data)
        client.put(entity)
        
    user_data["id"] = user_id
    return user_data

def update_user_profile(user_id: str, name: str, email: str) -> bool:
    client = get_client()
    key = client.key("User", user_id)
    entity = client.get(key)
    if not entity:
        return False
        
    entity["name"] = name
    entity["email"] = email.lower().strip()
    client.put(entity)
    return True

def add_user_bucket(user_id: str, bucket_name: str, region: str, storage_class: str) -> bool:
    client = get_client()
    key = client.key("User", user_id)
    entity = client.get(key)
    if not entity:
        return False
        
    buckets = list(entity.get("buckets", []))
    # Check if bucket already in user buckets
    if not any(b["name"] == bucket_name for b in buckets):
        buckets.append({
            "name": bucket_name,
            "region": region,
            "storage_class": storage_class
        })
        entity["buckets"] = buckets
        client.put(entity)
    return True

def set_active_bucket(user_id: str, bucket_name: str) -> bool:
    client = get_client()
    key = client.key("User", user_id)
    entity = client.get(key)
    if not entity:
        return False
        
    # Verify user owns the bucket
    buckets = entity.get("buckets", [])
    if not any(b["name"] == bucket_name for b in buckets):
        return False
        
    entity["active_bucket"] = bucket_name
    client.put(entity)
    return True

# File Cache Helpers
def cache_file(user_id: str, filename: str, path: str, size: int, storage_location: str, storage_class: str, is_dir: bool = False) -> Dict[str, Any]:
    client = get_client()
    # Normalize path to ensure no leading/trailing slashes, except empty string
    clean_path = path.strip("/")
    key_str = f"{user_id}:{storage_location}:{clean_path}"
    
    key = client.key("FileCache", key_str)
    
    file_data = {
        "user_id": user_id,
        "name": filename,
        "path": clean_path,
        "size": size,
        "upload_date": datetime.utcnow().isoformat(),
        "storage_location": storage_location,
        "storage_class": storage_class,
        "is_dir": is_dir
    }
    
    if config.USE_REAL_GCP:
        entity = datastore.Entity(key=key)
        entity.update(file_data)
        client.put(entity)
    else:
        from backend.mock_services import MockEntity
        entity = MockEntity(key, file_data)
        client.put(entity)
        
    file_data["id"] = key_str
    return file_data

def get_cached_files(user_id: str, bucket_name: str, folder_path: str = "") -> List[Dict[str, Any]]:
    client = get_client()
    query = client.query(kind="FileCache")
    query.add_filter("user_id", "=", user_id)
    query.add_filter("storage_location", "=", bucket_name)
    
    all_files = list(query.fetch())
    
    # We want files and directories directly in folder_path.
    # We do the path filtering in-memory to simplify Datastore indexing and keep caching fast.
    clean_folder = folder_path.strip("/")
    
    results = []
    # Set to avoid duplicates
    seen = set()
    
    for entity in all_files:
        path = entity.get("path", "")
        is_dir = entity.get("is_dir", False)
        
        # Check if the entity resides directly inside clean_folder
        if clean_folder == "":
            # Root folder: looking for files/folders without "/" in their path
            if "/" not in path:
                if path: # Ensure it is not empty
                    file_item = dict(entity)
                    file_item["id"] = entity.key.name or str(entity.key.id)
                    results.append(file_item)
            else:
                # Part of a subdirectory. We extract the top-level directory name and add it as a folder
                top_folder = path.split("/")[0]
                if top_folder not in seen:
                    seen.add(top_folder)
                    results.append({
                        "id": f"{user_id}:{bucket_name}:{top_folder}",
                        "user_id": user_id,
                        "name": top_folder,
                        "path": top_folder,
                        "size": 0,
                        "upload_date": "",
                        "storage_location": bucket_name,
                        "storage_class": "",
                        "is_dir": True
                    })
        else:
            # Inside a subfolder
            if path.startswith(clean_folder + "/"):
                sub_path = path[len(clean_folder) + 1:]
                if "/" not in sub_path:
                    file_item = dict(entity)
                    file_item["id"] = entity.key.name or str(entity.key.id)
                    results.append(file_item)
                else:
                    top_folder = sub_path.split("/")[0]
                    full_folder_path = f"{clean_folder}/{top_folder}"
                    if full_folder_path not in seen:
                        seen.add(full_folder_path)
                        results.append({
                            "id": f"{user_id}:{bucket_name}:{full_folder_path}",
                            "user_id": user_id,
                            "name": top_folder,
                            "path": full_folder_path,
                            "size": 0,
                            "upload_date": "",
                            "storage_location": bucket_name,
                            "storage_class": "",
                            "is_dir": True
                        })
                        
    return results

def get_cached_file_by_id(file_id: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    key = client.key("FileCache", file_id)
    entity = client.get(key)
    if entity:
        file_item = dict(entity)
        file_item["id"] = file_id
        return file_item
    return None

def delete_cached_file(file_id: str) -> bool:
    client = get_client()
    key = client.key("FileCache", file_id)
    entity = client.get(key)
    if not entity:
        return False
    client.delete(key)
    return True

def delete_cached_files_under_path(user_id: str, bucket_name: str, path_prefix: str):
    client = get_client()
    query = client.query(kind="FileCache")
    query.add_filter("user_id", "=", user_id)
    query.add_filter("storage_location", "=", bucket_name)
    
    all_files = list(query.fetch())
    clean_prefix = path_prefix.strip("/")
    
    for entity in all_files:
        path = entity.get("path", "")
        if path == clean_prefix or path.startswith(clean_prefix + "/"):
            client.delete(entity.key)

def clear_cache_for_bucket(user_id: str, bucket_name: str):
    client = get_client()
    query = client.query(kind="FileCache")
    query.add_filter("user_id", "=", user_id)
    query.add_filter("storage_location", "=", bucket_name)
    results = list(query.fetch())
    for entity in results:
        client.delete(entity.key)
