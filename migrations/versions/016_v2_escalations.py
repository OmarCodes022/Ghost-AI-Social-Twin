"""v2 escalations table.

Tracks every message Ghost decided he couldn't handle alone.
Written by telegram_bot Lambda on SQS consumption.
Read and resolved by the dashboard (/escalations page).

Revision ID: 016
Revises: 015
Create Date: 2026-06-25
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE escalations (
            id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone   VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            contact_name    VARCHAR,
            message_content TEXT      NOT NULL,
            ghost_reason    TEXT,
            status          VARCHAR   NOT NULL DEFAULT 'pending',
            response        TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved_at     TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_escalations_status ON escalations(status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS escalations CASCADE")
