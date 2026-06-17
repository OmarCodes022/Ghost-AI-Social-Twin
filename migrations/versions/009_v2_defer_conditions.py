"""v2 defer_conditions table - the condition system.
Ghost writes conditions; Pulse evaluates them mechanically (no LLM).

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
        "CREATE TYPE condition_status AS ENUM ('pending', 'resolved', 'expired', 'cancelled')"
    )

    op.execute(
        """
        CREATE TABLE defer_conditions (
            id               UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone    VARCHAR          NOT NULL REFERENCES contacts(phone_number),
            condition_type   VARCHAR          NOT NULL,
            condition_data   JSONB            NOT NULL DEFAULT '{}',
            target_action    VARCHAR          NOT NULL,
            target_payload   JSONB            NOT NULL DEFAULT '{}',
            status           condition_status NOT NULL DEFAULT 'pending',
            created_at       TIMESTAMP        NOT NULL DEFAULT NOW(),
            expires_at       TIMESTAMP,
            resolved_at      TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_defer_conditions_contact ON defer_conditions(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_defer_conditions_pending "
        "ON defer_conditions(status, expires_at) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS defer_conditions CASCADE")
    op.execute("DROP TYPE IF EXISTS condition_status")
