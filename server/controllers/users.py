"""HTTP routes for the users domain."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from server.controllers.common import record_audit, require_permission
from server.database import get_db
from server.models import AuditLog, User, UserRole
from server.schemas import AuditRead, UserCreate, UserRead, UserUpdate
from server.services.permissions import Permission
from server.services.security import hash_password

router = APIRouter()

@router.get("/api/v1/users", response_model=list[UserRead])
def list_users(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.manage_users)),
):
    return db.scalars(select(User).order_by(User.username).offset(offset).limit(limit)).all()


@router.post("/api/v1/users", status_code=201, response_model=UserRead)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.manage_users)),
):
    username = payload.username.strip().casefold()
    email = payload.email.strip().casefold()
    if db.scalar(select(User.id).where((User.username == username) | (User.email == email))):
        raise HTTPException(status_code=409, detail="Username or email is already registered")
    try:
        user = User(
            username=username,
            email=email,
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            department=payload.department,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(user)
    db.flush()
    record_audit(db, actor, "user.created", "user", user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already registered") from exc
    db.refresh(user)
    return user


@router.patch("/api/v1/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.manage_users)),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    if any(updates.get(key) is None for key in (
        "email", "full_name", "role", "is_active", "can_edit_content", "can_upload_roster"
    ) if key in updates):
        raise HTTPException(status_code=422, detail="Required user fields cannot be set to null")
    if updates.get("role", user.role) != UserRole.operator:
        updates["can_edit_content"] = False
        updates["can_upload_roster"] = False
    if actor.id == user.id and (updates.get("role") != user.role or updates.get("is_active") is False):
        raise HTTPException(status_code=400, detail="You cannot change your own role or deactivate your account")
    will_remove_admin = (
        user.role == UserRole.admin
        and user.is_active
        and (updates.get("role", user.role) != UserRole.admin or updates.get("is_active") is False)
    )
    if will_remove_admin:
        other_admin = db.scalar(
            select(User.id).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.id != user.id,
            ).limit(1)
        )
        if other_admin is None:
            raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    for key, value in updates.items():
        setattr(user, key, value.strip().casefold() if key == "email" and value else value)
    if "role" in updates or updates.get("is_active") is False:
        user.auth_version += 1
    record_audit(db, actor, "user.updated", "user", user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from exc
    db.refresh(user)
    return user


@router.delete("/api/v1/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.manage_users)),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.role == UserRole.admin and user.is_active:
        other_admin = db.scalar(
            select(User.id).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.id != user.id,
            ).limit(1)
        )
        if other_admin is None:
            raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    try:
        db.delete(user)
        record_audit(db, actor, "user.deleted", "user", user_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This user has related records (handovers, uploads, audit entries). Deactivate the account instead.",
        ) from exc


@router.get("/api/v1/audit-logs", response_model=list[AuditRead])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.view_audit_history)),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if actor.role == UserRole.operator:
        query = query.where(AuditLog.actor_user_id == actor.id)
    return db.scalars(query.limit(limit)).all()
