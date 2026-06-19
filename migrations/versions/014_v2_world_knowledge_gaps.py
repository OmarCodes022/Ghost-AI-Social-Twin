"""v2 world_events and contact_knowledge_gaps tables.

contact_knowledge_gaps: things Ghost doesn't know about a contact and wants
to learn. field is a specific attribute name (e.g. "city", "job", "relationship_status").

Revision ID: 014
Revises: 013
Create Date: 2026-06-17
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE world_events (
            id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type VARCHAR   NOT NULL,
            title      TEXT      NOT NULL,
            summary    TEXT,
            event_at   TIMESTAMP,
            source_url TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_world_events_type ON world_events(event_type, event_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE contact_knowledge_gaps (
            id                UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone     VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            field             TEXT      NOT NULL,
            priority          FLOAT     NOT NULL DEFAULT 0.5,
            asked_at          TIMESTAMP,
            ask_attempt_count INTEGER   NOT NULL DEFAULT 0,
            resolved_at       TIMESTAMP,
            status            VARCHAR   NOT NULL DEFAULT 'pending',
            created_at        TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_knowledge_gaps_contact "
        "ON contact_knowledge_gaps(contact_phone, priority DESC) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_knowledge_gaps CASCADE")
    op.execute("DROP TABLE IF EXISTS world_events CASCADE")
