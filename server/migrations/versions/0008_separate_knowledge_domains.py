"""Separate the four Knowledge Hub domains from the five L2 domains."""

from alembic import op

revision = "0008_separate_knowledge_domains"
down_revision = "0007_knowledge_hub_domains"
branch_labels = None
depends_on = None


def _rebuild_knowledge_domain(labels: str, conversion: str) -> None:
    op.execute('ALTER TYPE knowledge_domain RENAME TO knowledge_domain_old')
    op.execute(f"CREATE TYPE knowledge_domain AS ENUM ({labels})")
    op.execute(
        "ALTER TABLE knowledge_articles ALTER COLUMN domain TYPE knowledge_domain "
        f"USING ({conversion})::knowledge_domain"
    )
    op.execute("DROP TYPE knowledge_domain_old")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Knowledge domain migration requires PostgreSQL.")

    _rebuild_knowledge_domain(
        "'power', 'ran', 'tx', 'core'",
        "CASE domain::text "
        "WHEN 'transmission' THEN 'tx' "
        "WHEN 'tx' THEN 'tx' "
        "WHEN 'ran' THEN 'ran' "
        "WHEN 'power' THEN 'power' "
        "ELSE 'core' END",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Knowledge domain migration requires PostgreSQL.")

    _rebuild_knowledge_domain(
        "'tx', 'ran', 'power', 'ps_core_sdm', 'cs_core_volte'",
        "CASE domain::text WHEN 'core' THEN 'ps_core_sdm' ELSE domain::text END",
    )
