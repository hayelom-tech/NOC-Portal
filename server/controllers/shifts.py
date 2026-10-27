"""HTTP routes for the shifts domain."""
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload
from zoneinfo import ZoneInfo
from server.controllers.common import handover_dict, record_audit, require_permission, shift_or_404
from server.database import get_db
from server.models import FrontOfficeAssignment, Handover, HandoverFieldTeam, HandoverRegion, L2Assignment, L2Domain, NEXT_SHIFT, Shift, ShiftName, User, utc_now
from server.schemas import HandoverInput, HandoverRead, L2Read, ShiftRead
from server.services.handover_access import is_challenge_recipient
from server.services.permissions import Permission
from server.services.security import get_current_user

router = APIRouter()


def _is_challenge_recipient(db: Session, source_shift: Shift, handover: Handover, user: User) -> bool:
    return is_challenge_recipient(db, source_shift, handover, user)


def _redact_challenge(payload: dict, visible: bool) -> dict:
    if not visible:
        payload.update({
            "challenge_domain": None,
            "update_for_next_shift": "",
            "active_change_requests": "",
            "planned_maintenance": "",
            "active_field_teams": "",
            "major_incidents": "0",
            "resolved_major_incidents": "0",
            "alarms_pending_resolution": "0",
            "closed_trouble_tickets": 0,
            "archived_handover_index": None,
            "field_teams": [],
        })
    return payload


@router.get("/api/v1/shifts", response_model=list[ShiftRead])
def list_shifts(
    shift_date: date | None = Query(default=None, alias="date"),
    start_date: date | None = None,
    end_date: date | None = None,
    shift_name: ShiftName | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Shift).order_by(Shift.shift_date.desc(), Shift.shift_name)
    if shift_date:
        query = query.where(Shift.shift_date == shift_date)
    if start_date:
        query = query.where(Shift.shift_date >= start_date)
    if end_date:
        query = query.where(Shift.shift_date <= end_date)
    if shift_name:
        query = query.where(Shift.shift_name == shift_name)
    query = query.offset(offset).limit(limit)
    return db.scalars(query).all()


EAT_TZ = ZoneInfo("Africa/Addis_Ababa")


@router.get("/api/v1/shifts/current")
def current_shift_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the current shift plus the previous shift's handover summary."""
    now = datetime.now(EAT_TZ)
    today = now.date()

    hour = now.hour
    if 6 <= hour < 14:
        slot = ShiftName.morning
    elif 14 <= hour < 22:
        slot = ShiftName.afternoon
    else:
        slot = ShiftName.night

    current = db.scalar(
        select(Shift).where(Shift.shift_date == today, Shift.shift_name == slot)
    )

    prev_slot = {
        ShiftName.morning: ShiftName.night,
        ShiftName.afternoon: ShiftName.morning,
        ShiftName.night: ShiftName.afternoon,
    }[slot]
    prev_date = today if slot != ShiftName.morning else today - timedelta(days=1)

    previous = db.scalar(
        select(Shift)
        .options(selectinload(Shift.handover).selectinload(Handover.field_teams))
        .where(Shift.shift_date == prev_date, Shift.shift_name == prev_slot)
    )

    def handover_payload(source_shift: Shift | None) -> dict | None:
        handover = source_shift.handover if source_shift else None
        if handover is None:
            return None
        return _redact_challenge({
            "operational_challenges": handover.operational_challenges,
            "challenge_domain": handover.challenge_domain,
            "update_for_next_shift": handover.update_for_next_shift,
            "active_change_requests": handover.active_change_requests,
            "planned_maintenance": handover.planned_maintenance,
            "field_teams": [
                {"site_id": team.site_id, "name": team.name, "phone": team.phone}
                for team in handover.field_teams
            ],
            "updated_at": handover.updated_at,
        }, _is_challenge_recipient(db, source_shift, handover, user))

    return {
        "now": now,
        "current": {
            "shift_date": today.isoformat(),
            "shift_name": slot.value,
            "shift_id": current.id if current else None,
        },
        "previous": {
            "shift_date": prev_date.isoformat(),
            "shift_name": prev_slot.value,
            "shift_id": previous.id if previous else None,
            "handover": handover_payload(previous),
        },
    }


@router.get("/api/v1/shifts/{shift_id}", response_model=ShiftRead)
def get_shift(shift_id: int, db: Session = Depends(get_db)):
    return shift_or_404(db, shift_id)


@router.get("/api/v1/shifts/{shift_id}/front-office")
def get_front_office(shift_id: int, db: Session = Depends(get_db)):
    shift_or_404(db, shift_id)
    rows = db.scalars(
        select(FrontOfficeAssignment)
        .where(FrontOfficeAssignment.shift_id == shift_id)
        .order_by(FrontOfficeAssignment.is_primary.desc(), FrontOfficeAssignment.person_name)
    ).all()
    return [{
        "id": row.id, "person_name": row.person_name, "title": row.title,
        "phone": row.phone, "email": row.email, "is_primary": row.is_primary,
    } for row in rows]


@router.get("/api/v1/shifts/{shift_id}/l2-support", response_model=list[L2Read])
def get_l2_support(
    shift_id: int,
    domain: str | None = None,
    db: Session = Depends(get_db),
):
    shift_or_404(db, shift_id)
    query = select(L2Assignment).where(L2Assignment.shift_id == shift_id)
    if domain:
        try:
            from server.models import L2Domain
            query = query.where(L2Assignment.domain == L2Domain(domain))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Unknown L2 domain") from exc
    return db.scalars(query.order_by(L2Assignment.domain, L2Assignment.engineer_name)).all()


@router.get("/api/v1/shifts/{shift_id}/handover", response_model=HandoverRead)
def get_handover(
    shift_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    shift = shift_or_404(db, shift_id)
    handover = db.scalar(
        select(Handover)
        .options(selectinload(Handover.regions), selectinload(Handover.field_teams))
        .where(Handover.shift_id == shift_id)
    )
    if handover is None:
        raise HTTPException(status_code=404, detail="No handover has been recorded for this shift")
    return _redact_challenge(
        handover_dict(handover),
        _is_challenge_recipient(db, shift, handover, actor),
    )


@router.put("/api/v1/shifts/{shift_id}/handover", response_model=HandoverRead)
def update_handover(
    shift_id: int,
    payload: HandoverInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.submit_handovers)),
):
    shift = shift_or_404(db, shift_id)
    handover = db.scalar(
        select(Handover)
        .options(selectinload(Handover.regions), selectinload(Handover.field_teams))
        .where(Handover.shift_id == shift_id)
    )
    values = payload.model_dump(exclude={"regions", "field_teams", "expected_updated_at"})
    if payload.next_shift_name != NEXT_SHIFT[shift.shift_name]:
        raise HTTPException(
            status_code=422,
            detail=f"The next shift after {shift.shift_name.value} is {NEXT_SHIFT[shift.shift_name].value}.",
        )
    preserve_challenge_details = bool(
        handover
        and handover.operational_challenges
        and not _is_challenge_recipient(db, shift, handover, actor)
    )
    if preserve_challenge_details:
        for key in (
            "operational_challenges",
            "challenge_domain",
            "update_for_next_shift",
            "active_change_requests",
            "planned_maintenance",
            "active_field_teams",
            "major_incidents",
            "resolved_major_incidents",
            "alarms_pending_resolution",
            "closed_trouble_tickets",
            "archived_handover_index",
        ):
            values[key] = getattr(handover, key)
    if handover is None:
        handover = Handover(shift_id=shift_id, created_by_id=actor.id, **values)
        db.add(handover)
        db.flush()
    else:
        if payload.expected_updated_at is None:
            raise HTTPException(
                status_code=428,
                detail="Reload this handover before editing so the latest version is included.",
            )
        locked_at = utc_now()
        claim = db.execute(
            update(Handover)
            .where(
                Handover.id == handover.id,
                Handover.updated_at == payload.expected_updated_at,
            )
            .values(updated_at=locked_at)
            .execution_options(synchronize_session=False)
        )
        if claim.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This handover changed after you opened it. Reload it before saving again.",
            )
        handover.updated_at = locked_at
        for key, value in values.items():
            setattr(handover, key, value)
        handover.acknowledged_by_id = None
        handover.acknowledged_at = None
        for region in list(handover.regions):
            db.delete(region)
        if payload.field_teams is not None and not preserve_challenge_details:
            for team in list(handover.field_teams):
                db.delete(team)
        db.flush()
    for region in payload.regions:
        db.add(HandoverRegion(handover_id=handover.id, **region.model_dump()))
    if payload.field_teams is not None and not preserve_challenge_details:
        for team in payload.field_teams:
            db.add(HandoverFieldTeam(handover_id=handover.id, **team.model_dump()))
    record_audit(db, actor, "handover.updated", "handover", handover.id)
    db.commit()
    db.refresh(handover)
    db.refresh(handover, attribute_names=["regions", "field_teams"])
    return _redact_challenge(
        handover_dict(handover),
        _is_challenge_recipient(db, shift, handover, actor),
    )


@router.post("/api/v1/shifts/{shift_id}/handover/acknowledge", response_model=HandoverRead)
def acknowledge_handover(
    shift_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.submit_handovers)),
):
    shift = shift_or_404(db, shift_id)
    handover = db.scalar(
        select(Handover)
        .options(selectinload(Handover.regions), selectinload(Handover.field_teams))
        .where(Handover.shift_id == shift_id)
    )
    if handover is None:
        raise HTTPException(status_code=404, detail="No handover has been recorded for this shift")

    acknowledged_at = utc_now()
    result = db.execute(
        update(Handover)
        .where(Handover.id == handover.id, Handover.acknowledged_at.is_(None))
        .values(
            acknowledged_by_id=actor.id,
            acknowledged_at=acknowledged_at,
            updated_at=acknowledged_at,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This handover has already been acknowledged")
    record_audit(db, actor, "handover.acknowledged", "handover", handover.id)
    db.commit()
    db.refresh(handover)
    db.refresh(handover, attribute_names=["regions", "field_teams"])
    return _redact_challenge(
        handover_dict(handover),
        _is_challenge_recipient(db, shift, handover, actor),
    )
