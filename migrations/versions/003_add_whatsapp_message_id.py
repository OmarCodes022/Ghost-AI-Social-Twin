"""Add whatsapp_message_id to messages table.

Stores the inbound WhatsApp message ID (wamid) on each user message.
Enables:
  1. Deduplication — if Meta delivers the same webhook twice, the second
     invocation is discarded before doing any work.
  2. Reply bubbles — the orchestrator reads the wamid of the last pending
     message in a burst and passes it to whatsapp_sender so the reply shows
     a WhatsApp quote bubble pointing at that specific message.

Revision ID: 003
Revises: 002
Create Date: 2026-03-27
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages ADD COLUMN whatsapp_message_id VARCHAR(255)"
    )
    op.execute(
        "CREATE INDEX idx_messages_whatsapp_msg_id ON messages(whatsapp_message_id)"
    )
    # Partial unique index — NULL values (agent messages) are excluded
    op.execute(
        """
        CREATE UNIQUE INDEX idx_messages_whatsapp_msg_id_unique
        ON messages(whatsapp_message_id)
        WHERE whatsapp_message_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_whatsapp_msg_id_unique")
    op.execute("DROP INDEX IF EXISTS idx_messages_whatsapp_msg_id")
    op.execute("ALTER TABLE messages DROP COLUMN whatsapp_message_id")
