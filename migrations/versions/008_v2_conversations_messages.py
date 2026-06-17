"""v2 conversations and messages tables.

Revision ID: 008
Revises: 007
Create Date: 2026-06-17
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'ghost')")

    op.execute(
        """
        CREATE TABLE conversations (
            id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone   VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMP NOT NULL DEFAULT NOW(),
            ended_at        TIMESTAMP,
            message_count   INTEGER   NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_conversations_contact ON conversations(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_conversations_active ON conversations(contact_phone) "
        "WHERE ended_at IS NULL"
    )

    op.execute(
        """
        CREATE TABLE messages (
            id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id     UUID         NOT NULL REFERENCES conversations(id),
            contact_phone       VARCHAR      NOT NULL REFERENCES contacts(phone_number),
            role                message_role NOT NULL,
            content             TEXT         NOT NULL,
            whatsapp_message_id VARCHAR      UNIQUE,
            sent_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
            processed           BOOLEAN      NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_messages_conversation ON messages(conversation_id)"
    )
    op.execute(
        "CREATE INDEX idx_messages_contact ON messages(contact_phone, sent_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TYPE IF EXISTS message_role")
