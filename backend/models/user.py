"""User-related Pydantic models."""

from pydantic import BaseModel, EmailStr, Field
from typing import List
from backend.models.bucket import BucketInfo


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


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    buckets: List[BucketInfo]
    active_bucket: str
