"""Add avatar_key to users."""

import sqlalchemy as sa
from alembic import op

revision = "0005_user_avatar"
down_revision = "0004_handover_field_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "avatar_key" not in columns:
        op.add_column(
            "users",
            sa.Column("avatar_key", sa.String(length=20), nullable=False, server_default="default"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "avatar_key" in columns:
        op.drop_column("users", "avatar_key")
