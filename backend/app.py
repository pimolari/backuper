from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from datetime import timedelta
from typing import List, Optional
import io
import os

from backend import config
from backend import models
from backend import auth
from backend import database
from backend import storage

app = FastAPI(title="Backuper API", version="1.0.0")

# Enable CORS for frontend communications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication Endpoints
@app.post("/api/auth/register", response_model=models.UserResponse)
def register(user_in: models.UserRegister):
    # Check if user already exists
    existing_user = database.get_user_by_email(user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
        
    # Validate location & storage class
    if user_in.default_region not in config.ALLOWED_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid region. Allowed: {config.ALLOWED_REGIONS}"
        )
    if user_in.default_storage_class not in config.ALLOWED_STORAGE_CLASSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid storage class. Allowed: {config.ALLOWED_STORAGE_CLASSES}"
        )
        
    # Create GCS Bucket first
    try:
        bucket_name = storage.create_user_bucket(
            email=user_in.email,
            region=user_in.default_region,
            storage_class=user_in.default_storage_class
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Google Cloud Storage bucket: {str(e)}"
        )
        
    # Register User in Datastore
    hashed_pw = auth.hash_password(user_in.password)
    user_data = database.create_user(
        name=user_in.name,
        email=user_in.email,
        hashed_password=hashed_pw,
        default_bucket=bucket_name,
        default_region=user_in.default_region,
        default_storage_class=user_in.default_storage_class
    )
    
    # Return user response
    buckets_info = [
        models.BucketInfo(
            name=bucket_name,
            region=user_in.default_region,
            storage_class=user_in.default_storage_class,
            is_active=True
        )
    ]
    
    return models.UserResponse(
        id=user_data["id"],
        name=user_data["name"],
        email=user_data["email"],
        buckets=buckets_info,
        active_bucket=bucket_name
    )

@app.post("/api/auth/login")
def login(login_in: models.UserLogin):
    user = database.get_user_by_email(login_in.email)
    if not user or not auth.verify_password(login_in.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Create token
    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "name": user["name"],
            "email": user["email"],
            "active_bucket": user["active_bucket"]
        }
    }

# Profile / Workspace Configuration Endpoints
@app.get("/api/profile", response_model=models.UserResponse)
def get_profile(current_user: dict = Depends(auth.get_current_user)):
    buckets_info = []
    active_b = current_user.get("active_bucket", "")
    for b in current_user.get("buckets", []):
        buckets_info.append(
            models.BucketInfo(
                name=b["name"],
                region=b["region"],
                storage_class=b["storage_class"],
                is_active=(b["name"] == active_b)
            )
        )
    return models.UserResponse(
        id=current_user["id"],
        name=current_user["name"],
        email=current_user["email"],
        buckets=buckets_info,
        active_bucket=active_b
    )

@app.post("/api/profile/update", response_model=models.UserResponse)
def update_profile(profile_in: models.ProfileUpdate, current_user: dict = Depends(auth.get_current_user)):
    # If email changes, check if new email already exists
    if profile_in.email.lower() != current_user["email"].lower():
        existing = database.get_user_by_email(profile_in.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists."
            )
            
    database.update_user_profile(
        user_id=current_user["id"],
        name=profile_in.name,
        email=profile_in.email
    )
    
    # Reload user
    updated_user = database.get_user_by_id(current_user["id"])
    
    buckets_info = []
    active_b = updated_user.get("active_bucket", "")
    for b in updated_user.get("buckets", []):
        buckets_info.append(
            models.BucketInfo(
                name=b["name"],
                region=b["region"],
                storage_class=b["storage_class"],
                is_active=(b["name"] == active_b)
            )
        )
    return models.UserResponse(
        id=updated_user["id"],
        name=updated_user["name"],
        email=updated_user["email"],
        buckets=buckets_info,
        active_bucket=active_b
    )

@app.post("/api/profile/bucket", response_model=models.UserResponse)
def create_new_bucket(bucket_in: models.BucketCreate, current_user: dict = Depends(auth.get_current_user)):
    if bucket_in.region not in config.ALLOWED_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid region. Allowed: {config.ALLOWED_REGIONS}"
        )
    if bucket_in.storage_class not in config.ALLOWED_STORAGE_CLASSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid storage class. Allowed: {config.ALLOWED_STORAGE_CLASSES}"
        )
        
    # Create GCS Bucket
    try:
        bucket_name = storage.create_user_bucket(
            email=current_user["email"],
            region=bucket_in.region,
            storage_class=bucket_in.storage_class
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create GCS bucket: {str(e)}"
        )
        
    # Add bucket to User model in Datastore
    database.add_user_bucket(
        user_id=current_user["id"],
        bucket_name=bucket_name,
        region=bucket_in.region,
        storage_class=bucket_in.storage_class
    )
    
    # Reload user
    updated_user = database.get_user_by_id(current_user["id"])
    
    buckets_info = []
    active_b = updated_user.get("active_bucket", "")
    for b in updated_user.get("buckets", []):
        buckets_info.append(
            models.BucketInfo(
                name=b["name"],
                region=b["region"],
                storage_class=b["storage_class"],
                is_active=(b["name"] == active_b)
            )
        )
    return models.UserResponse(
        id=updated_user["id"],
        name=updated_user["name"],
        email=updated_user["email"],
        buckets=buckets_info,
        active_bucket=active_b
    )

@app.post("/api/profile/active-bucket", response_model=models.UserResponse)
def change_active_bucket(bucket_name: str = Query(...), current_user: dict = Depends(auth.get_current_user)):
    success = database.set_active_bucket(current_user["id"], bucket_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to change active bucket. Ensure you own this bucket."
        )
        
    # Reload user
    updated_user = database.get_user_by_id(current_user["id"])
    
    buckets_info = []
    active_b = updated_user.get("active_bucket", "")
    for b in updated_user.get("buckets", []):
        buckets_info.append(
            models.BucketInfo(
                name=b["name"],
                region=b["region"],
                storage_class=b["storage_class"],
                is_active=(b["name"] == active_b)
            )
        )
    return models.UserResponse(
        id=updated_user["id"],
        name=updated_user["name"],
        email=updated_user["email"],
        buckets=buckets_info,
        active_bucket=active_b
    )

# File Management Endpoints
@app.get("/api/files/browse", response_model=models.BrowseResponse)
def browse_files(path: str = Query(""), current_user: dict = Depends(auth.get_current_user)):
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GCS bucket configured for this profile."
        )
        
    cached_items = database.get_cached_files(current_user["id"], active_bucket, path)
    
    # Process breadcrumbs
    clean_path = path.strip("/")
    breadcrumbs = [{"name": "Root", "path": ""}]
    if clean_path:
        parts = clean_path.split("/")
        accumulated = []
        for part in parts:
            accumulated.append(part)
            breadcrumbs.append({
                "name": part,
                "path": "/".join(accumulated)
            })
            
    folders = []
    files = []
    
    for item in cached_items:
        if item.get("is_dir", False):
            folders.append(item["name"])
        else:
            files.append(
                models.FileItem(
                    id=item["id"],
                    name=item["name"],
                    path=item["path"],
                    size=item["size"],
                    upload_date=item["upload_date"],
                    storage_location=item["storage_location"],
                    storage_class=item["storage_class"],
                    is_dir=False
                )
            )
            
    return models.BrowseResponse(
        current_path=clean_path,
        breadcrumbs=breadcrumbs,
        folders=sorted(folders),
        files=sorted(files, key=lambda x: x.name)
    )

@app.get("/api/files/tree")
def get_folders_tree(current_user: dict = Depends(auth.get_current_user)):
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        return []
        
    client = database.get_client()
    query = client.query(kind="FileCache")
    query.add_filter("user_id", "=", current_user["id"])
    query.add_filter("storage_location", "=", active_bucket)
    all_items = list(query.fetch())
    
    folders = set()
    for item in all_items:
        path = item.get("path", "")
        # Get parent path directories
        parts = path.split("/")
        if len(parts) > 1:
            for i in range(1, len(parts)):
                folders.add("/".join(parts[:i]))
        elif item.get("is_dir", False) and path:
            folders.add(path)
            
    return sorted(list(folders))

@app.post("/api/files/upload")
def upload_file(
    path: str = Form(""),
    file: UploadFile = File(...),
    current_user: dict = Depends(auth.get_current_user)
):
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GCS bucket configured."
        )
        
    # Find current active bucket configuration to fetch region & storage class
    bucket_cfg = next((b for b in current_user.get("buckets", []) if b["name"] == active_bucket), None)
    storage_class = bucket_cfg["storage_class"] if bucket_cfg else config.DEFAULT_STORAGE_CLASS
    
    clean_path = path.strip("/")
    if clean_path:
        destination_blob_name = f"{clean_path}/{file.filename}"
    else:
        destination_blob_name = file.filename
        
    # Determine file size without reading the entire file into memory.
    # FastAPI/Starlette uses a SpooledTemporaryFile which supports seek.
    file.file.seek(0, 2)        # seek to end
    file_size = file.file.tell()
    file.file.seek(0)           # rewind for upload
    
    # Stream the file object directly to GCS (no full-memory buffer)
    success = storage.upload_file_to_gcs(
        bucket_name=active_bucket,
        file_obj=file.file,
        destination_blob_name=destination_blob_name,
        file_size=file_size
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to Google Cloud Storage."
        )
        
    # Save to Datastore cache (secured by current_user's ID)
    cached_file = database.cache_file(
        user_id=current_user["id"],
        filename=file.filename,
        path=destination_blob_name,
        size=file_size,
        storage_location=active_bucket,
        storage_class=storage_class,
        is_dir=False
    )
    
    return {"message": "File uploaded and cached successfully", "file": cached_file}

@app.get("/api/files/download/{file_id:path}")
def download_file(file_id: str, current_user: dict = Depends(auth.get_current_user)):
    file_item = database.get_cached_file_by_id(file_id)
    if not file_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in metadata cache."
        )
        
    # Secure: Verify owner
    if file_item["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to download this file."
        )
        
    # Download content from GCS
    content = storage.get_file_content_gcs(
        bucket_name=file_item["storage_location"],
        blob_name=file_item["path"]
    )
    
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file content from GCS."
        )
        
    # Stream file content back
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file_item['name']}"}
    )

@app.delete("/api/files/folder/{folder_path:path}")
def delete_folder(folder_path: str, current_user: dict = Depends(auth.get_current_user)):
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GCS bucket configured."
        )
        
    clean_path = folder_path.strip("/")
    if not clean_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete root workspace."
        )
        
    # Delete all blobs starting with folder_path/ in GCS
    success = storage.delete_folder_from_gcs(
        bucket_name=active_bucket,
        folder_prefix=clean_path
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete folder from Google Cloud Storage."
        )
        
    # Delete from Datastore Cache
    database.delete_cached_files_under_path(
        user_id=current_user["id"],
        bucket_name=active_bucket,
        path_prefix=clean_path
    )
    
    return {"message": f"Folder {clean_path} and its contents deleted successfully"}

@app.delete("/api/files/{file_id:path}")
def delete_file(file_id: str, current_user: dict = Depends(auth.get_current_user)):
    file_item = database.get_cached_file_by_id(file_id)
    if not file_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in metadata cache."
        )
        
    # Secure: Verify owner
    if file_item["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this file."
        )
        
    # Delete from GCS
    success = storage.delete_file_from_gcs(
        bucket_name=file_item["storage_location"],
        blob_name=file_item["path"]
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file from Google Cloud Storage."
        )
        
    # Delete from Datastore Cache
    database.delete_cached_file(file_id)
    
    return {"message": "File deleted successfully"}


@app.post("/api/files/create-folder")
def create_empty_folder(
    path: str = Form(""),
    folder_name: str = Form(...),
    current_user: dict = Depends(auth.get_current_user)
):
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GCS bucket configured."
        )
        
    # Find current active bucket configuration
    bucket_cfg = next((b for b in current_user.get("buckets", []) if b["name"] == active_bucket), None)
    storage_class = bucket_cfg["storage_class"] if bucket_cfg else config.DEFAULT_STORAGE_CLASS
    
    clean_path = path.strip("/")
    if clean_path:
        dir_path = f"{clean_path}/{folder_name}"
    else:
        dir_path = folder_name
        
    # In Datastore cache, a folder can be registered by setting is_dir=True.
    # Note: GCS has no actual directories (it uses flat namespaces), so we register 
    # it in our Datastore cache to let users create and browse empty directories seamlessly!
    cached_folder = database.cache_file(
        user_id=current_user["id"],
        filename=folder_name,
        path=dir_path,
        size=0,
        storage_location=active_bucket,
        storage_class=storage_class,
        is_dir=True
    )
    
    return {"message": "Folder created successfully", "folder": cached_folder}

@app.post("/api/files/sync")
def sync_cache(current_user: dict = Depends(auth.get_current_user)):
    """
    Forces a GCS sync to Datastore Cache for active bucket.
    This reads actual objects from GCS and populates Datastore cache.
    """
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GCS bucket configured."
        )
        
    # Get active bucket configs
    bucket_cfg = next((b for b in current_user.get("buckets", []) if b["name"] == active_bucket), None)
    storage_class = bucket_cfg["storage_class"] if bucket_cfg else config.DEFAULT_STORAGE_CLASS
    
    # 1. Fetch real list from GCS
    real_blobs = storage.list_bucket_blobs(active_bucket)
    
    # 2. Clear current cache for this bucket
    database.clear_cache_for_bucket(current_user["id"], active_bucket)
    
    # 3. Populate cache
    count = 0
    for blob in real_blobs:
        # Ignore empty directories or folder placeholders if any
        if blob["path"].endswith("/"):
            continue
            
        filename = blob["name"]
        path = blob["path"]
        size = blob["size"]
        blob_storage_class = blob.get("storage_class", storage_class)
        
        database.cache_file(
            user_id=current_user["id"],
            filename=filename,
            path=path,
            size=size,
            storage_location=active_bucket,
            storage_class=blob_storage_class,
            is_dir=False
        )
        count += 1
        
    return {"message": f"Cache sync complete. Processed {count} files."}
