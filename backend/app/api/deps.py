"""Shared FastAPI dependency type aliases.

Import these in route handlers instead of writing out the full Annotated[…, Depends(…)]
expression each time. This keeps all dependency wiring in one place.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user, get_telephony_provider, require_admin
from app.models.user import User
from app.services.telephony.twilio_provider import TwilioProvider

# Any authenticated user (admin or staff)
CurrentUser = Annotated[User, Depends(get_current_user)]

# Admin-only routes
AdminUser = Annotated[User, Depends(require_admin)]

# Async database session
DB = Annotated[AsyncSession, Depends(get_db)]

# Twilio telephony provider singleton
Provider = Annotated[TwilioProvider, Depends(get_telephony_provider)]
