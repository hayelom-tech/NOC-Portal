"""Store admin uploaded NOC reference documents."""

import sqlalchemy as sa
from alembic import op


revision = "0010_process_documents"
down_revision = "0009_knowledge_post_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "process_documents" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "process_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("process_documents")}
    if "ix_process_documents_created_at" not in indexes:
        op.create_index("ix_process_documents_created_at", "process_documents", ["created_at"])


def downgrade() -> None:
    if "process_documents" in sa.inspect(op.get_bind()).get_table_names():
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("process_documents")}
        if "ix_process_documents_created_at" in indexes:
            op.drop_index("ix_process_documents_created_at", table_name="process_documents")
        op.drop_table("process_documents")
