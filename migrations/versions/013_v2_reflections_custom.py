"""v2 ghost_reflections and ghost_custom (sandbox) tables.

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
            id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone    VARCHAR   REFERENCES contacts(phone_number),
            reflection_type  VARCHAR   NOT NULL,
            content          TEXT      NOT NULL,
            insights         JSONB     NOT NULL DEFAULT '{}',
            created_at       TIMESTAMP NOT NULL DEFAULT NOW()
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
            id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            key        VARCHAR   NOT NULL UNIQUE,
            value      JSONB     NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghost_custom CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_reflections CASCADE")
