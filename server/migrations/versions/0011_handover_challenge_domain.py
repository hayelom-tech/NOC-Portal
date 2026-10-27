"""Route operational challenges to Power or Transmission."""

import sqlalchemy as sa
from alembic import op


revision = "0011_handover_challenge_domain"
down_revision = "5c11013ee6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("handovers")}
    if "challenge_domain" not in columns:
        op.add_column("handovers", sa.Column("challenge_domain", sa.String(length=20), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("handovers")}
    if "challenge_domain" in columns:
        op.drop_column("handovers", "challenge_domain")
