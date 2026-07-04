"""initial create — auctions schema, auctions + items tables

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "auctions"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "auctions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reserve_price", sa.Integer(), nullable=False),
        sa.Column("seller", sa.String(), nullable=False),
        sa.Column("winner", sa.String(), nullable=True),
        sa.Column("sold_amount", sa.Integer(), nullable=True),
        sa.Column("current_high_bid", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auction_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("Live", "Finished", "ReserveNotMet", name="status", schema=SCHEMA),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("make", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("mileage", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column(
            "auction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.auctions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("items", schema=SCHEMA)
    op.drop_table("auctions", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.status")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
