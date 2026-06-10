"""File management routes — browse, upload, download, delete, sync."""

import io

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from backend.auth.dependencies import get_current_user
from backend.clients.gcs_client import GCSClient
from backend.models.file import BrowseResponse
from backend.services import file_service

router = APIRouter(prefix="/api/files", tags=["files"])
_gcs = GCSClient()


@router.get("/browse", response_model=BrowseResponse)
def browse_files(
    path: str = Query(""),
    limit: int = Query(200),
    page: int = Query(1),
    current_user: dict = Depends(get_current_user),
):
    return file_service.browse_files(current_user, path, limit, page)


@router.get("/tree")
def get_folders_tree(current_user: dict = Depends(get_current_user)):
    return file_service.get_folder_tree(current_user)


@router.post("/upload")
def upload_file(
    path: str = Form(""),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    current_user: dict = Depends(get_current_user),
):
    # Use the size FastAPI derives from the Content-Length header.
    # This avoids seek(0, 2)/tell()/seek(0) which forces FastAPI to
    # spool the entire upload to a temp file before we even start
    # streaming it to GCS.
    file_size = file.size or 0

    return file_service.upload_file(
        current_user=current_user,
        path=path,
        filename=file.filename,
        file_obj=file.file,
        file_size=file_size,
        overwrite=overwrite,
    )


@router.post("/upload/initiate")
def initiate_chunked_upload(
    path: str = Form(""),
    filename: str = Form(...),
    file_size: int = Form(...),
    content_type: str = Form("application/octet-stream"),
    thumbnail_base64: str = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Step 1 of chunked upload. Initializes session and returns upload_id.
    """
    return file_service.initiate_chunked_upload(
        current_user=current_user,
        path=path,
        filename=filename,
        file_size=file_size,
        content_type=content_type,
        thumbnail_base64=thumbnail_base64,
    )


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    offset: int = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Step 2 of chunked upload. Uploads a single chunk.
    """
    chunk_bytes = await file.read()
    return file_service.upload_chunk(
        current_user=current_user,
        upload_id=upload_id,
        offset=offset,
        chunk_bytes=chunk_bytes,
    )


@router.post("/upload/complete")
def complete_chunked_upload(
    upload_id: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Step 3 of chunked upload. Assembles the file and registers it in the cache.
    """
    return file_service.complete_chunked_upload(
        current_user=current_user,
        upload_id=upload_id,
    )



@router.get("/download/{file_id:path}")
def download_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    file_item, content = file_service.download_file(current_user, file_id)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={file_item['name']}"
        },
    )


@router.delete("/folder/{folder_path:path}")
def delete_folder(
    folder_path: str,
    current_user: dict = Depends(get_current_user),
):
    return file_service.delete_folder(current_user, folder_path)


@router.delete("/{file_id:path}")
def delete_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    return file_service.delete_file(current_user, file_id)


@router.post("/create-folder")
def create_empty_folder(
    path: str = Form(""),
    folder_name: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    return file_service.create_folder(current_user, path, folder_name)


@router.post("/sync")
def sync_cache(current_user: dict = Depends(get_current_user)):
    """
    Synchronize the local Datastore cache with the real GCS bucket contents.
    """
    return file_service.sync_cache(current_user)
