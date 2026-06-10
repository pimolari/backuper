"""File-related Pydantic models."""

from pydantic import BaseModel
from typing import List


class FileItem(BaseModel):
    id: str
    name: str
    path: str
    size: int
    upload_date: str
    storage_location: str
    storage_class: str
    is_dir: bool = False
    thumbnail_base64: str | None = None


class BrowseResponse(BaseModel):
    current_path: str
    breadcrumbs: List[dict]
    folders: List[str]
    files: List[FileItem]
    total_count: int
