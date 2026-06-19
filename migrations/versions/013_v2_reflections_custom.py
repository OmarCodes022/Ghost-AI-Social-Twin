"""v2 ghost_reflections and ghost_custom (sandbox) tables.

ghost_custom: Ghost's own freeform storage. Ghost invents table_name as a
taxonomy key (e.g. "omar_social_calendar", "contact_vibes"). No schema
enforced - Ghost decides what to store and how to categorise it.

Revision ID: 013
Revises: 012
Create Date: 2026-06-17
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ghost_reflections (
            id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            trigger_type  VARCHAR   NOT NULL,
            contact_phone VARCHAR   REFERENCES contacts(phone_number),
            scratchpad    TEXT,
            decision      TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ghost_reflections_contact "
        "ON ghost_reflections(contact_phone, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE ghost_custom (
            id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name    TEXT      NOT NULL,
            key           TEXT      NOT NULL,
            value         JSONB     NOT NULL,
            contact_phone VARCHAR   REFERENCES contacts(phone_number),
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ghost_custom_table ON ghost_custom(table_name, key)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghost_custom CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_reflections CASCADE")
