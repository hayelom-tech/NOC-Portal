"""Create incidents and change_requests tables."""

import sqlalchemy as sa
from alembic import op

revision = "0015_incidents_cr"
down_revision = "0014_roster_team_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum types (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE incident_priority AS ENUM ('P1', 'P2', 'P3', 'P4', 'P5');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE incident_status AS ENUM ('ongoing', 'resolved', 'closed');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE change_status AS ENUM ('in_progress', 'scheduled', 'completed', 'cancelled', 'rollback');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE change_risk AS ENUM ('low', 'medium', 'high');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE cm_region AS ENUM ('East 1', 'East 2', 'West', 'North West', 'North East', 'North', 'Afar');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create incidents table
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column(
            "priority",
            sa.Enum("P1", "P2", "P3", "P4", "P5", name="incident_priority", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("ongoing", "resolved", "closed", name="incident_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "region",
            sa.Enum(
                "East 1", "East 2", "West", "North West", "North East", "North", "Afar",
                name="cm_region", create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_impact", sa.String(length=255), nullable=True),
        sa.Column("system_impact", sa.String(length=255), nullable=True),
        sa.Column("incident_owner", sa.String(length=160), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mttr", sa.String(length=80), nullable=True),
        sa.Column("reported_by", sa.String(length=160), nullable=True),
        sa.Column("support_group", sa.String(length=160), nullable=True),
        sa.Column("problem_statement", sa.Text(), nullable=True),
        sa.Column("update", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_incidents_reference", "incidents", ["reference"], unique=True)
    op.create_index("ix_incidents_priority", "incidents", ["priority"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_region", "incidents", ["region"])
    op.create_index("ix_incidents_status_priority", "incidents", ["status", "priority"])
    # Create change_requests table
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cr_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "in_progress", "scheduled", "completed", "cancelled", "rollback",
                name="change_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            sa.Enum("low", "medium", "high", name="change_risk", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "region",
            sa.Enum(
                "East 1", "East 2", "West", "North West", "North East", "North", "Afar",
                name="cm_region", create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_engineer", sa.String(length=160), nullable=True),
        sa.Column("approver", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_change_requests_cr_id", "change_requests", ["cr_id"], unique=True)
    op.create_index("ix_change_requests_domain", "change_requests", ["domain"])
    op.create_index("ix_change_requests_status", "change_requests", ["status"])
    op.create_index("ix_change_requests_region", "change_requests", ["region"])
    op.create_index("ix_change_requests_status_risk", "change_requests", ["status", "risk_level"])


def downgrade() -> None:
    op.drop_index("ix_change_requests_status_risk", table_name="change_requests")
    op.drop_index("ix_change_requests_region", table_name="change_requests")
    op.drop_index("ix_change_requests_status", table_name="change_requests")
    op.drop_index("ix_change_requests_domain", table_name="change_requests")
    op.drop_index("ix_change_requests_cr_id", table_name="change_requests")
    op.drop_table("change_requests")

    op.drop_index("ix_incidents_status_priority", table_name="incidents")
    op.drop_index("ix_incidents_region", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_priority", table_name="incidents")
    op.drop_index("ix_incidents_reference", table_name="incidents")
    op.drop_table("incidents")

    op.execute("DROP TYPE incident_priority")
    op.execute("DROP TYPE incident_status")
    op.execute("DROP TYPE change_status")
    op.execute("DROP TYPE change_risk")
    op.execute("DROP TYPE cm_region")
