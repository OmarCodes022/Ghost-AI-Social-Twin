"""v2 life_events and per_person_rules tables.

Revision ID: 012
Revises: 011
Create Date: 2026-06-17
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE life_events (
            id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type       VARCHAR   NOT NULL,
            description      TEXT      NOT NULL,
            event_date       DATE,
            importance       FLOAT     NOT NULL DEFAULT 0.5,
            people_involved  JSONB     NOT NULL DEFAULT '[]',
            created_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_life_events_date ON life_events(event_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE per_person_rules (
            id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            rule          TEXT      NOT NULL,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_per_person_rules_contact ON per_person_rules(contact_phone)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS per_person_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS life_events CASCADE")
