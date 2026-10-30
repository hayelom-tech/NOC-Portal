import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Time,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    guest = "guest"
    operator = "operator"
    admin = "admin"


class ShiftName(str, enum.Enum):
    morning = "morning"
    afternoon = "afternoon"
    night = "night"


NEXT_SHIFT = {
    ShiftName.morning: ShiftName.afternoon,
    ShiftName.afternoon: ShiftName.night,
    ShiftName.night: ShiftName.morning,
}


class KnowledgeDomain(str, enum.Enum):
    power = "power"
    ran = "ran"
    tx = "tx"
    core = "core"


class L2Domain(str, enum.Enum):
    tx = "tx"
    ran = "ran"
    power = "power"
    ps_core_sdm = "ps_core_sdm"
    cs_core_volte = "cs_core_volte"


class CMRegion(str, enum.Enum):
    east_1 = "East 1"
    east_2 = "East 2"
    west = "West"
    north_west = "North West"
    north_east = "North East"
    north = "North"
    afar = "Afar"


class IncidentStatus(str, enum.Enum):
    ongoing = "ongoing"
    resolved = "resolved"
    closed = "closed"


class IncidentPriority(str, enum.Enum):
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"
    p4 = "P4"
    p5 = "P5"


class ChangeStatus(str, enum.Enum):
    in_progress = "in_progress"
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    rollback = "rollback"


class ChangeRisk(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_edit_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_upload_roster: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_key: Mapped[str] = mapped_column(String(20), default="default", nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("shift_date", "shift_name", name="uq_shifts_date_name"),
        CheckConstraint("shift_name IN ('morning', 'afternoon', 'night')", name="ck_shifts_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_date: Mapped[date] = mapped_column(Date, index=True)
    shift_name: Mapped[ShiftName] = mapped_column(Enum(ShiftName, name="shift_name"))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    front_office: Mapped[list["FrontOfficeAssignment"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )
    l2_assignments: Mapped[list["L2Assignment"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )
    handover: Mapped["Handover | None"] = relationship(
        back_populates="shift", cascade="all, delete-orphan", uselist=False
    )


class FrontOfficeAssignment(Base):
    __tablename__ = "front_office_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), index=True)
    person_name: Mapped[str] = mapped_column(String(160))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shift: Mapped[Shift] = relationship(back_populates="front_office")


class L2Assignment(Base):
    __tablename__ = "l2_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), index=True)
    domain: Mapped[L2Domain] = mapped_column(Enum(L2Domain, name="l2_domain"), index=True)
    engineer_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    shift: Mapped[Shift] = relationship(back_populates="l2_assignments")


class NOCProcess(Base):
    __tablename__ = "noc_processes"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    steps: Mapped[str] = mapped_column(Text)
    escalation_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ProcessDocument(Base):
    __tablename__ = "process_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Handover(Base):
    __tablename__ = "handovers"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), unique=True)
    next_shift_name: Mapped[ShiftName] = mapped_column(Enum(ShiftName, name="next_shift_name"))
    update_for_next_shift: Mapped[str] = mapped_column(Text, default="")
    operational_challenges: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    challenge_domain: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active_change_requests: Mapped[str] = mapped_column(Text, default="")
    planned_maintenance: Mapped[str] = mapped_column(Text, default="")
    active_field_teams: Mapped[str] = mapped_column(Text, default="")
    major_incidents: Mapped[str] = mapped_column(Text, default="")
    resolved_major_incidents: Mapped[str] = mapped_column(Text, default="")
    alarms_pending_resolution: Mapped[str] = mapped_column(Text, default="")
    closed_trouble_tickets: Mapped[int] = mapped_column(Integer, default=0)
    archived_handover_index: Mapped[str | None] = mapped_column(String(200), nullable=True)
    acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    shift: Mapped[Shift] = relationship(back_populates="handover")
    regions: Mapped[list["HandoverRegion"]] = relationship(
        back_populates="handover", cascade="all, delete-orphan"
    )
    field_teams: Mapped[list["HandoverFieldTeam"]] = relationship(
        back_populates="handover",
        cascade="all, delete-orphan",
        order_by="HandoverFieldTeam.position",
    )


class HandoverRegion(Base):
    __tablename__ = "handover_regions"
    __table_args__ = (UniqueConstraint("handover_id", "region_name", name="uq_handover_region"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    handover_id: Mapped[int] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    region_name: Mapped[str] = mapped_column(String(120))
    corrective_maintenance_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover: Mapped[Handover] = relationship(back_populates="regions")


class HandoverFieldTeam(Base):
    __tablename__ = "handover_field_teams"
    __table_args__ = (
        CheckConstraint("site_id ~ '^[0-9]{1,6}$'", name="ck_field_team_site_id"),
        CheckConstraint(
            r"phone IS NULL OR phone ~ '^\+251[0-9]{9}$'",
            name="ck_field_team_phone",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    handover_id: Mapped[int] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), index=True
    )
    site_id: Mapped[str] = mapped_column(String(6))
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    handover: Mapped[Handover] = relationship(back_populates="field_teams")


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_knowledge_articles_approval_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[KnowledgeDomain] = mapped_column(Enum(KnowledgeDomain, name="knowledge_domain"), index=True)
    issue_title: Mapped[str] = mapped_column(String(200), index=True)
    symptoms: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    troubleshooting_steps: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    reference_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False, index=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AdminNotification(Base):
    __tablename__ = "admin_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(30), default="success")
    import_logs: Mapped[list["ImportLog"]] = relationship(
        back_populates="uploaded_file", cascade="all, delete-orphan"
    )


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(100))
    row_count: Mapped[int] = mapped_column(Integer)
    imported_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="import_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class RosterTeam(Base):
    __tablename__ = "roster_teams"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roster_teams_name"),
        CheckConstraint(
            "challenge_domain IS NULL OR challenge_domain IN ('power', 'tx')",
            name="ck_roster_teams_challenge_domain",
        ),
        Index("uq_roster_teams_name_lower", text("lower(name)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    challenge_domain: Mapped[str | None] = mapped_column(String(20), nullable=True)
    members: Mapped[list["RosterMember"]] = relationship(back_populates="roster_team")


class RosterMember(Base):
    __tablename__ = "roster_members"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roster_members_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    roster_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("roster_teams.id"), nullable=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    roster_team: Mapped[RosterTeam | None] = relationship(back_populates="members")
    assignments: Mapped[list["RosterAssignment"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class RosterAssignment(Base):
    __tablename__ = "roster_assignments"
    __table_args__ = (
        UniqueConstraint("member_id", "assignment_date", name="uq_roster_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("roster_members.id", ondelete="CASCADE"), index=True
    )
    assignment_date: Mapped[date] = mapped_column(Date, index=True)
    shift_code: Mapped[str] = mapped_column(String(4))
    shift_name: Mapped[ShiftName | None] = mapped_column(
        Enum(ShiftName, name="roster_shift_name"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    member: Mapped[RosterMember] = relationship(back_populates="assignments")


class L2Roster(Base):
    __tablename__ = "l2_roster"
    __table_args__ = (
        UniqueConstraint("department", "week", name="uq_l2_roster_dept_week"),
        CheckConstraint(
            "department IN ('tx', 'ran', 'power', 'ps_core_sdm', 'cs_core_volte')",
            name="ck_l2_roster_department",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[str] = mapped_column(String(40), index=True)
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    engineer_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    priority: Mapped[IncidentPriority] = mapped_column(
        Enum(IncidentPriority, name="incident_priority", values_callable=lambda x: [e.value for e in x]), default=IncidentPriority.p2, index=True
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"), default=IncidentStatus.ongoing, index=True
    )
    region: Mapped[CMRegion | None] = mapped_column(
        Enum(CMRegion, name="cm_region", values_callable=lambda x: [e.value for e in x]), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_impact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    system_impact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    incident_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mttr: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    support_group: Mapped[str | None] = mapped_column(String(160), nullable=True)
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    update: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped["User | None"] = relationship()

    @property
    def created_by_name(self) -> str | None:
        return self.created_by.full_name if self.created_by else None

    @property
    def created_by_name(self) -> str | None:
        return self.created_by.full_name if self.created_by else None


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        Index("ix_change_requests_status_risk", "status", "risk_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cr_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(50), index=True)  # Core, TX, RAN, Power
    status: Mapped[ChangeStatus] = mapped_column(
        Enum(ChangeStatus, name="change_status"), default=ChangeStatus.scheduled, index=True
    )
    risk_level: Mapped[ChangeRisk] = mapped_column(
        Enum(ChangeRisk, name="change_risk"), default=ChangeRisk.medium
    )
    region: Mapped[CMRegion | None] = mapped_column(
        Enum(CMRegion, name="cm_region", values_callable=lambda x: [e.value for e in x]), nullable=True, index=True
    )
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lead_engineer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approver: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped["User | None"] = relationship()

    @property
    def created_by_name(self) -> str | None:
        return self.created_by.full_name if self.created_by else None
