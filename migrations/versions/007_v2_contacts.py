"""v2 contacts and contact_state tables.

Revision ID: 007
Revises: 006
Create Date: 2026-06-17
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE contact_status AS ENUM ('active', 'idle', 'dormant')")

    op.execute(
        """
        CREATE TABLE contacts (
            phone_number      VARCHAR   PRIMARY KEY,
            name              VARCHAR   NOT NULL,
            relationship_tier SMALLINT  NOT NULL DEFAULT 3,
            platform          VARCHAR   NOT NULL DEFAULT 'whatsapp',
            active            BOOLEAN   NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE contact_state (
            contact_phone   VARCHAR        PRIMARY KEY REFERENCES contacts(phone_number),
            status          contact_status NOT NULL DEFAULT 'idle',
            last_seen_at    TIMESTAMP,
            last_message_at TIMESTAMP,
            pending_action  TEXT,
            ghost_notes     JSONB          NOT NULL DEFAULT '{}',
            updated_at      TIMESTAMP      NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_state_status ON contact_state(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_state CASCADE")
    op.execute("DROP TABLE IF EXISTS contacts CASCADE")
    op.execute("DROP TYPE IF EXISTS contact_status")
