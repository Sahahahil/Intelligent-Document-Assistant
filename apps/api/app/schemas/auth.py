"""JWT token payload schema for NextAuth.js integration."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserClaims(BaseModel):
    """Decoded JWT claims from NextAuth.js."""

    sub: str
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None
    iat: Optional[int] = None
    exp: Optional[int] = None
    jti: Optional[str] = None