"""Role-based permission matrix from Model.xlsx Sheet2.

Values per (permission, role):
  "yes"           → allow
  "no"            → deny
  "limited"       → allow with scope restrictions (caller decides)
  "read_only"     → allow read access only (caller decides)
  "if_authorized" → allow only when a per-user flag is set
"""

import enum

from server.models import User, UserRole


class Permission(str, enum.Enum):
    view_audit_history = "view_audit_history"
    manage_users = "manage_users"
    edit_process_articles = "edit_process_articles"
    submit_handovers = "submit_handovers"
    create_incidents = "create_incidents"
    upload_roster = "upload_roster"
    view_incidents_handovers = "view_incidents_handovers"
    view_roster_knowledge = "view_roster_knowledge"
    change_own_password = "change_own_password"


_MATRIX: dict[Permission, dict[UserRole, str]] = {
    Permission.view_audit_history: {
        UserRole.guest: "no",
        UserRole.operator: "limited",
        UserRole.admin: "yes",
    },
    Permission.manage_users: {
        UserRole.guest: "no",
        UserRole.operator: "no",
        UserRole.admin: "yes",
    },
    Permission.edit_process_articles: {
        UserRole.guest: "no",
        UserRole.operator: "if_authorized",
        UserRole.admin: "yes",
    },
    Permission.submit_handovers: {
        UserRole.guest: "no",
        UserRole.operator: "yes",
        UserRole.admin: "yes",
    },
    Permission.create_incidents: {
        UserRole.guest: "no",
        UserRole.operator: "yes",
        UserRole.admin: "yes",
    },
    Permission.upload_roster: {
        UserRole.guest: "no",
        UserRole.operator: "if_authorized",
        UserRole.admin: "yes",
    },
    Permission.view_incidents_handovers: {
        UserRole.guest: "read_only",
        UserRole.operator: "yes",
        UserRole.admin: "yes",
    },
    Permission.view_roster_knowledge: {
        UserRole.guest: "yes",
        UserRole.operator: "yes",
        UserRole.admin: "yes",
    },
    Permission.change_own_password: {
        UserRole.guest: "yes",
        UserRole.operator: "yes",
        UserRole.admin: "yes",
    },
}


def _resolve(user: User, permission: Permission) -> str:
    result = _MATRIX[permission][user.role]
    if result == "if_authorized":
        if permission == Permission.edit_process_articles and user.can_edit_content:
            return "yes"
        if permission == Permission.upload_roster and user.can_upload_roster:
            return "yes"
        return "no"
    return result


def check(user: User, permission: Permission) -> str:
    """Return the raw rule: 'yes' | 'no' | 'limited' | 'read_only'."""
    return _resolve(user, permission)


def allowed(user: User, permission: Permission) -> bool:
    """True when the user can perform the permission at all."""
    return _resolve(user, permission) in {"yes", "limited", "read_only"}


def full_matrix(user: User) -> dict[str, str]:
    """Return every permission resolved for this specific user."""
    return {perm.value: _resolve(user, perm) for perm in Permission}