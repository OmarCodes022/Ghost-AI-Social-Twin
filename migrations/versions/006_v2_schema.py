"""v2 schema — full rewrite, all 16 tables

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    # Drop all v1 tables
    op.execute("DROP TABLE IF EXISTS agent_traces CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS contacts CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_state CASCADE")

    op.execute("CREATE EXTENSION IF NOT EXISTS pgvector")

    # 1. contacts
    op.execute("""
        CREATE TABLE contacts (
            phone_number        VARCHAR PRIMARY KEY,
            name                VARCHAR NOT NULL,
            relationship_tier   SMALLINT DEFAULT 3,
            language_primary    VARCHAR,
            language_secondary  VARCHAR,
            texting_style       JSONB,
            personality_summary TEXT,
            current_life_situation TEXT,
            trust_level         FLOAT DEFAULT 0.5,
            risk_level          FLOAT DEFAULT 0.5,
            relationship_goal   TEXT,
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # 2. contact_state
    op.execute("""
        CREATE TABLE contact_state (
            contact_phone               VARCHAR PRIMARY KEY REFERENCES contacts(phone_number),
            current_attitude_score      FLOAT DEFAULT 0.5,
            attitude_trend              FLOAT DEFAULT 0.0,
            attitude_trend_duration     INTEGER DEFAULT 0,
            last_interaction_at         TIMESTAMP,
            last_interaction_role       VARCHAR,
            baseline_frequency          FLOAT,
            conversation_quality_avg    FLOAT DEFAULT 0.5,
            unanswered_message_flag     BOOLEAN DEFAULT FALSE,
            unanswered_since            TIMESTAMP,
            pulse_score                 FLOAT DEFAULT 0.0,
            pulse_score_updated_at      TIMESTAMP,
            last_heartbeat_action       TEXT,
            last_heartbeat_at           TIMESTAMP,
            updated_at                  TIMESTAMP DEFAULT NOW()
        )
    """)

    # 3. conversations
    op.execute("""
        CREATE TABLE conversations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone   VARCHAR REFERENCES contacts(phone_number),
            state           VARCHAR DEFAULT 'open',
            started_at      TIMESTAMP DEFAULT NOW(),
            closed_at       TIMESTAMP,
            message_count   INTEGER DEFAULT 0,
            quality_score   FLOAT,
            emotional_tone  TEXT,
            close_condition JSONB,
            summary         TEXT,
            unresolved_threads JSONB,
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    # 4. messages
    op.execute("""
        CREATE TABLE messages (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id     UUID REFERENCES conversations(id),
            contact_phone       VARCHAR REFERENCES contacts(phone_number),
            role                VARCHAR NOT NULL,
            content             TEXT NOT NULL,
            language            VARCHAR,
            sent_at             TIMESTAMP DEFAULT NOW(),
            was_deferred        BOOLEAN DEFAULT FALSE,
            defer_duration      INTEGER,
            whatsapp_message_id VARCHAR UNIQUE
        )
    """)

    # 5. defer_conditions
    op.execute("""
        CREATE TABLE defer_conditions (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR REFERENCES contacts(phone_number),
            condition     JSONB NOT NULL,
            reason        TEXT,
            created_at    TIMESTAMP DEFAULT NOW(),
            expires_at    TIMESTAMP,
            resolved_at   TIMESTAMP,
            status        VARCHAR DEFAULT 'active'
        )
    """)

    # 6. ghost_state (single row)
    op.execute("""
        CREATE TABLE ghost_state (
            id                  INTEGER PRIMARY KEY DEFAULT 1,
            mood                TEXT,
            social_battery      FLOAT DEFAULT 0.7,
            emotional_load      FLOAT DEFAULT 0.3,
            current_focus       TEXT,
            whats_on_mind       TEXT,
            period_description  TEXT,
            updated_at          TIMESTAMP DEFAULT NOW(),
            updated_by          VARCHAR DEFAULT 'ghost',
            CONSTRAINT single_row CHECK (id = 1)
        )
    """)
    op.execute("INSERT INTO ghost_state (id) VALUES (1)")

    # 7. ghost_intentions
    op.execute("""
        CREATE TABLE ghost_intentions (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR REFERENCES contacts(phone_number),
            intention     TEXT NOT NULL,
            reason        TEXT,
            created_at    TIMESTAMP DEFAULT NOW(),
            acted_on_at   TIMESTAMP,
            status        VARCHAR DEFAULT 'active'
        )
    """)

    # 8. memories (RAG source — vector(1024) for Voyage-3)
    op.execute("""
        CREATE TABLE memories (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone       VARCHAR REFERENCES contacts(phone_number),
            category            VARCHAR NOT NULL,
            content             TEXT NOT NULL,
            language            VARCHAR,
            embedding           vector(1024),
            importance          FLOAT DEFAULT 0.5,
            created_at          TIMESTAMP DEFAULT NOW(),
            created_by          VARCHAR DEFAULT 'ghost',
            source_conversation UUID REFERENCES conversations(id)
        )
    """)
    op.execute("""
        CREATE INDEX memories_embedding_idx
        ON memories USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # 9. life_events
    op.execute("""
        CREATE TABLE life_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone   VARCHAR REFERENCES contacts(phone_number),
            event_type      VARCHAR NOT NULL,
            description     TEXT,
            event_date      DATE NOT NULL,
            lookahead_days  INTEGER DEFAULT 3,
            notified        BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    # 10. per_person_rules
    op.execute("""
        CREATE TABLE per_person_rules (
            contact_phone        VARCHAR PRIMARY KEY REFERENCES contacts(phone_number),
            allowed_topics       JSONB,
            forbidden_topics     JSONB,
            vulnerability_level  FLOAT DEFAULT 0.0,
            humor_allowed        BOOLEAN DEFAULT TRUE,
            image_to_project     TEXT,
            things_to_hide       JSONB,
            message_length_style VARCHAR DEFAULT 'short',
            double_texting       BOOLEAN DEFAULT FALSE,
            updated_at           TIMESTAMP DEFAULT NOW()
        )
    """)

    # 11. ghost_reflections
    op.execute("""
        CREATE TABLE ghost_reflections (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trigger_type  VARCHAR NOT NULL,
            contact_phone VARCHAR REFERENCES contacts(phone_number),
            scratchpad    TEXT,
            decision      TEXT,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    # 12. ghost_custom (Ghost's self-shaping sandbox)
    op.execute("""
        CREATE TABLE ghost_custom (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name    TEXT NOT NULL,
            key           TEXT NOT NULL,
            value         JSONB,
            contact_phone VARCHAR REFERENCES contacts(phone_number),
            notes         TEXT,
            created_at    TIMESTAMP DEFAULT NOW(),
            updated_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    # 13. world_events (PARKED — reserved, not yet designed)
    op.execute("""
        CREATE TABLE world_events (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 14. contact_knowledge_gaps
    op.execute("""
        CREATE TABLE contact_knowledge_gaps (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone     VARCHAR REFERENCES contacts(phone_number),
            field             TEXT NOT NULL,
            priority          FLOAT DEFAULT 0.5,
            asked_at          TIMESTAMP,
            ask_attempt_count INTEGER DEFAULT 0,
            resolved_at       TIMESTAMP,
            status            VARCHAR DEFAULT 'pending',
            created_at        TIMESTAMP DEFAULT NOW()
        )
    """)

    # 15. omar_voice_profiles
    op.execute("""
        CREATE TABLE omar_voice_profiles (
            language            VARCHAR PRIMARY KEY,
            register            TEXT,
            slang               JSONB,
            sentence_structure  TEXT,
            emoji_behavior      TEXT,
            punctuation_habits  TEXT,
            avg_message_length  FLOAT,
            formality_level     FLOAT,
            tone_description    TEXT,
            updated_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # 16. omar_few_shots
    op.execute("""
        CREATE TABLE omar_few_shots (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            language          VARCHAR NOT NULL,
            relationship_tier SMALLINT NOT NULL,
            context           TEXT,
            input             TEXT NOT NULL,
            output            TEXT NOT NULL,
            source            VARCHAR DEFAULT 'manual',
            created_at        TIMESTAMP DEFAULT NOW()
        )
    """)


def downgrade():
    for table in [
        "omar_few_shots", "omar_voice_profiles", "contact_knowledge_gaps",
        "world_events", "ghost_custom", "ghost_reflections", "per_person_rules",
        "life_events", "memories", "ghost_intentions", "ghost_state",
        "defer_conditions", "messages", "conversations", "contact_state",
        "contacts",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
