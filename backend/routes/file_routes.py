"""File management routes — browse, upload, download, delete, sync."""

import io
import json
import base64

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List

from backend.auth.dependencies import get_current_user
from backend.clients.gcs_client import GCSClient
from backend.models.file import BrowseResponse
from backend.services import file_service
from backend.common.events import broker
import asyncio

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


async def event_generator():
    """Generator for Server-Sent Events"""
    q = await broker.subscribe()
    try:
        while True:
            try:
                # Wait for an event, with a 20s timeout for keep-alive
                message = await asyncio.wait_for(q.get(), timeout=20.0)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                # Send a comment to keep the connection alive
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        broker.unsubscribe(q)

@router.get("/events")
async def sse_events(request: Request):
    """
    Server-Sent Events endpoint. The client will reconnect automatically.
    """
    return StreamingResponse(event_generator(), media_type="text/event-stream")


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


class BulkDeleteRequest(BaseModel):
    items: List[str]

@router.post("/bulk-delete/queue")
def queue_bulk_delete(
    request: BulkDeleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Queue a list of file/folder IDs for deletion via Pub/Sub chunks."""
    return file_service.queue_bulk_delete(current_user, request.items)


@router.post("/internal/bulk-delete")
async def bulk_delete_push_endpoint(request: Request):
    """
    Pub/Sub Push endpoint for asynchronous bulk deletions.
    """
    envelope = await request.json()
    if not envelope:
        raise HTTPException(status_code=400, detail="Bad Request: no JSON envelope")
    
    message = envelope.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Bad Request: invalid Pub/Sub message format")
    
    try:
        # data is Base64 encoded JSON
        payload_bytes = base64.b64decode(message.get("data", ""))
        payload = json.loads(payload_bytes)
        
        file_service.process_bulk_delete_message(payload)
        
        # Broadcast that a deletion chunk completed
        asyncio.create_task(broker.broadcast(json.dumps({"type": "bulk_delete_complete"})))
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Error processing push delivery for bulk delete: {e}")
        # Return 200 so Pub/Sub doesn't infinitely retry broken messages
        return {"status": "error", "message": str(e)}


@router.post("/create-folder")
def create_empty_folder(
    path: str = Form(""),
    folder_name: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    return file_service.create_folder(current_user, path, folder_name)


@router.post("/internal/snapshot")
async def generate_snapshot_push(request: Request):
    """Pub/Sub push endpoint for snapshot generation."""
    import base64
    import json
    
    body = await request.json()
    message = body.get("message", {})
    data = message.get("data")
    if not data:
        return {"status": "ignored", "reason": "no data"}
        
    try:
        payload_bytes = base64.b64decode(data)
        payload = json.loads(payload_bytes.decode("utf-8"))
        file_service.process_snapshot_message(payload)
        return {"status": "success"}
    except Exception as e:
        # We should still return 200 so Pub/Sub doesn't continuously retry on hard errors,
        # or we could return 500 to leverage Pub/Sub retries.
        # Given this is a background task, logging is most important.
        from backend.common.logging import tech_logger
        tech_logger.error("Error processing snapshot push: %s", e)
        return {"status": "error", "message": str(e)}

@router.post("/sync")
def sync_cache(current_user: dict = Depends(get_current_user)):
    """
    Synchronize the local Datastore cache with the real GCS bucket contents.
    """
    return file_service.sync_cache(current_user)
