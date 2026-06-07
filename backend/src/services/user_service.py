from typing import Optional, Dict, Any, List
from src.clients.datastore import DatastoreClient

# Instantiate Datastore Client
db = DatastoreClient(db_name='backuper-db')

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    query = db.query(kind="User")
    query.add_filter("email", "=", email.lower().strip())
    results = list(query.fetch())
    if results:
        user = dict(results[0])
        user["id"] = results[0].key.name or str(results[0].key.id)
        return user
    return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    key = db.key("User", user_id)
    entity = db.get(key)
    if entity:
        user = dict(entity)
        user["id"] = user_id
        return user
    return None

def create_user(name: str, email: str, hashed_password: str, default_bucket: str, default_region: str, default_storage_class: str) -> Dict[str, Any]:
    user_id = email.lower().strip() # Use email as primary key to prevent duplication
    key = db.key("User", user_id)
    
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
    
    entity = db.create_entity(key, user_data)
    db.put(entity)
        
    user_data["id"] = user_id
    return user_data

def update_user_profile(user_id: str, name: str, email: str) -> bool:
    key = db.key("User", user_id)
    entity = db.get(key)
    if not entity:
        return False
        
    entity["name"] = name
    entity["email"] = email.lower().strip()
    db.put(entity)
    return True

def add_user_bucket(user_id: str, bucket_name: str, region: str, storage_class: str) -> bool:
    key = db.key("User", user_id)
    entity = db.get(key)
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
        db.put(entity)
    return True

def set_active_bucket(user_id: str, bucket_name: str) -> bool:
    key = db.key("User", user_id)
    entity = db.get(key)
    if not entity:
        return False
        
    # Verify user owns the bucket
    buckets = entity.get("buckets", [])
    if not any(b["name"] == bucket_name for b in buckets):
        return False
        
    entity["active_bucket"] = bucket_name
    db.put(entity)
    return True
