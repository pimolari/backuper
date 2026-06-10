"""Profile and workspace-configuration routes."""

from fastapi import APIRouter, Depends, Query

from backend.auth.dependencies import get_current_user
from backend.models.user import ProfileUpdate, UserResponse
from backend.models.bucket import BucketCreate
from backend.services import user_service, bucket_service

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Retrieve the authenticated user's profile.
    """
    return user_service.get_profile(current_user)


@router.post("/update", response_model=UserResponse)
def update_profile(
    profile_in: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    return user_service.update_profile(
        current_user=current_user,
        name=profile_in.name,
        email=profile_in.email,
    )


@router.post("/bucket", response_model=UserResponse)
def create_new_bucket(
    bucket_in: BucketCreate,
    current_user: dict = Depends(get_current_user),
):
    return bucket_service.create_bucket(
        current_user=current_user,
        region=bucket_in.region,
        storage_class=bucket_in.storage_class,
    )


@router.post("/active-bucket", response_model=UserResponse)
def change_active_bucket(
    bucket_name: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    return bucket_service.set_active_bucket(
        current_user=current_user,
        bucket_name=bucket_name,
    )
