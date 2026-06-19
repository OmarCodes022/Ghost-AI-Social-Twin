"""v2 omar_voice_profiles and omar_few_shots tables.

omar_voice_profiles: ONE row per language (french/english/arabic).
Describes how Omar texts in that language - register, slang, style.

omar_few_shots: keyed by language + relationship_tier, not by contact.
Used as few-shot examples for Ghost to mimic Omar's voice.

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
            language          VARCHAR   PRIMARY KEY,
            register          TEXT,
            slang             JSONB     NOT NULL DEFAULT '[]',
            sentence_structure TEXT,
            emoji_behavior    TEXT,
            punctuation_habits TEXT,
            avg_message_length INTEGER,
            formality_level   FLOAT     NOT NULL DEFAULT 0.5,
            tone_description  TEXT,
            updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE omar_few_shots (
            id                UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            language          VARCHAR   NOT NULL,
            relationship_tier SMALLINT  NOT NULL,
            context           TEXT      NOT NULL,
            input             TEXT      NOT NULL,
            output            TEXT      NOT NULL,
            source            VARCHAR   NOT NULL DEFAULT 'manual',
            created_at        TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_omar_few_shots_lang_tier "
        "ON omar_few_shots(language, relationship_tier)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS omar_few_shots CASCADE")
    op.execute("DROP TABLE IF EXISTS omar_voice_profiles CASCADE")
