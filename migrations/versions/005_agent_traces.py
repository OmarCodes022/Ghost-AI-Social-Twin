"""Add agent_traces table.

Stores the full tool call trace for every agent loop run.
The dashboard reads this to show per-reply debugging info:
tool calls + inputs + output summaries, token counts, iteration count.

message_id is nullable — delay actions have no outgoing agent message.

Revision ID: 005
Revises: 004
Create Date: 2026-03-28
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_traces (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id      UUID        REFERENCES messages(id) ON DELETE SET NULL,
            conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            contact_phone   VARCHAR(20) NOT NULL,
            tool_calls      JSONB       NOT NULL DEFAULT '[]',
            input_tokens    INT         NOT NULL DEFAULT 0,
            output_tokens   INT         NOT NULL DEFAULT 0,
            iterations      INT         NOT NULL DEFAULT 0,
            action          VARCHAR(20) NOT NULL DEFAULT 'reply',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ON agent_traces(conversation_id)")
    op.execute("CREATE INDEX ON agent_traces(created_at DESC)")
    op.execute("CREATE INDEX ON agent_traces(message_id) WHERE message_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_traces")
