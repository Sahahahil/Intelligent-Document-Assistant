"""JWT verification endpoint for NextAuth.js integration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import Settings, get_settings
from app.schemas.auth import UserClaims

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


@router.get("/verify", response_model=UserClaims, summary="Validate JWT from NextAuth.js")
async def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserClaims:
    """Validate a JWT token issued by NextAuth.js using shared HS256 secret."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.nextauth_secret,
            algorithms=["HS256"],
        )
        return UserClaims(**payload)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc