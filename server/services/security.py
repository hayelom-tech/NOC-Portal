from datetime import datetime, timedelta, timezone
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from server.config import ACCESS_TOKEN_MINUTES, COOKIE_NAME, jwt_secret
from server.database import get_db
from server.models import User, UserRole

ALGORITHM = "HS256"
DUMMY_PASSWORD_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("ascii")

def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) < 12 or len(raw) > 72:
        raise ValueError("Password must be 12-72 UTF-8 bytes long.")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    return jwt.encode(
        {
            "sub": str(user.id),
            "exp": expires,
            "role": user.role.value,
            "ver": user.auth_version,
        },
        jwt_secret(),
        algorithm=ALGORITHM,
    )


def user_from_token(token: str, db: Session) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        token_version = int(payload["ver"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None or not user.is_active or token_version != user.auth_version:
        raise credentials_error
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    cached_user = getattr(request.state, "user", None)
    if cached_user is not None:
        return db.merge(cached_user, load=False)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_from_token(token, db)


def require_roles(*roles: UserRole):
    def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return check_role
