"""Invite service — handles generation, validation, and listing of invites."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from backend.clients.datastore_client import DatastoreClient
from backend.common.exceptions import ConflictError, InternalError, AppError
from backend.common.logging import biz_logger, tech_logger
from backend.models.invite import InviteResponse

_db = DatastoreClient()

def _build_invite_response(data: dict) -> InviteResponse:
    # Handle missing created_at for safety
    created_at = data.get("created_at") or datetime.now(tz=timezone.utc).isoformat()
    return InviteResponse(
        id=data["id"],
        inviter_email=data["inviter_email"],
        invited_email=data["invited_email"],
        status=data["status"],
        created_at=created_at,
    )

def _get_invite_by_id(token: str) -> Optional[Dict[str, Any]]:
    key = _db.key("Invite", token)
    entity = _db.get(key)
    if entity:
        invite = dict(entity)
        invite["id"] = token
        return invite
    return None

def create_invite(inviter_email: str, invited_email: str) -> InviteResponse:
    """Creates a new invite token."""
    invited_email = invited_email.lower().strip()
    
    # Check if the user is already registered
    from backend.services.user_service import get_user_by_email
    if get_user_by_email(invited_email):
        raise ConflictError("A user with this email is already registered.")

    # Check for pending invites for this email
    query = _db.query(kind="Invite")
    query.add_filter("invited_email", "=", invited_email)
    query.add_filter("status", "=", "pending")
    existing_invites = list(query.fetch())
    if existing_invites:
        # We could cancel the old one or just throw an error. Let's just throw an error.
        raise ConflictError("A pending invite for this email already exists.")

    token = str(uuid.uuid4())
    key = _db.key("Invite", token)
    
    invite_data = {
        "inviter_email": inviter_email,
        "invited_email": invited_email,
        "status": "pending",
        "created_at": datetime.now(tz=timezone.utc).isoformat()
    }
    
    entity = _db.create_entity(key, invite_data)
    _db.put(entity)
    invite_data["id"] = token
    
    biz_logger.info("Invite created by %s for %s. Token: %s", inviter_email, invited_email, token)
    # The token is printed here in logs, simulating email sending.
    
    return _build_invite_response(invite_data)

def validate_invite(token: str) -> Dict[str, Any]:
    """Validates the invite token and returns the invite data. Raises AppError if invalid."""
    invite = _get_invite_by_id(token)
    if not invite:
        raise AppError("Invalid invite token.", status_code=400)
    
    if invite["status"] != "pending":
        raise AppError(f"This invite is {invite['status']}.", status_code=400)
    
    # Check expiration (2 days)
    created_at = datetime.fromisoformat(invite["created_at"])
    # Make naive datetimes timezone-aware for comparison
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > created_at + timedelta(days=2):
        # Update status to outdated
        invite["status"] = "outdated"
        key = _db.key("Invite", token)
        entity = _db.get(key)
        if entity:
            entity["status"] = "outdated"
            _db.put(entity)
        raise AppError("This invite has expired.", status_code=400)
        
    return invite

def mark_invite_accepted(token: str) -> None:
    key = _db.key("Invite", token)
    entity = _db.get(key)
    if entity:
        entity["status"] = "accepted"
        _db.put(entity)

def cancel_invite(token: str) -> InviteResponse:
    invite = _get_invite_by_id(token)
    if not invite:
        raise AppError("Invalid invite token.", status_code=404)
        
    key = _db.key("Invite", token)
    entity = _db.get(key)
    if entity:
        entity["status"] = "cancelled"
        _db.put(entity)
        invite["status"] = "cancelled"
    
    biz_logger.info("Invite %s cancelled", token)
    return _build_invite_response(invite)

def list_invites() -> List[InviteResponse]:
    query = _db.query(kind="Invite")
    results = list(query.fetch())

    now = datetime.now(tz=timezone.utc)
    invites = []
    for res in results:
        data = dict(res)
        data["id"] = res.key.name or str(res.key.id)

        # Check if pending invites are outdated; reuse the already-fetched entity
        # to avoid a second Datastore read per invite.
        if data["status"] == "pending":
            created_at_str = data.get("created_at")
            if created_at_str:
                try:
                    dt = datetime.fromisoformat(created_at_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if now > dt + timedelta(days=2):
                        data["status"] = "outdated"
                        res["status"] = "outdated"  # update in-place on fetched entity
                        _db.put(res)
                except ValueError:
                    pass

        invites.append(_build_invite_response(data))

    # Sort by created_at descending
    invites.sort(key=lambda x: x.created_at, reverse=True)
    return invites
