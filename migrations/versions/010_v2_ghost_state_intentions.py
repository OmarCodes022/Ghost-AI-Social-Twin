"""v2 ghost_state (singleton) and ghost_intentions tables.

Revision ID: 010
Revises: 009
Create Date: 2026-06-17
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE intention_status AS ENUM ('pending', 'sent', 'cancelled')"
    )

    op.execute(
        """
        CREATE TABLE ghost_state (
            id                INTEGER   PRIMARY KEY DEFAULT 1,
            energy            FLOAT     NOT NULL DEFAULT 0.7,
            mood_summary      TEXT,
            last_reflection_at TIMESTAMP,
            updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ghost_state_singleton CHECK (id = 1)
        )
        """
    )
    op.execute("INSERT INTO ghost_state (id) VALUES (1)")

    op.execute(
        """
        CREATE TABLE ghost_intentions (
            id               UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone    VARCHAR          NOT NULL REFERENCES contacts(phone_number),
            intention_type   VARCHAR          NOT NULL,
            content          TEXT             NOT NULL,
            scheduled_for    TIMESTAMP        NOT NULL,
            status           intention_status NOT NULL DEFAULT 'pending',
            created_at       TIMESTAMP        NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ghost_intentions_scheduled "
        "ON ghost_intentions(scheduled_for) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX idx_ghost_intentions_contact "
        "ON ghost_intentions(contact_phone, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghost_intentions CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_state CASCADE")
    op.execute("DROP TYPE IF EXISTS intention_status")
