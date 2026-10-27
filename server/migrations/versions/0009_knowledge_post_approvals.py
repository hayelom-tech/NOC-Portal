"""Add operator article approval and admin notifications."""

import sqlalchemy as sa
from alembic import op


revision = "0009_knowledge_post_approvals"
down_revision = "0008_separate_knowledge_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    article_columns = {column["name"] for column in sa.inspect(bind).get_columns("knowledge_articles")}
    for name, column in (
        ("approval_status", sa.Column("approval_status", sa.String(length=20), server_default="approved", nullable=False)),
        ("approved_by_id", sa.Column("approved_by_id", sa.Integer(), nullable=True)),
        ("approved_at", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if name not in article_columns:
            op.add_column("knowledge_articles", column)

    inspector = sa.inspect(bind)
    article_indexes = {index["name"] for index in inspector.get_indexes("knowledge_articles")}
    if "ix_knowledge_articles_approval_status" not in article_indexes:
        op.create_index("ix_knowledge_articles_approval_status", "knowledge_articles", ["approval_status"])
    approved_by_fks = {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys("knowledge_articles")
    }
    if ("approved_by_id",) not in approved_by_fks:
        op.create_foreign_key(
            "fk_knowledge_articles_approved_by_id_users",
            "knowledge_articles",
            "users",
            ["approved_by_id"],
            ["id"],
        )

    tables = set(inspector.get_table_names())
    if "admin_notifications" not in tables:
        op.create_table(
            "admin_notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recipient_id", sa.Integer(), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("message", sa.String(length=500), nullable=False),
            sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["article_id"], ["knowledge_articles.id"], ondelete="CASCADE"),
        )
    notification_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("admin_notifications")}
    for name, columns in (
        ("ix_admin_notifications_recipient_id", ["recipient_id"]),
        ("ix_admin_notifications_article_id", ["article_id"]),
        ("ix_admin_notifications_created_at", ["created_at"]),
    ):
        if name not in notification_indexes:
            op.create_index(name, "admin_notifications", columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "admin_notifications" in tables:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("admin_notifications")}
        for name in ("ix_admin_notifications_created_at", "ix_admin_notifications_article_id", "ix_admin_notifications_recipient_id"):
            if name in indexes:
                op.drop_index(name, table_name="admin_notifications")
        op.drop_table("admin_notifications")
    article_columns = {column["name"] for column in sa.inspect(bind).get_columns("knowledge_articles")}
    if "approved_by_id" in article_columns:
        for foreign_key in sa.inspect(bind).get_foreign_keys("knowledge_articles"):
            if foreign_key["constrained_columns"] == ["approved_by_id"] and foreign_key["name"]:
                op.drop_constraint(foreign_key["name"], "knowledge_articles", type_="foreignkey")
                break
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("knowledge_articles")}
    if "ix_knowledge_articles_approval_status" in indexes:
        op.drop_index("ix_knowledge_articles_approval_status", table_name="knowledge_articles")
    for name in ("approved_at", "approved_by_id", "approval_status"):
        if name in article_columns:
            op.drop_column("knowledge_articles", name)
