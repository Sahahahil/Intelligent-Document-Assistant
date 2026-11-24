"""JWT token payload schema for NextAuth.js integration."""


from pydantic import BaseModel, EmailStr


class UserClaims(BaseModel):
    """Decoded JWT claims from NextAuth.js."""

    sub: str
    email: EmailStr
    name: str | None = None
    picture: str | None = None
    iat: int | None = None
    exp: int | None = None
    jti: str | None = None