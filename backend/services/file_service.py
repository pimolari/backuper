"""
File service — business logic for browsing, uploading, downloading,
deleting files, creating folders, and cache synchronisation.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from backend import config
from backend.clients.datastore_client import DatastoreClient
from backend.clients.gcs_client import GCSClient
from backend.common.exceptions import (
    ForbiddenError,
    InternalError,
    NotFoundError,
    ValidationError,
)
from backend.common.logging import biz_logger, tech_logger
from backend.models.file import BrowseResponse, FileItem

_db = DatastoreClient()
_gcs = GCSClient()


# ─── helpers ────────────────────────────────────────────────────────

def _require_active_bucket(current_user: Dict[str, Any]) -> str:
    """Return the active bucket name or raise."""
    bucket = current_user.get("active_bucket", "")
    if not bucket:
        raise ValidationError("No active GCS bucket configured for this profile.")
    return bucket


def _get_bucket_storage_class(current_user: Dict[str, Any], bucket_name: str) -> str:
    """Resolve storage class for the given bucket from user config."""
    cfg = next(
        (b for b in current_user.get("buckets", []) if b["name"] == bucket_name),
        None,
    )
    return cfg["storage_class"] if cfg else config.DEFAULT_STORAGE_CLASS


def _verify_file_owner(file_item: Dict[str, Any], user_id: str) -> None:
    """Raise ForbiddenError if the file doesn't belong to the user."""
    if file_item["user_id"] != user_id:
        raise ForbiddenError("You are not authorized to access this file.")


# ─── cache layer (Datastore) ───────────────────────────────────────

def _cache_file(
    user_id: str,
    filename: str,
    path: str,
    size: int,
    storage_location: str,
    storage_class: str,
    is_dir: bool = False,
    thumbnail_base64: str = None,
) -> Dict[str, Any]:
    """Persist a file/folder entry in the Datastore cache."""
    clean_path = path.strip("/")
    key_str = f"{user_id}:{storage_location}:{clean_path}"
    key = _db.key("FileCache", key_str)

    file_data = {
        "user_id": user_id,
        "name": filename,
        "path": clean_path,
        "size": size,
        "upload_date": datetime.utcnow().isoformat(),
        "storage_location": storage_location,
        "storage_class": storage_class,
        "is_dir": is_dir,
    }
    
    if thumbnail_base64:
        file_data["thumbnail_base64"] = thumbnail_base64
        
    entity = _db.create_entity(key, file_data, exclude_from_indexes=("thumbnail_base64",))
    _db.put(entity)

    file_data["id"] = key_str
    return file_data


def _get_cached_file_by_id(file_id: str) -> Optional[Dict[str, Any]]:
    key = _db.key("FileCache", file_id)
    entity = _db.get(key)
    if entity:
        item = dict(entity)
        item["id"] = file_id
        return item
    return None


def _get_cached_files(
    user_id: str, bucket_name: str, folder_path: str = ""
) -> List[Dict[str, Any]]:
    """
    Return items directly inside *folder_path* (one level).
    Sub-directories are synthesised from deeper paths.
    
    Args:
        user_id (str): The ID of the user.
        bucket_name (str): The name of the GCS bucket.
        folder_path (str): The relative path to list contents of.
        
    Returns:
        List[Dict[str, Any]]: A list of file and folder metadata dictionaries.
    """
    query = _db.query(kind="FileCache")
    query.add_filter("user_id", "=", user_id)
    query.add_filter("storage_location", "=", bucket_name)
    all_files = list(query.fetch())

    clean_folder = folder_path.strip("/")
    prefix = f"{clean_folder}/" if clean_folder else ""
    results: List[Dict[str, Any]] = []
    seen_folders: set = set()

    for entity in all_files:
        path = entity.get("path", "")
        
        # Check if the file is inside the requested folder
        if path.startswith(prefix) and path != clean_folder:
            sub_path = path[len(prefix):]
            
            # If there's no slash in sub_path, it's a direct child (file or explicit folder)
            if "/" not in sub_path:
                full_path = f"{prefix}{sub_path}"
                if entity.get("is_dir", False):
                    seen_folders.add(full_path)
                item = dict(entity)
                item["id"] = entity.key.name or str(entity.key.id)
                results.append(item)
            else:
                # There is a slash, meaning it's nested inside a sub-folder. We must infer that sub-folder.
                top_folder = sub_path.split("/")[0]
                full_inferred_path = f"{prefix}{top_folder}"
                if full_inferred_path not in seen_folders:
                    seen_folders.add(full_inferred_path)
                    results.append({
                        "id": f"{user_id}:{bucket_name}:{full_inferred_path}",
                        "user_id": user_id,
                        "name": top_folder,
                        "path": full_inferred_path,
                        "size": 0,
                        "upload_date": "",
                        "storage_location": bucket_name,
                        "storage_class": "",
                        "is_dir": True,
                    })

    return results


def _delete_cached_file(file_id: str) -> None:
    key = _db.key("FileCache", file_id)
    _db.delete(key)


def _delete_cached_files_under_path(
    user_id: str, bucket_name: str, path_prefix: str = ""
) -> None:
    """
    Delete cache entries under a specific path prefix, or clear the entire bucket cache if path_prefix is empty.
    
    Args:
        user_id (str): The user's ID.
        bucket_name (str): The name of the storage bucket.
        path_prefix (str): The directory prefix to clear. If empty, clears everything.
    """
    query = _db.query(kind="FileCache")
    query.add_filter("user_id", "=", user_id)
    query.add_filter("storage_location", "=", bucket_name)
    
    clean = path_prefix.strip("/")
    for entity in query.fetch():
        if not clean:
            _db.delete(entity.key)
        else:
            path = entity.get("path", "")
            if path == clean or path.startswith(clean + "/"):
                _db.delete(entity.key)



def _resolve_and_verify_upload_path(
    current_user: Dict[str, Any], path: str, filename: str, active_bucket: str, overwrite: bool = False
) -> str:
    """
    Construct the full blob name from path and filename.
    Check for existing duplicate files if overwrite is False.
    
    Args:
        current_user: The user context.
        path: The directory path for the file.
        filename: The name of the file.
        active_bucket: The name of the target GCS bucket.
        overwrite: If False, raises ValidationError when duplicate found.
        
    Returns:
        str: The fully resolved blob name.
    """
    clean_path = path.strip("/")
    blob_name = f"{clean_path}/{filename}" if clean_path else filename

    existing_id = f"{current_user['id']}:{active_bucket}:{blob_name}"
    if not overwrite and _get_cached_file_by_id(existing_id):
        raise ValidationError(
            f"A file named '{filename}' already exists at this path. "
            "Delete it first or upload with overwrite enabled."
        )
    return blob_name

# ─── public API ─────────────────────────────────────────────────────

def browse_files(
    current_user: Dict[str, Any], path: str = "", limit: int = 200, page: int = 1
) -> BrowseResponse:
    """List files and folders at *path* inside the active bucket with pagination."""
    active_bucket = _require_active_bucket(current_user)
    cached = _get_cached_files(current_user["id"], active_bucket, path)

    clean_path = path.strip("/")

    # Breadcrumbs
    breadcrumbs = [{"name": "Root", "path": ""}]
    if clean_path:
        accumulated: list[str] = []
        for part in clean_path.split("/"):
            accumulated.append(part)
            breadcrumbs.append({"name": part, "path": "/".join(accumulated)})

    folders: list[str] = []
    files: list[FileItem] = []

    for item in cached:
        if item.get("is_dir", False):
            folders.append(item["name"])
        else:
            file_item = FileItem(
                id=item["id"],
                name=item["name"],
                path=item["path"],
                size=item["size"],
                upload_date=item["upload_date"],
                storage_location=item["storage_location"],
                storage_class=item["storage_class"],
                is_dir=False,
            )
            # Monkey-patch thumbnail_base64 if it exists for backwards-compatibility 
            # with the strict FileItem model schema constraints.
            if "thumbnail_base64" in item:
                file_item.thumbnail_base64 = item["thumbnail_base64"]
            files.append(file_item)

    folders.sort()
    files.sort(key=lambda f: f.name)

    total_count = len(folders) + len(files)
    offset = (page - 1) * limit
    
    p_folders = []
    p_files = []
    
    if offset < len(folders):
        p_folders = folders[offset:offset+limit]
        rem_limit = limit - len(p_folders)
        p_files = files[0:rem_limit]
    else:
        file_offset = offset - len(folders)
        p_files = files[file_offset:file_offset+limit]

    return BrowseResponse(
        current_path=clean_path,
        breadcrumbs=breadcrumbs,
        folders=p_folders,
        files=p_files,
        total_count=total_count,
    )


def get_folder_tree(current_user: Dict[str, Any]) -> List[str]:
    """Return a flat sorted list of all folder paths in the active bucket."""
    active_bucket = current_user.get("active_bucket", "")
    if not active_bucket:
        return []

    query = _db.query(kind="FileCache")
    query.add_filter("user_id", "=", current_user["id"])
    query.add_filter("storage_location", "=", active_bucket)

    folders: set[str] = set()
    for item in query.fetch():
        path = item.get("path", "")
        parts = path.split("/")
        if len(parts) > 1:
            for i in range(1, len(parts)):
                folders.add("/".join(parts[:i]))
        elif item.get("is_dir", False) and path:
            folders.add(path)

    return sorted(folders)


def upload_file(
    current_user: Dict[str, Any],
    path: str,
    filename: str,
    file_obj,
    file_size: int,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Upload a file to GCS and cache its metadata.

    Args:
        current_user: The dictionary of the currently authenticated user.
        path: The target folder path.
        filename: The name of the file to save.
        file_obj: The file-like object containing data.
        file_size: Size in bytes.
        overwrite: When *False* (default) an existing file at the same path
                   raises a :class:`ValidationError` instead of silently
                   overwriting it.
                   
    Returns:
        Dict: Message and cached file metadata.
    """
    active_bucket = _require_active_bucket(current_user)
    storage_class = _get_bucket_storage_class(current_user, active_bucket)
    blob_name = _resolve_and_verify_upload_path(current_user, path, filename, active_bucket, overwrite)

    success = _gcs.upload_file(
        bucket_name=active_bucket,
        file_obj=file_obj,
        destination_blob_name=blob_name,
        file_size=file_size,
    )
    if not success:
        raise InternalError("Failed to upload file to Google Cloud Storage.")

    cached = _cache_file(
        user_id=current_user["id"],
        filename=filename,
        path=blob_name,
        size=file_size,
        storage_location=active_bucket,
        storage_class=storage_class,
        is_dir=False,
    )

    biz_logger.info(
        "File uploaded: %s → %s/%s", filename, active_bucket, blob_name
    )
    return {"message": "File uploaded and cached successfully", "file": cached}


def initiate_chunked_upload(
    current_user: Dict[str, Any],
    path: str,
    filename: str,
    file_size: int,
    content_type: str,
    thumbnail_base64: str = None,
) -> Dict[str, Any]:
    """
    Step 1 of chunked upload. Initializes the session and GCS resumable session (or local temp path).
    
    Args:
        current_user: The currently authenticated user context.
        path: The folder path in the bucket.
        filename: Target name for the assembled file.
        file_size: Expected total size of the final file.
        content_type: MIME type of the file.
        thumbnail_base64: Optional base64-encoded thumbnail payload.
        
    Returns:
        Dict: Information including the upload_id and chunk_size boundaries.
    """
    import uuid
    active_bucket = _require_active_bucket(current_user)
    blob_name = _resolve_and_verify_upload_path(current_user, path, filename, active_bucket, overwrite=False)

    # Initiate resumable upload session on GCS/local mock
    upload_target = _gcs.initiate_resumable_upload(
        bucket_name=active_bucket,
        blob_name=blob_name,
        file_size=file_size,
        content_type=content_type or "application/octet-stream",
    )

    upload_id = str(uuid.uuid4())
    session_data = {
        "user_id": current_user["id"],
        "bucket": active_bucket,
        "blob_name": blob_name,
        "filename": filename,
        "file_size": file_size,
        "content_type": content_type or "application/octet-stream",
        "created_at": datetime.utcnow().isoformat(),
    }

    if thumbnail_base64:
        session_data["thumbnail_base64"] = thumbnail_base64

    if config.USE_REAL_GCP:
        session_data["gcs_session_url"] = upload_target
    else:
        session_data["temp_file_path"] = upload_target

    key = _db.key("UploadSession", upload_id)
    entity = _db.create_entity(key, session_data, exclude_from_indexes=("thumbnail_base64",))
    _db.put(entity)

    biz_logger.info(
        "Chunked upload session initiated for %s (id: %s)",
        filename, upload_id,
    )
    return {
        "upload_id": upload_id,
        "chunk_size": 5 * 1024 * 1024, # 5 MB
    }


def upload_chunk(
    current_user: Dict[str, Any],
    upload_id: str,
    offset: int,
    chunk_bytes: bytes,
) -> Dict[str, Any]:
    """
    Step 2 of chunked upload. Receives a chunk and writes/streams it to the target storage.
    """
    import os
    import requests
    
    key = _db.key("UploadSession", upload_id)
    session = _db.get(key)
    if not session:
        raise ValidationError("Upload session not found or expired.")

    if session["user_id"] != current_user["id"]:
        raise ForbiddenError("You are not authorized to upload to this session.")

    chunk_size = len(chunk_bytes)
    total_size = session["file_size"]

    if config.USE_REAL_GCP:
        session_url = session["gcs_session_url"]
        headers = {
            "Content-Length": str(chunk_size),
            "Content-Range": f"bytes {offset}-{offset + chunk_size - 1}/{total_size}"
        }
        res = requests.put(session_url, data=chunk_bytes, headers=headers)
        # 308 is Resume Incomplete (successful upload of intermediate chunk)
        # 200/201 is successful upload of the final chunk
        if res.status_code not in (200, 201, 308):
            raise InternalError(f"Failed to upload chunk to GCS: {res.status_code} {res.text}")
    else:
        temp_file_path = session["temp_file_path"]
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        # "r+b" if file exists, "w+b" if not
        mode = "r+b" if os.path.exists(temp_file_path) else "w+b"
        with open(temp_file_path, mode) as f:
            f.seek(offset)
            f.write(chunk_bytes)

    return {"status": "ok"}


def complete_chunked_upload(
    current_user: Dict[str, Any],
    upload_id: str,
) -> Dict[str, Any]:
    """
    Step 3 of chunked upload. Registers the completed upload in the database and cleans up.
    """
    import os
    import shutil

    key = _db.key("UploadSession", upload_id)
    session = _db.get(key)
    if not session:
        raise ValidationError("Upload session not found or expired.")

    if session["user_id"] != current_user["id"]:
        raise ForbiddenError("You are not authorized to complete this session.")

    bucket = session["bucket"]
    blob_name = session["blob_name"]
    filename = session["filename"]
    file_size = session["file_size"]
    storage_class = _get_bucket_storage_class(current_user, bucket)

    if not config.USE_REAL_GCP:
        temp_file_path = session["temp_file_path"]
        if not os.path.exists(temp_file_path):
            raise ValidationError("Assembled temporary file not found.")

        final_path = os.path.join(
            config.MOCK_STORAGE_DIR,
            bucket,
            blob_name.replace("/", "_DIRSEP_")
        )
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        shutil.move(temp_file_path, final_path)

    # Register in metadata cache
    cached = _cache_file(
        user_id=current_user["id"],
        filename=filename,
        path=blob_name,
        size=file_size,
        storage_location=bucket,
        storage_class=storage_class,
        is_dir=False,
        thumbnail_base64=session.get("thumbnail_base64"),
    )

    # Clean up session
    _db.delete(key)

    biz_logger.info(
        "Chunked upload completed and registered: %s (size: %d)",
        filename, file_size,
    )
    return {"message": "File uploaded and registered successfully", "file": cached}



def download_file(
    current_user: Dict[str, Any], file_id: str
) -> tuple[Dict[str, Any], bytes]:
    """
    Download a file.  Returns ``(file_metadata, content_bytes)``.
    """
    file_item = _get_cached_file_by_id(file_id)
    if not file_item:
        raise NotFoundError("File not found in metadata cache.")

    _verify_file_owner(file_item, current_user["id"])

    content = _gcs.get_file_content(
        file_item["storage_location"], file_item["path"]
    )
    if content is None:
        raise InternalError("Failed to retrieve file content from GCS.")

    return file_item, content


def delete_file(current_user: Dict[str, Any], file_id: str) -> dict:
    """Delete a single file from GCS and the Datastore cache."""
    file_item = _get_cached_file_by_id(file_id)
    if not file_item:
        raise NotFoundError("File not found in metadata cache.")

    _verify_file_owner(file_item, current_user["id"])

    success = _gcs.delete_file(file_item["storage_location"], file_item["path"])
    if not success:
        raise InternalError("Failed to delete file from Google Cloud Storage.")

    _delete_cached_file(file_id)
    biz_logger.info("File deleted: %s", file_id)
    return {"message": "File deleted successfully"}


def delete_folder(
    current_user: Dict[str, Any], folder_path: str
) -> dict:
    """Delete all objects under a folder prefix."""
    active_bucket = _require_active_bucket(current_user)
    clean = folder_path.strip("/")
    if not clean:
        raise ValidationError("Cannot delete root workspace.")

    success = _gcs.delete_folder(active_bucket, clean)
    if not success:
        raise InternalError("Failed to delete folder from Google Cloud Storage.")

    _delete_cached_files_under_path(current_user["id"], active_bucket, clean)
    biz_logger.info("Folder deleted: %s/%s", active_bucket, clean)
    return {"message": f"Folder {clean} and its contents deleted successfully"}


def create_folder(
    current_user: Dict[str, Any],
    path: str,
    folder_name: str,
) -> dict:
    """Register an empty folder in the Datastore cache."""
    active_bucket = _require_active_bucket(current_user)
    storage_class = _get_bucket_storage_class(current_user, active_bucket)

    clean_path = path.strip("/")
    dir_path = f"{clean_path}/{folder_name}" if clean_path else folder_name

    cached = _cache_file(
        user_id=current_user["id"],
        filename=folder_name,
        path=dir_path,
        size=0,
        storage_location=active_bucket,
        storage_class=storage_class,
        is_dir=True,
    )

    biz_logger.info("Folder created: %s/%s", active_bucket, dir_path)
    return {"message": "Folder created successfully", "folder": cached}


def sync_cache(current_user: Dict[str, Any]) -> dict:
    """
    Force-sync the Datastore cache with the real GCS bucket contents.
    """
    active_bucket = _require_active_bucket(current_user)
    storage_class = _get_bucket_storage_class(current_user, active_bucket)

    real_blobs = _gcs.list_bucket_blobs(active_bucket)
    _delete_cached_files_under_path(current_user["id"], active_bucket, "")

    count = 0
    for blob in real_blobs:
        if blob["path"].endswith("/"):
            continue
        _cache_file(
            user_id=current_user["id"],
            filename=blob["name"],
            path=blob["path"],
            size=blob["size"],
            storage_location=active_bucket,
            storage_class=blob.get("storage_class", storage_class),
            is_dir=False,
        )
        count += 1

    biz_logger.info(
        "Cache sync complete for %s: %d files", active_bucket, count
    )
    return {"message": f"Cache sync complete. Processed {count} files."}
