"""outbox — the transactional outbox table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "auctions"


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_outbox_unprocessed",
        "outbox",
        ["created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_unprocessed", table_name="outbox", schema=SCHEMA)
    op.drop_table("outbox", schema=SCHEMA)
