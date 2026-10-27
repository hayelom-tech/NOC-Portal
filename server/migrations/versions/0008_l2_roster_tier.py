"""Support tiered L2 domain contacts."""

import sqlalchemy as sa
from alembic import op

revision = "0008_l2_roster_tier"
down_revision = "0007_knowledge_hub_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"]: column for column in sa.inspect(bind).get_columns("l2_roster")}
    if not columns["week"]["nullable"]:
        op.alter_column("l2_roster", "week", existing_type=sa.Integer(), nullable=True)
    if "tier" not in columns:
        op.add_column("l2_roster", sa.Column("tier", sa.String(length=80), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"]: column for column in sa.inspect(bind).get_columns("l2_roster")}
    if "tier" in columns:
        op.drop_column("l2_roster", "tier")
    if columns["week"]["nullable"]:
        op.execute("UPDATE l2_roster SET week = 0 WHERE week IS NULL")
        op.alter_column("l2_roster", "week", existing_type=sa.Integer(), nullable=False)
