"""Invite-related Pydantic models."""

from pydantic import BaseModel, EmailStr
from typing import Optional


class InviteCreate(BaseModel):
    invited_email: EmailStr


class InviteResponse(BaseModel):
    id: str  # The token itself
    inviter_email: str
    invited_email: str
    status: str  # 'pending', 'accepted', 'cancelled', 'outdated'
    created_at: str
