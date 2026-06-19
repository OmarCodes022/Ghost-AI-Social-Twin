"""v2 defer_conditions - the condition system.

Ghost writes structured conditions; Pulse evaluates them mechanically every 1-2 min.
No LLM involved in evaluation. A condition is a single JSONB blob describing
what must be true before Ghost acts (e.g. time elapsed, reply received, etc.).

Revision ID: 009
Revises: 008
Create Date: 2026-06-17
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE defer_conditions (
            id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            condition     JSONB     NOT NULL,
            reason        TEXT      NOT NULL,
            status        VARCHAR   NOT NULL DEFAULT 'active',
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at    TIMESTAMP,
            resolved_at   TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_defer_conditions_active "
        "ON defer_conditions(contact_phone, expires_at) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS defer_conditions CASCADE")
