import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.config import validate_runtime_config
from server.database import SessionLocal
from server.models import User, UserRole
from server.schemas import UserCreate
from server.services.security import hash_password


def ensure_initial_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is not None:
            return

        username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip().casefold()
        email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().casefold()
        full_name = os.getenv("INITIAL_ADMIN_FULL_NAME", "").strip()
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        if not all((username, email, full_name, password)):
            raise RuntimeError(
                "The database has no users. Set INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_EMAIL, "
                "INITIAL_ADMIN_FULL_NAME, and INITIAL_ADMIN_PASSWORD to create the first administrator."
            )
        try:
            details = UserCreate(
                username=username,
                email=email,
                full_name=full_name,
                password=password,
                role=UserRole.admin,
            )
            db.add(User(
                username=details.username.casefold(),
                email=details.email.casefold(),
                full_name=details.full_name,
                password_hash=hash_password(details.password),
                role=UserRole.admin,
            ))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            active_admin = db.scalar(
                select(User.id)
                .where(User.role == UserRole.admin, User.is_active.is_(True))
                .limit(1)
            )
            if active_admin is None:
                raise RuntimeError(f"Could not create the initial administrator: {exc}") from exc
        except (ValueError, ValidationError) as exc:
            db.rollback()
            raise RuntimeError(f"Could not create the initial administrator: {exc}") from exc


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    validate_runtime_config()
    ensure_initial_admin()
    yield
