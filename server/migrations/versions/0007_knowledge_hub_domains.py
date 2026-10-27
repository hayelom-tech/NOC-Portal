"""Update L2 and knowledge domains for the Knowledge Hub."""

import sqlalchemy as sa
from alembic import op

revision = "0007_knowledge_hub_domains"
down_revision = "0006_roster"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("L2 domain enum migration requires PostgreSQL.")

    enum_labels = {item["name"]: set(item["labels"]) for item in sa.inspect(bind).get_enums()}
    for enum_name in ("l2_domain", "knowledge_domain"):
        labels = enum_labels.get(enum_name, set())
        if "transmission" in labels and "tx" not in labels:
            op.execute(f'ALTER TYPE "{enum_name}" RENAME VALUE \'transmission\' TO \'tx\'')
        if "core" in labels and "ps_core_sdm" not in labels:
            op.execute(f'ALTER TYPE "{enum_name}" RENAME VALUE \'core\' TO \'ps_core_sdm\'')

    op.execute("ALTER TYPE l2_domain ADD VALUE IF NOT EXISTS 'cs_core_volte'")
    op.execute("ALTER TYPE knowledge_domain ADD VALUE IF NOT EXISTS 'cs_core_volte'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum labels without rebuilding the enum types.
    # Keep the added label on downgrade so existing CS Core/VoLTE records remain valid.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("L2 domain enum migration requires PostgreSQL.")
