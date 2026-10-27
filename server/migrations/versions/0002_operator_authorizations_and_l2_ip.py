"""Add operator permissions, L2 IP addresses, and handover acknowledgement."""

import sqlalchemy as sa
from alembic import op

revision = "0002_operator_permissions"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    l2_columns = {column["name"] for column in inspector.get_columns("l2_assignments")}
    handover_columns = {column["name"] for column in inspector.get_columns("handovers")}
    if "can_edit_content" not in user_columns:
        op.add_column(
            "users",
            sa.Column("can_edit_content", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "can_upload_roster" not in user_columns:
        op.add_column(
            "users",
            sa.Column("can_upload_roster", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "ip" not in l2_columns:
        op.add_column("l2_assignments", sa.Column("ip", sa.String(length=45), nullable=True))
    if "acknowledged_by_id" not in handover_columns:
        op.add_column(
            "handovers",
            sa.Column("acknowledged_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
    if "acknowledged_at" not in handover_columns:
        op.add_column("handovers", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ip" in {column["name"] for column in inspector.get_columns("l2_assignments")}:
        op.drop_column("l2_assignments", "ip")
    handover_columns = {column["name"] for column in inspector.get_columns("handovers")}
    if "acknowledged_at" in handover_columns:
        op.drop_column("handovers", "acknowledged_at")
    if "acknowledged_by_id" in handover_columns:
        op.drop_column("handovers", "acknowledged_by_id")
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "can_upload_roster" in user_columns:
        op.drop_column("users", "can_upload_roster")
    if "can_edit_content" in user_columns:
        op.drop_column("users", "can_edit_content")
