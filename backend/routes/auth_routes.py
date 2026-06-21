"""Authentication routes — register and login."""

from fastapi import APIRouter

from backend.models.user import UserRegister, UserLogin, UserResponse
from backend.services import user_service
from backend.services.invite_service import validate_invite

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(user_in: UserRegister):
    """
    Register a new user account.

    Validates inputs, Provisions a new default Google Cloud Storage Bucket for the user based
    on their email, and stores their profile in Datastore.

    Args:
        user_in (UserRegister): The registration payload.

    Returns:
        UserResponse: The registered user profile data.
    """
    return user_service.register_user(
        name=user_in.name,
        email=user_in.email,
        password=user_in.password,
        region=user_in.default_region,
        storage_class=user_in.default_storage_class,
        invite_token=user_in.invite_token,
    )

@router.get("/validate-invite")
def check_invite(token: str):
    """
    Check if an invite token is valid before showing the registration form.
    """
    invite = validate_invite(token)
    return {"valid": True, "email": invite["invited_email"]}


@router.post("/login")
def login(login_in: UserLogin):
    """
    Authenticate a user and return an access token.

    Verifies the user credentials against Datastore and generates a JWT
    access token used for subsequent authenticated requests.

    Args:
        login_in (UserLogin): The login payload.

    Returns:
        dict: A dictionary containing `access_token` and `user` profile data.
    """
    return user_service.login_user(
        email=login_in.email,
        password=login_in.password,
    )
