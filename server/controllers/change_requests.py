"""HTTP routes for change request management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from server.controllers.common import record_audit
from server.database import get_db
from server.models import ChangeRequest, User, UserRole, utc_now
from server.schemas import ChangeRequestCreate, ChangeRequestRead, ChangeRequestUpdate
from server.services.security import require_roles

router = APIRouter()

# Retention: none — change requests are kept indefinitely (no auto-purge).
# Intentional: CRs serve as an audit trail of infrastructure changes.


@router.get("/api/v1/change-requests", response_model=list[ChangeRequestRead])
def list_change_requests(
    status: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    # joinedload on created_by (many-to-one) avoids N+1 without Cartesian explosion.
    query = select(ChangeRequest).options(joinedload(ChangeRequest.created_by)).order_by(ChangeRequest.created_at.desc())
    if status:
        query = query.where(ChangeRequest.status == status)
    if domain:
        query = query.where(ChangeRequest.domain == domain)
    query = query.offset(offset).limit(limit)
    return db.scalars(query).all()


@router.post("/api/v1/change-requests", response_model=ChangeRequestRead, status_code=201)
def create_change_request(
    payload: ChangeRequestCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.operator, UserRole.admin)),
):
    data = payload.model_dump()
    cr = ChangeRequest(**data, created_by_id=actor.id)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    record_audit(db, actor, "change_request.created", "change_request", cr.id)
    db.commit()
    return cr


@router.patch("/api/v1/change-requests/{cr_id}", response_model=ChangeRequestRead)
def update_change_request(
    cr_id: int,
    payload: ChangeRequestUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.operator, UserRole.admin)),
):
    cr = db.get(ChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(cr, key, value)
    db.commit()
    db.refresh(cr)
    record_audit(db, actor, "change_request.updated", "change_request", cr.id)
    db.commit()
    return cr