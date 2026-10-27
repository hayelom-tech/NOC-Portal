"""Add structured field teams to handovers."""

import sqlalchemy as sa
from alembic import op

revision = "0004_handover_field_teams"
down_revision = "0003_l2_domain_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "handover_field_teams" not in inspector.get_table_names():
        op.create_table(
            "handover_field_teams",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "handover_id",
                sa.Integer(),
                sa.ForeignKey("handovers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("site_id", sa.String(length=6), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.CheckConstraint("site_id ~ '^[0-9]{1,6}$'", name="ck_field_team_site_id"),
            sa.CheckConstraint(
                r"phone IS NULL OR phone ~ '^\+251[0-9]{9}$'",
                name="ck_field_team_phone",
            ),
        )
        op.create_index(
            "ix_handover_field_teams_handover_id",
            "handover_field_teams",
            ["handover_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "handover_field_teams" in inspector.get_table_names():
        op.drop_index("ix_handover_field_teams_handover_id", table_name="handover_field_teams")
        op.drop_table("handover_field_teams")
