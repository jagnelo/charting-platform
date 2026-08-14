"""
FastAPI dependency injection for authentication.
Use `current_user = Depends(get_current_user)` on any protected endpoint.
Use `Depends(require_admin)` for admin-only endpoints.
"""

from inspect import isawaitable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.database import (
    close_session_safely,
    get_auth_session_factory,
    get_db,
    rollback_session_safely,
)
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession | Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    user = db.get(User, user_id)
    if isawaitable(user):
        user = await user
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )

    return user


async def get_current_user_detached(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session_factory=Depends(get_auth_session_factory),
) -> User:
    """Authenticate without holding a request DB session past token lookup.

    Streaming responses can outlive the dependency resolution that authenticates
    them.  This variant keeps its short identity lookup session independent of
    the response body so cancellation cannot strand that connection.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    db = session_factory()
    is_active = False
    try:
        user = db.get(User, user_id)
        if isawaitable(user):
            user = await user
        if user is not None:
            # Rollback expires ORM state.  Detach the fully-loaded identity
            # first so the dependency can safely return it after cleanup.
            is_active = user.is_active
            db.expunge(user)
    finally:
        # ``get`` starts an implicit transaction on asyncpg.  Roll it back
        # explicitly before close so even a successful read cannot leave a
        # pooled connection waiting for garbage collection.
        await rollback_session_safely(db)
        await close_session_safely(db)

    if user is None or not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
