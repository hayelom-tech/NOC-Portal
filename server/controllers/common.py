"""Shared controller dependencies and request helpers.

Kept independent of the FastAPI application module so routers can be reused.
"""
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from server.config import ACCESS_TOKEN_MINUTES, COOKIE_NAME, cookie_secure
from server.models import AuditLog, Handover, Shift, User
from server.schemas import UserRead
from server.services.permissions import Permission, allowed as permission_allowed
from server.services.security import create_access_token, get_current_user

def record_audit(db: Session, actor: User, action: str, entity_type: str, entity_id: object) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
    )


def authenticated_response(user: User) -> JSONResponse:
    response = JSONResponse({
        "status": "success",
        "user": UserRead.model_validate(user).model_dump(mode="json"),
    })
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user),
        httponly=True,
        secure=cookie_secure(),
        samesite="strict",
        max_age=ACCESS_TOKEN_MINUTES * 60,
        path="/",
    )
    return response


def shift_or_404(db: Session, shift_id: int) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


def require_permission(permission: Permission):
    def _checker(user: User = Depends(get_current_user)) -> User:
        if not permission_allowed(user, permission):
            raise HTTPException(status_code=403, detail="You do not have permission to do that")
        return user
    return _checker






def handover_dict(handover: Handover) -> dict:
    return {
        "id": handover.id,
        "shift_id": handover.shift_id,
        "next_shift_name": handover.next_shift_name,
        "update_for_next_shift": handover.update_for_next_shift,
        "operational_challenges": handover.operational_challenges,
        "challenge_domain": handover.challenge_domain,
        "active_change_requests": handover.active_change_requests,
        "planned_maintenance": handover.planned_maintenance,
        "active_field_teams": handover.active_field_teams,
        "major_incidents": handover.major_incidents,
        "resolved_major_incidents": handover.resolved_major_incidents,
        "alarms_pending_resolution": handover.alarms_pending_resolution,
        "closed_trouble_tickets": handover.closed_trouble_tickets,
        "archived_handover_index": handover.archived_handover_index,
        "acknowledged_by_id": handover.acknowledged_by_id,
        "acknowledged_at": handover.acknowledged_at,
        "updated_at": handover.updated_at,
        "regions": [
            {
                "region_name": region.region_name,
                "corrective_maintenance_count": region.corrective_maintenance_count,
                "notes": region.notes,
            }
            for region in sorted(handover.regions, key=lambda item: item.region_name.casefold())
        ],
        "field_teams": [
            {
                "id": team.id,
                "site_id": team.site_id,
                "name": team.name,
                "phone": team.phone,
                "position": team.position,
            }
            for team in handover.field_teams
        ],
    }


def _cell_text(value) -> str:
    return "" if value is None else str(value).strip()
