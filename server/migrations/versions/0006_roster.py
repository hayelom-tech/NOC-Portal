"""Add roster members, assignments, and L2 roster."""

import sqlalchemy as sa
from alembic import op

revision = "0006_roster"
down_revision = "0005_user_avatar"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    tables = _tables()
    if "roster_members" not in tables:
        op.create_table(
            "roster_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("location", sa.String(length=160), nullable=True),
            sa.Column("team", sa.String(length=40), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("name", name="uq_roster_members_name"),
        )
    if "ix_roster_members_name" not in _indexes("roster_members"):
        op.create_index("ix_roster_members_name", "roster_members", ["name"])

    tables = _tables()
    if "roster_assignments" not in tables:
        op.create_table(
            "roster_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "member_id",
                sa.Integer(),
                sa.ForeignKey("roster_members.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("assignment_date", sa.Date(), nullable=False),
            sa.Column("shift_code", sa.String(length=4), nullable=False),
            sa.Column(
                "shift_name",
                sa.Enum("morning", "afternoon", "night", name="roster_shift_name"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("member_id", "assignment_date", name="uq_roster_assignment"),
        )
    indexes = _indexes("roster_assignments")
    if "ix_roster_assignments_member_id" not in indexes:
        op.create_index("ix_roster_assignments_member_id", "roster_assignments", ["member_id"])
    if "ix_roster_assignments_assignment_date" not in indexes:
        op.create_index("ix_roster_assignments_assignment_date", "roster_assignments", ["assignment_date"])

    if "l2_roster" not in _tables():
        op.create_table(
            "l2_roster",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("department", sa.String(length=40), nullable=False),
            sa.Column("week", sa.Integer(), nullable=False),
            sa.Column("engineer_name", sa.String(length=160), nullable=False),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("email", sa.String(length=254), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("department", "week", name="uq_l2_roster_dept_week"),
        )
    if "ix_l2_roster_department" not in _indexes("l2_roster"):
        op.create_index("ix_l2_roster_department", "l2_roster", ["department"])


def downgrade() -> None:
    tables = _tables()
    for table_name, index_names in (
        ("l2_roster", ("ix_l2_roster_department",)),
        ("roster_assignments", ("ix_roster_assignments_assignment_date", "ix_roster_assignments_member_id")),
        ("roster_members", ("ix_roster_members_name",)),
    ):
        if table_name not in tables:
            continue
        existing_indexes = _indexes(table_name)
        for index_name in index_names:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
        tables.remove(table_name)
