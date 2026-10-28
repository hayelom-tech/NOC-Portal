import re
from datetime import date, datetime, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from server.models import KnowledgeDomain, L2Domain, ShiftName, UserRole
from server.domain.regions import REGION_NAMES, canonical_region_name


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=72)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=72)
    role: UserRole
    department: str | None = Field(default=None, max_length=120)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: UserRole | None = None
    department: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    can_edit_content: bool | None = None
    can_upload_roster: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: str
    role: UserRole
    department: str | None
    is_active: bool
    can_edit_content: bool
    can_upload_roster: bool
    avatar_key: str
    created_at: datetime


class RosterTeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    challenge_domain: Literal["power", "tx"] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Team label cannot be blank.")
        return name


class RosterTeamDomainUpdate(BaseModel):
    challenge_domain: Literal["power", "tx"] | None


class RosterTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    challenge_domain: str | None


class ShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_date: date
    shift_name: ShiftName
    start_time: time
    end_time: time


class FrontOfficeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_name: str
    title: str | None
    phone: str | None
    email: str | None
    is_primary: bool


class L2Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: L2Domain
    engineer_name: str
    role: str | None
    phone: str | None
    email: str | None
    ip: str | None
    team_name: str | None


class RegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    region_name: str
    corrective_maintenance_count: int
    notes: str | None


class FieldTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: str
    name: str
    phone: str | None
    position: int


class HandoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_id: int
    next_shift_name: ShiftName
    update_for_next_shift: str
    operational_challenges: bool
    challenge_domain: str | None
    active_change_requests: str
    planned_maintenance: str
    active_field_teams: str
    major_incidents: str
    resolved_major_incidents: str
    alarms_pending_resolution: str
    closed_trouble_tickets: int
    archived_handover_index: str | None
    acknowledged_by_id: int | None
    acknowledged_at: datetime | None
    updated_at: datetime
    regions: list[RegionRead]
    field_teams: list[FieldTeamRead]


class RegionInput(BaseModel):
    region_name: str = Field(min_length=1, max_length=120)
    corrective_maintenance_count: int = Field(default=0, ge=0, le=50)
    notes: str | None = None

    @field_validator("region_name")
    @classmethod
    def require_official_region(cls, value: str) -> str:
        region_name = canonical_region_name(value)
        if region_name is None:
            raise ValueError(f"Region must be one of: {', '.join(REGION_NAMES)}.")
        return region_name


class FieldTeamInput(BaseModel):
    site_id: str = Field(min_length=1, max_length=6)
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    position: int = Field(default=0, ge=0)

    @field_validator("site_id")
    @classmethod
    def validate_site_id(cls, value: str) -> str:
        if re.fullmatch(r"[0-9]{1,6}", value) is None:
            raise ValueError("Site ID must contain 1 to 6 digits.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and value != "" and re.fullmatch(r"\+251[0-9]{9}", value) is None:
            raise ValueError("Phone must be an Ethiopian mobile number in +251XXXXXXXXX format.")
        return value or None


class HandoverInput(BaseModel):
    expected_updated_at: datetime | None = None
    next_shift_name: ShiftName
    update_for_next_shift: str = ""
    operational_challenges: bool = False
    challenge_domain: str | None = Field(default=None, pattern=r"^(power|tx)$")
    active_change_requests: str = ""
    planned_maintenance: str = ""
    active_field_teams: str = ""
    major_incidents: str = ""
    resolved_major_incidents: str = ""
    alarms_pending_resolution: str = ""
    closed_trouble_tickets: int = Field(default=0, ge=0, le=50)
    archived_handover_index: str | None = Field(default=None, max_length=200)
    regions: list[RegionInput] = Field(min_length=7, max_length=7)
    field_teams: list[FieldTeamInput] | None = Field(default=None, max_length=6)

    @model_validator(mode="after")
    def require_challenge_domain(self):
        if self.operational_challenges and self.challenge_domain is None:
            raise ValueError("Choose Power or Transmission for the operational challenge.")
        if not self.operational_challenges and self.challenge_domain is not None:
            raise ValueError("Challenge domain must be empty when there are no operational challenges.")
        return self

    @field_validator("major_incidents", "resolved_major_incidents", "alarms_pending_resolution", mode="before")
    @classmethod
    def require_count_up_to_fifty(cls, value: object) -> str:
        if value is None or value == "":
            return "0"
        text = str(value).strip()
        if not text.isascii() or not text.isdigit():
            raise ValueError("Incident and alarm counts must be whole numbers from 0 to 50.")
        try:
            count = int(text)
        except ValueError as exc:
            raise ValueError("Incident and alarm counts must be whole numbers from 0 to 50.") from exc
        if count < 0 or count > 50:
            raise ValueError("Incident and alarm counts must be whole numbers from 0 to 50.")
        return str(count)

    @field_validator("active_field_teams")
    @classmethod
    def limit_active_field_teams(cls, value: str) -> str:
        if sum(bool(line.strip()) for line in value.splitlines()) > 6:
            raise ValueError("Provide no more than 6 active field teams, one team per line.")
        return value

    @field_validator("regions")
    @classmethod
    def require_seven_distinct_regions(cls, value: list[RegionInput]) -> list[RegionInput]:
        names = {region.region_name for region in value}
        if names != set(REGION_NAMES):
            missing = sorted(set(REGION_NAMES) - names)
            raise ValueError(f"Provide each official region exactly once; missing: {', '.join(missing)}.")
        return value


class ProcessInput(BaseModel):
    expected_updated_at: datetime | None = Field(default=None, exclude=True)
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str
    owner: str | None = Field(default=None, max_length=160)
    steps: str
    escalation_rule: str | None = None
    priority: str | None = Field(default=None, max_length=40)
    is_active: bool = True


class ProcessRead(ProcessInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProcessDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    file_name: str
    content_type: str
    created_at: datetime


class KnowledgeInput(BaseModel):
    expected_updated_at: datetime | None = Field(default=None, exclude=True)
    domain: KnowledgeDomain
    issue_title: str = Field(min_length=1, max_length=200)
    symptoms: str
    root_cause: str
    troubleshooting_steps: str
    resolution: str
    reference_link: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class KnowledgeRead(KnowledgeInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    approval_status: str
    created_at: datetime
    updated_at: datetime


class ImportSheetResult(BaseModel):
    sheet_name: str
    row_count: int
    imported_count: int


class ImportResult(BaseModel):
    file_id: int
    original_name: str
    status: str
    sheets: list[ImportSheetResult]


class ImportLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_file_id: int
    sheet_name: str
    row_count: int
    imported_count: int
    status: str
    error_message: str | None


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int
    action: str
    entity_type: str
    entity_id: str
    created_at: datetime


class AvatarUpdate(BaseModel):
    avatar_key: str = Field(min_length=1, max_length=20)


class PasswordResetRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=72)
