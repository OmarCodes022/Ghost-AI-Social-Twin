"""v2 omar_voice_profiles and omar_few_shots tables.

Revision ID: 015
Revises: 014
Create Date: 2026-06-17
"""
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE omar_voice_profiles (
            contact_phone VARCHAR   PRIMARY KEY REFERENCES contacts(phone_number),
            style_notes   TEXT,
            vocab_examples JSONB   NOT NULL DEFAULT '[]',
            tone          VARCHAR,
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE omar_few_shots (
            id             UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone  VARCHAR   REFERENCES contacts(phone_number),
            scenario       TEXT      NOT NULL,
            input_message  TEXT      NOT NULL,
            ideal_response TEXT      NOT NULL,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_omar_few_shots_contact ON omar_few_shots(contact_phone)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS omar_few_shots CASCADE")
    op.execute("DROP TABLE IF EXISTS omar_voice_profiles CASCADE")
