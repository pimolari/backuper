import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.clients.datastore_client import DatastoreClient
from backend.common.logging import tech_logger
from datetime import datetime

def migrate_users():
    db = DatastoreClient()
    query = db.query(kind="User")
    users = list(query.fetch())
    
    count = 0
    for entity in users:
        # Default existing users to admin
        if "role" not in entity:
            entity["role"] = "admin"
        if "enrolment_date" not in entity:
            entity["enrolment_date"] = datetime.utcnow().isoformat()
        if "is_active" not in entity:
            entity["is_active"] = True
            
        db.put(entity)
        count += 1
        
    print(f"Migrated {count} users to admin role.")

if __name__ == "__main__":
    migrate_users()
