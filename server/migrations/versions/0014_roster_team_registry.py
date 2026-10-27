"""Replace Front Office roster team strings with a constrained registry."""

import sqlalchemy as sa
from alembic import op


revision = "0014_roster_team_registry"
down_revision = "0013_domain_and_approval_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "roster_teams" not in tables:
        op.create_table(
            "roster_teams",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("challenge_domain", sa.String(length=20), nullable=True),
            sa.UniqueConstraint("name", name="uq_roster_teams_name"),
            sa.CheckConstraint(
                "challenge_domain IS NULL OR challenge_domain IN ('power', 'tx')",
                name="ck_roster_teams_challenge_domain",
            ),
        )
    else:
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("roster_teams")
        }
        if "ck_roster_teams_challenge_domain" not in checks:
            op.create_check_constraint(
                "ck_roster_teams_challenge_domain",
                "roster_teams",
                "challenge_domain IS NULL OR challenge_domain IN ('power', 'tx')",
            )
        indexes = {index["name"] for index in inspector.get_indexes("roster_teams")}
        if "uq_roster_teams_name_lower" not in indexes:
            op.create_index(
                "uq_roster_teams_name_lower",
                "roster_teams",
                [sa.text("lower(name)")],
                unique=True,
            )

    roster_member_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("roster_members")
    }
    if "team" in roster_member_columns:
        collisions = bind.execute(sa.text("""
            SELECT lower(trim(team)) AS normalized_name,
                   array_agg(DISTINCT trim(team)) AS labels
            FROM roster_members
            WHERE team IS NOT NULL AND trim(team) <> ''
            GROUP BY lower(trim(team))
            HAVING count(DISTINCT trim(team)) > 1
            LIMIT 10
        """)).all()
        if collisions:
            raise RuntimeError(
                "Cannot create roster team registry because existing labels collide "
                "case-insensitively. Resolve these labels first: "
                + ", ".join(f"{key!r}: {labels!r}" for key, labels in collisions)
            )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("roster_teams")}
    if "uq_roster_teams_name_lower" not in indexes:
        op.create_index(
            "uq_roster_teams_name_lower",
            "roster_teams",
            [sa.text("lower(name)")],
            unique=True,
        )

    aliases = (
        ("Power", "power"),
        ("Power Domain", "power"),
        ("Power Gen", "power"),
        ("Power Generation", "power"),
        ("Pwr", "power"),
        ("TX", "tx"),
        ("Transmission", "tx"),
        ("Transmission Domain", "tx"),
    )
    bind.execute(
        sa.text("""
            INSERT INTO roster_teams (name, challenge_domain)
            VALUES (:name, :challenge_domain)
            ON CONFLICT DO NOTHING
        """),
        [
            {"name": name, "challenge_domain": domain}
            for name, domain in aliases
        ],
    )

    if "team" not in roster_member_columns and "roster_team_id" not in roster_member_columns:
        raise RuntimeError("roster_members has neither a team label nor a roster_team_id column.")

    if "team" in roster_member_columns:
        bind.execute(sa.text("""
            INSERT INTO roster_teams (name, challenge_domain)
            SELECT DISTINCT trim(team),
                CASE regexp_replace(lower(trim(team)), '[^a-z0-9]', '', 'g')
                    WHEN 'power' THEN 'power'
                    WHEN 'powerdomain' THEN 'power'
                    WHEN 'powergen' THEN 'power'
                    WHEN 'powergeneration' THEN 'power'
                    WHEN 'pwr' THEN 'power'
                    WHEN 'tx' THEN 'tx'
                    WHEN 'transmission' THEN 'tx'
                    WHEN 'transmissiondomain' THEN 'tx'
                    ELSE NULL
                END
            FROM roster_members
            WHERE team IS NOT NULL AND trim(team) <> ''
            ON CONFLICT DO NOTHING
        """))

        if "roster_team_id" not in roster_member_columns:
            op.add_column(
                "roster_members",
                sa.Column("roster_team_id", sa.Integer(), nullable=True),
            )
        bind.execute(sa.text("""
            UPDATE roster_members AS member
            SET roster_team_id = team.id
            FROM roster_teams AS team
            WHERE member.team IS NOT NULL
              AND trim(member.team) <> ''
              AND lower(trim(member.team)) = lower(team.name)
        """))
        unassigned = bind.execute(sa.text("""
            SELECT name, team
            FROM roster_members
            WHERE team IS NOT NULL AND trim(team) <> '' AND roster_team_id IS NULL
            LIMIT 10
        """)).all()
        if unassigned:
            raise RuntimeError(
                "Cannot migrate these roster members to the team registry: "
                + ", ".join(f"{name!r} ({team!r})" for name, team in unassigned)
            )

    foreign_keys = {
        foreign_key["name"]
        for foreign_key in sa.inspect(bind).get_foreign_keys("roster_members")
    }
    if "fk_roster_members_roster_team_id_roster_teams" not in foreign_keys:
        op.create_foreign_key(
            "fk_roster_members_roster_team_id_roster_teams",
            "roster_members",
            "roster_teams",
            ["roster_team_id"],
            ["id"],
        )
    member_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("roster_members")
    }
    if "ix_roster_members_roster_team_id" not in member_indexes:
        op.create_index("ix_roster_members_roster_team_id", "roster_members", ["roster_team_id"])
    if "team" in roster_member_columns:
        op.drop_column("roster_members", "team")


def downgrade() -> None:
    op.add_column("roster_members", sa.Column("team", sa.String(length=40), nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE roster_members AS member
        SET team = registry.name
        FROM roster_teams AS registry
        WHERE member.roster_team_id = registry.id
    """))
    op.drop_index("ix_roster_members_roster_team_id", table_name="roster_members")
    op.drop_constraint(
        "fk_roster_members_roster_team_id_roster_teams",
        "roster_members",
        type_="foreignkey",
    )
    op.drop_column("roster_members", "roster_team_id")
    op.drop_index("uq_roster_teams_name_lower", table_name="roster_teams")
    op.drop_table("roster_teams")
