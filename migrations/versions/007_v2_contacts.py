"""v2 contacts and contact_state tables.

Revision ID: 007
Revises: 006
Create Date: 2026-06-17
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contacts (
            phone_number          VARCHAR   PRIMARY KEY,
            name                  VARCHAR   NOT NULL,
            relationship_tier     SMALLINT  NOT NULL DEFAULT 3,
            language_primary      VARCHAR   NOT NULL DEFAULT 'french',
            language_secondary    VARCHAR,
            texting_style         JSONB     NOT NULL DEFAULT '{}',
            personality_summary   TEXT,
            current_life_situation TEXT,
            trust_level           FLOAT     NOT NULL DEFAULT 0.5,
            risk_level            FLOAT     NOT NULL DEFAULT 0.0,
            relationship_goal     TEXT,
            created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE contact_state (
            contact_phone             VARCHAR   PRIMARY KEY REFERENCES contacts(phone_number),
            current_attitude_score    FLOAT     NOT NULL DEFAULT 0.0,
            attitude_trend            VARCHAR   NOT NULL DEFAULT 'stable',
            attitude_trend_duration   INTEGER   NOT NULL DEFAULT 0,
            last_interaction_at       TIMESTAMP,
            last_interaction_role     VARCHAR,
            baseline_frequency        FLOAT,
            conversation_quality_avg  FLOAT     NOT NULL DEFAULT 0.5,
            unanswered_message_flag   BOOLEAN   NOT NULL DEFAULT FALSE,
            unanswered_since          TIMESTAMP,
            pulse_score               FLOAT     NOT NULL DEFAULT 0.0,
            pulse_score_updated_at    TIMESTAMP,
            last_heartbeat_action     TEXT,
            last_heartbeat_at         TIMESTAMP,
            updated_at                TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_contact_state_unanswered "
        "ON contact_state(unanswered_message_flag) WHERE unanswered_message_flag = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_state CASCADE")
    op.execute("DROP TABLE IF EXISTS contacts CASCADE")
