"""Constrain L2 roster domains and knowledge approval states."""

import sqlalchemy as sa
from alembic import op


revision = "0013_domain_and_approval_checks"
down_revision = "0012_roster_member_user_email"
branch_labels = None
depends_on = None


L2_DOMAINS = ("tx", "ran", "power", "ps_core_sdm", "cs_core_volte")
L2_DOMAIN_SQL = ", ".join(f"'{domain}'" for domain in L2_DOMAINS)


def upgrade() -> None:
    bind = op.get_bind()
    conflicts = bind.execute(sa.text("""
        WITH normalized AS (
            SELECT
                week,
                CASE regexp_replace(lower(trim(department)), '[^a-z0-9]', '', 'g')
                    WHEN 'tx' THEN 'tx'
                    WHEN 'transmission' THEN 'tx'
                    WHEN 'ran' THEN 'ran'
                    WHEN 'radioaccessnetwork' THEN 'ran'
                    WHEN 'radioaccessnetworkran' THEN 'ran'
                    WHEN 'power' THEN 'power'
                    WHEN 'pwr' THEN 'power'
                    WHEN 'pscore' THEN 'ps_core_sdm'
                    WHEN 'pscoresdm' THEN 'ps_core_sdm'
                    WHEN 'cscore' THEN 'cs_core_volte'
                    WHEN 'cscorevolte' THEN 'cs_core_volte'
                    ELSE department
                END AS normalized_department
            FROM l2_roster
        )
        SELECT normalized_department, week
        FROM normalized
        WHERE week IS NOT NULL
        GROUP BY normalized_department, week
        HAVING count(*) > 1
        LIMIT 10
    """)).all()
    if conflicts:
        raise RuntimeError(
            "Cannot normalize L2 roster domains: multiple rows would share a department and week "
            "after normalization. Resolve these department/week pairs first: "
            + ", ".join(f"{department!r}/week {week}" for department, week in conflicts)
        )

    bind.execute(sa.text("""
        UPDATE l2_roster
        SET department = CASE regexp_replace(lower(trim(department)), '[^a-z0-9]', '', 'g')
            WHEN 'tx' THEN 'tx'
            WHEN 'transmission' THEN 'tx'
            WHEN 'ran' THEN 'ran'
            WHEN 'radioaccessnetwork' THEN 'ran'
            WHEN 'radioaccessnetworkran' THEN 'ran'
            WHEN 'power' THEN 'power'
            WHEN 'pwr' THEN 'power'
            WHEN 'pscore' THEN 'ps_core_sdm'
            WHEN 'pscoresdm' THEN 'ps_core_sdm'
            WHEN 'cscore' THEN 'cs_core_volte'
            WHEN 'cscorevolte' THEN 'cs_core_volte'
            ELSE department
        END
    """))
    invalid_departments = bind.execute(sa.text(
        f"SELECT DISTINCT department FROM l2_roster "
        f"WHERE department NOT IN ({L2_DOMAIN_SQL}) LIMIT 10"
    )).scalars().all()
    if invalid_departments:
        raise RuntimeError(
            "Cannot add the L2 roster domain constraint; normalize these department values first: "
            + ", ".join(repr(value) for value in invalid_departments)
        )

    inspector = sa.inspect(bind)
    roster_checks = {check["name"] for check in inspector.get_check_constraints("l2_roster")}
    if "ck_l2_roster_department" not in roster_checks:
        op.create_check_constraint(
            "ck_l2_roster_department",
            "l2_roster",
            "department IN ('tx', 'ran', 'power', 'ps_core_sdm', 'cs_core_volte')",
        )

    article_checks = {
        check["name"] for check in inspector.get_check_constraints("knowledge_articles")
    }
    if "ck_knowledge_articles_approval_status" not in article_checks:
        op.create_check_constraint(
            "ck_knowledge_articles_approval_status",
            "knowledge_articles",
            "approval_status IN ('pending', 'approved', 'rejected')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    article_checks = {
        check["name"] for check in inspector.get_check_constraints("knowledge_articles")
    }
    if "ck_knowledge_articles_approval_status" in article_checks:
        op.drop_constraint(
            "ck_knowledge_articles_approval_status",
            "knowledge_articles",
            type_="check",
        )

    roster_checks = {check["name"] for check in inspector.get_check_constraints("l2_roster")}
    if "ck_l2_roster_department" in roster_checks:
        op.drop_constraint("ck_l2_roster_department", "l2_roster", type_="check")
