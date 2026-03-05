"""Initial schema — contacts, conversations, messages, mood_states,
knowledge_chunks (pgvector), escalations.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # gen_random_uuid() is built-in from PostgreSQL 13+; no pgcrypto needed.

    # ── ENUM types ────────────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE arc_state AS ENUM ('open', 'flowing', 'winding_down', 'dormant')"
    )
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'agent')")
    op.execute(
        "CREATE TYPE knowledge_category AS ENUM "
        "('identity', 'opinion', 'relationship', 'behavioral')"
    )
    op.execute(
        "CREATE TYPE knowledge_source AS ENUM ('manual', 'import', 'learned')"
    )
    op.execute(
        "CREATE TYPE escalation_resolution AS ENUM "
        "('sent', 'edited', 'skipped', 'paused')"
    )

    # ── contacts ──────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE contacts (
            phone_number          VARCHAR PRIMARY KEY,
            name                  VARCHAR,
            relationship_tier     SMALLINT  NOT NULL DEFAULT 3,
            voice_profile         JSONB,
            last_interaction      TIMESTAMP,
            interaction_frequency FLOAT     NOT NULL DEFAULT 0.0,
            notes                 TEXT,
            created_at            TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # ── mood_states (created before messages — messages FK here) ──────────────
    op.execute(
        """
        CREATE TABLE mood_states (
            id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            computed_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            energy           FLOAT     NOT NULL DEFAULT 0.5,
            warmth           FLOAT     NOT NULL DEFAULT 0.5,
            humor_threshold  FLOAT     NOT NULL DEFAULT 0.5,
            openness         FLOAT     NOT NULL DEFAULT 0.5,
            patience         FLOAT     NOT NULL DEFAULT 0.5,
            signals          JSONB     NOT NULL DEFAULT '{}'
        )
        """
    )

    # ── conversations ─────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE conversations (
            id               UUID        PRIMARY KEY,
            contact_phone    VARCHAR     NOT NULL REFERENCES contacts(phone_number),
            arc_state        arc_state   NOT NULL DEFAULT 'open',
            started_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
            last_message_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
            message_count    INTEGER     NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_conversations_contact_phone ON conversations(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_conversations_arc_state ON conversations(arc_state)"
    )

    # ── messages ──────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE messages (
            id               UUID          PRIMARY KEY,
            conversation_id  UUID          NOT NULL REFERENCES conversations(id),
            role             message_role  NOT NULL,
            content          TEXT          NOT NULL,
            sent_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
            was_delayed      BOOLEAN       NOT NULL DEFAULT FALSE,
            delay_seconds    INTEGER       NOT NULL DEFAULT 0,
            mood_state_id    UUID          REFERENCES mood_states(id),
            confidence_score FLOAT         NOT NULL DEFAULT 1.0,
            escalated        BOOLEAN       NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_messages_conversation_id ON messages(conversation_id)"
    )

    # ── knowledge_chunks (pgvector) ───────────────────────────────────────────
    # Create with TEXT first, then ALTER to vector(1536) so Alembic doesn't
    # need to know about the custom type.
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
            id            UUID               PRIMARY KEY DEFAULT gen_random_uuid(),
            category      knowledge_category NOT NULL,
            content       TEXT               NOT NULL,
            embedding     TEXT,
            contact_phone VARCHAR            REFERENCES contacts(phone_number),
            created_at    TIMESTAMP          NOT NULL DEFAULT NOW(),
            source        knowledge_source   NOT NULL DEFAULT 'manual'
        )
        """
    )
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    # IVFFlat index for fast cosine-distance lookups (<=>).
    # lists=100 is appropriate for up to ~1M rows; tune as data grows.
    op.execute(
        "CREATE INDEX idx_knowledge_chunks_embedding "
        "ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_chunks_contact ON knowledge_chunks(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_chunks_category ON knowledge_chunks(category)"
    )

    # ── escalations ───────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE escalations (
            id                  UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id          UUID                  NOT NULL REFERENCES messages(id),
            reason              TEXT                  NOT NULL,
            confidence          FLOAT                 NOT NULL,
            telegram_message_id VARCHAR,
            resolution          escalation_resolution,
            resolved_at         TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_escalations_message_id ON escalations(message_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS escalations")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS mood_states")
    op.execute("DROP TABLE IF EXISTS contacts")

    op.execute("DROP TYPE IF EXISTS escalation_resolution")
    op.execute("DROP TYPE IF EXISTS knowledge_source")
    op.execute("DROP TYPE IF EXISTS knowledge_category")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS arc_state")

    op.execute("DROP EXTENSION IF EXISTS vector")
