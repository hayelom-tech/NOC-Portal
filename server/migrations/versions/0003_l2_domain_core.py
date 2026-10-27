"""Rename the PSCore/SDM domain enum value to core."""

import sqlalchemy as sa
from alembic import op

revision = "0003_l2_domain_core"
down_revision = "0002_operator_permissions"
branch_labels = None
depends_on = None


def _rename_domain_value(old_value: str, new_value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("L2 domain enum migration requires PostgreSQL.")

    enum_labels = {enum["name"]: set(enum["labels"]) for enum in sa.inspect(bind).get_enums()}
    for enum_name in ("l2_domain", "knowledge_domain"):
        labels = enum_labels.get(enum_name, set())
        if old_value in labels and new_value not in labels:
            op.execute(
                f'ALTER TYPE "{enum_name}" RENAME VALUE \'{old_value}\' TO \'{new_value}\''
            )


def upgrade() -> None:
    _rename_domain_value("pscore_sdm", "core")


def downgrade() -> None:
    _rename_domain_value("core", "pscore_sdm")
