from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from server.models import (
    Handover,
    RosterAssignment,
    RosterMember,
    RosterTeam,
    Shift,
    ShiftName,
    User,
    UserRole,
)


def is_challenge_recipient(
    db: Session,
    source_shift: Shift,
    handover: Handover,
    user: User,
) -> bool:
    if user.role == UserRole.admin:
        return True
    if not handover.operational_challenges or handover.challenge_domain not in {"power", "tx"}:
        return False

    target_date = source_shift.shift_date
    if source_shift.shift_name == ShiftName.night:
        target_date += timedelta(days=1)
    team_domains = db.scalars(
        select(RosterTeam.challenge_domain)
        .select_from(RosterMember)
        .join(RosterAssignment, RosterAssignment.member_id == RosterMember.id)
        .join(RosterTeam, RosterTeam.id == RosterMember.roster_team_id)
        .where(
            RosterAssignment.assignment_date == target_date,
            RosterAssignment.shift_name == handover.next_shift_name,
            RosterMember.user_id == user.id,
        )
    ).all()
    return handover.challenge_domain in team_domains
