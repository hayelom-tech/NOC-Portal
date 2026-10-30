"""HTTP routes for incident management."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.controllers.common import record_audit
from server.database import get_db
from server.models import Incident, User, UserRole, utc_now
from server.schemas import IncidentCreate, IncidentRead, IncidentUpdate
from server.services.security import get_current_user, require_roles

router = APIRouter()

RESOLVED_RETENTION_DAYS = 3


def _three_days_ago() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=RESOLVED_RETENTION_DAYS)


@router.get("/api/v1/incidents", response_model=list[IncidentRead])
def list_incidents(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Incident).order_by(Incident.created_at.desc())
    if status:
        query = query.where(Incident.status == status)
    # Server-side 3-day retention for resolved incidents (no deletion).
    if status == "resolved":
        query = query.where(Incident.resolved_at.is_not(None)).where(
            Incident.resolved_at >= _three_days_ago()
        )
    query = query.offset(offset).limit(limit)
    return db.scalars(query).all()


@router.post("/api/v1/incidents", response_model=IncidentRead, status_code=201)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.operator, UserRole.admin)),
):
    data = payload.model_dump()
    if data.get("status") == "resolved" and data.get("resolved_at") is None:
        data["resolved_at"] = utc_now()
    incident = Incident(**data, created_by_id=actor.id)
    db.add(incident)
    db.commit()
    db.refresh(incident)
    record_audit(db, actor, "incident.created", "incident", incident.id)
    db.commit()
    return incident


@router.patch("/api/v1/incidents/{incident_id}", response_model=IncidentRead)
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.operator, UserRole.admin)),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    updates = payload.model_dump(exclude_unset=True)
    new_status = updates.get("status")
    becoming_resolved = new_status == "resolved" and incident.status != "resolved"
    for key, value in updates.items():
        setattr(incident, key, value)
    if becoming_resolved and incident.resolved_at is None:
        incident.resolved_at = utc_now()
    db.commit()
    db.refresh(incident)
    record_audit(db, actor, "incident.updated", "incident", incident.id)
    db.commit()
    return incident
