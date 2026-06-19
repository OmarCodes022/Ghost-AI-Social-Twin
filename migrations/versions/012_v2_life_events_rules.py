"""v2 life_events and per_person_rules tables.

per_person_rules: ONE row per contact (contact_phone is PK). Structured fields,
not free-text rules. Ghost reads this as a behavioural constraint map.

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
            id             UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone  VARCHAR   REFERENCES contacts(phone_number),
            event_type     VARCHAR   NOT NULL,
            description    TEXT      NOT NULL,
            event_date     DATE,
            lookahead_days INTEGER   NOT NULL DEFAULT 7,
            notified       BOOLEAN   NOT NULL DEFAULT FALSE,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_life_events_contact ON life_events(contact_phone, event_date)"
    )
    op.execute(
        "CREATE INDEX idx_life_events_upcoming "
        "ON life_events(event_date) WHERE notified = FALSE"
    )

    op.execute(
        """
        CREATE TABLE per_person_rules (
            contact_phone      VARCHAR   PRIMARY KEY REFERENCES contacts(phone_number),
            allowed_topics     JSONB     NOT NULL DEFAULT '[]',
            forbidden_topics   JSONB     NOT NULL DEFAULT '[]',
            vulnerability_level FLOAT   NOT NULL DEFAULT 0.5,
            humor_allowed      BOOLEAN   NOT NULL DEFAULT TRUE,
            image_to_project   TEXT,
            things_to_hide     JSONB     NOT NULL DEFAULT '[]',
            message_length_style VARCHAR NOT NULL DEFAULT 'medium',
            double_texting     BOOLEAN   NOT NULL DEFAULT FALSE,
            updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS per_person_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS life_events CASCADE")
