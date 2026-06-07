from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    default_region: str = "europe-west1"
    default_storage_class: str = "STANDARD"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    name: str
    email: EmailStr

class BucketCreate(BaseModel):
    region: str
    storage_class: str

class BucketInfo(BaseModel):
    name: str
    region: str
    storage_class: str
    is_active: bool = False

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    buckets: List[BucketInfo]
    active_bucket: str

class FileItem(BaseModel):
    id: str
    name: str
    path: str
    size: int
    upload_date: str
    storage_location: str
    storage_class: str
    is_dir: bool = False

class BrowseResponse(BaseModel):
    current_path: str
    breadcrumbs: List[dict]
    folders: List[str]
    files: List[FileItem]
