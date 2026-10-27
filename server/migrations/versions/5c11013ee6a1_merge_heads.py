"""merge heads

Revision ID: 5c11013ee6a1
Revises: 0009_seed_l2_contacts, 0010_process_documents
Create Date: 2026-10-18 20:01:06.219259
"""
from alembic import op
import sqlalchemy as sa


revision = '5c11013ee6a1'
down_revision = ('0009_seed_l2_contacts', '0010_process_documents')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
