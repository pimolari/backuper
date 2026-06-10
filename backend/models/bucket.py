"""Bucket-related Pydantic models."""

from pydantic import BaseModel


class BucketCreate(BaseModel):
    region: str
    storage_class: str


class BucketInfo(BaseModel):
    name: str
    region: str
    storage_class: str
    is_active: bool = False
