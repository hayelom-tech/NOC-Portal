"""Link imported Front Office roster members to user accounts by email."""

import sqlalchemy as sa
from alembic import op


revision = "0012_roster_member_user_email"
down_revision = "0011_handover_challenge_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("roster_members")}
    if "email" not in columns:
        op.add_column("roster_members", sa.Column("email", sa.String(length=254), nullable=True))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("roster_members")}
    if "ix_roster_members_email" not in indexes:
        op.create_index("ix_roster_members_email", "roster_members", ["email"])


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("roster_members")}
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("roster_members")}
    if "ix_roster_members_email" in indexes:
        op.drop_index("ix_roster_members_email", table_name="roster_members")
    if "email" in columns:
        op.drop_column("roster_members", "email")
