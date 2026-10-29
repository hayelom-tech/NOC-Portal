"""HTTP routes for the auth domain."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from server.config import COOKIE_NAME, app_base_url, cookie_secure
from server.controllers.common import authenticated_response, record_audit
from server.database import get_db
from server.models import User, UserRole
from server.schemas import AvatarUpdate, ForgotPasswordRequest, LoginInput, PasswordChange, PasswordResetConfirm, PasswordResetRequest, UserRead
from server.services.email import send_password_reset_email
from server.services.login_rate_limit import LoginRateLimiter, login_rate_limiter
from server.services.permissions import full_matrix
from server.services.security import (
    DUMMY_PASSWORD_HASH,
    RESET_TOKEN_MINUTES,
    create_reset_token,
    get_current_user,
    hash_password,
    require_roles,
    user_from_reset_token,
    verify_password,
)

router = APIRouter()

password_reset_request_limiter = LoginRateLimiter()

@router.post("/api/v1/auth/login")
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip().casefold()
    address = request.client.host if request.client else "unknown"

    retry_after = login_rate_limiter.retry_after(address, username)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.username == username))
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_matches = verify_password(payload.password, password_hash)
    if user is None or not user.is_active or not password_matches:
        login_rate_limiter.record_failure(address, username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    login_rate_limiter.record_success(address, username)
    record_audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return authenticated_response(user)


@router.post("/api/v1/auth/forgot-password", response_model=dict)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    address = request.client.host if request.client else "unknown"
    identifier = payload.identifier.strip().casefold()

    retry_after = password_reset_request_limiter.retry_after(address, identifier)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many reset requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(
        select(User).where((User.username == identifier) | (User.email == identifier))
    )

    if user is not None and user.is_active:
        token = create_reset_token(user)
        record_audit(db, user, "auth.password_reset_requested", "user", user.id)
        db.commit()
        send_password_reset_email(user.email, user.username, token)

    # Count every request for throttling (no enumeration).
    password_reset_request_limiter.record_failure(address, identifier)

    return {
        "status": "password_reset_requested",
        "message": "If an account exists for that identifier, a reset link has been sent.",
    }


@router.post("/api/v1/auth/logout")
def logout():
    response = JSONResponse({"status": "success"})
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=cookie_secure(), samesite="strict")
    return response


@router.get("/api/v1/auth/me", response_model=UserRead)
def current_user(user: User = Depends(get_current_user)):
    return user


@router.post("/api/v1/auth/password")
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.auth_version += 1
    record_audit(db, user, "user.password_changed", "user", user.id)
    db.commit()
@router.post("/api/v1/auth/reset-password", response_model=dict)
def generate_reset_token(
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
):
    user = db.scalar(select(User).where(User.username == payload.username.strip().casefold()))
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    token = create_reset_token(user)
    record_audit(db, actor, "password.reset_requested", "user", user.id)
    db.commit()
    return {"reset_token": token, "expires_in_minutes": RESET_TOKEN_MINUTES}


@router.post("/api/v1/auth/reset-password/confirm")
def confirm_reset_token(
    payload: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    user = user_from_reset_token(payload.token, db)
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.auth_version += 1
    record_audit(db, user, "password.reset_completed", "user", user.id)
    db.commit()
    return {"status": "password_reset"}






@router.patch("/api/v1/auth/me/avatar")
def update_avatar(
    payload: AvatarUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    allowed = {"default", "green", "blue", "purple", "amber", "rose", "teal", "indigo"}
    if payload.avatar_key not in allowed:
        raise HTTPException(status_code=422, detail="Unknown avatar key")
    user.avatar_key = payload.avatar_key
    record_audit(db, user, "user.avatar_updated", "user", user.id)
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/api/v1/auth/permissions")
def my_permissions(user: User = Depends(get_current_user)):
    return full_matrix(user)
