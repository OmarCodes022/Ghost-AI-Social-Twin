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
        """
        CREATE TABLE ghost_state (
            id                 INTEGER   PRIMARY KEY DEFAULT 1,
            mood               TEXT,
            social_battery     FLOAT     NOT NULL DEFAULT 0.7,
            emotional_load     FLOAT     NOT NULL DEFAULT 0.3,
            current_focus      TEXT,
            whats_on_mind      TEXT,
            period_description TEXT,
            updated_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_by         VARCHAR,
            CONSTRAINT ghost_state_singleton CHECK (id = 1)
        )
        """
    )
    op.execute("INSERT INTO ghost_state (id) VALUES (1)")

    op.execute(
        """
        CREATE TABLE ghost_intentions (
            id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR   REFERENCES contacts(phone_number),
            intention     TEXT      NOT NULL,
            reason        TEXT,
            status        VARCHAR   NOT NULL DEFAULT 'active',
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            acted_on_at   TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ghost_intentions_active "
        "ON ghost_intentions(status, contact_phone) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghost_intentions CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_state CASCADE")
