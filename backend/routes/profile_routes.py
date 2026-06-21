"""Profile and workspace-configuration routes."""

from fastapi import APIRouter, Depends, Query

from backend.auth.dependencies import get_current_user
from backend.models.user import ProfileUpdate, UserResponse
from backend.models.bucket import BucketCreate
from backend.models.invite import InviteCreate, InviteResponse
from backend.services import user_service, bucket_service, invite_service
from backend.common.exceptions import ForbiddenError

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

def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise ForbiddenError("Admin access required.")

@router.get("/users", response_model=list[UserResponse])
def get_all_users(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return user_service.list_users()

@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    user_service.deactivate_user(user_id)
    return {"message": "User deactivated successfully."}

@router.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from backend.services.file_service import queue_bulk_delete
    # Provide the target as "user:id" to the bulk delete queue
    queue_bulk_delete(current_user, [f"user:{user_id}"])
    return {"message": "User queued for permanent deletion."}

@router.get("/invites", response_model=list[InviteResponse])
def get_all_invites(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return invite_service.list_invites()

@router.post("/invites", response_model=InviteResponse)
def create_invite(invite_in: InviteCreate, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return invite_service.create_invite(current_user["email"], invite_in.invited_email)

@router.post("/invites/{token}/cancel", response_model=InviteResponse)
def cancel_invite(token: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return invite_service.cancel_invite(token)

