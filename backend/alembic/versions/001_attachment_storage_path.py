"""add storage_path to attachments (local disk cache)

Revision ID: 001_attachment_storage_path
Revises:
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "001_attachment_storage_path"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # storage_path já existe no modelo ORM mas pode não estar na tabela em
    # instalações anteriores ao campo ter sido adicionado. O IF NOT EXISTS
    # torna a migração idempotente.
    op.execute(
        """
        ALTER TABLE attachments
        ADD COLUMN IF NOT EXISTS storage_path VARCHAR(500)
        """
    )


def downgrade() -> None:
    op.drop_column("attachments", "storage_path")
