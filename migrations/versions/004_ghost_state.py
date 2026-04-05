"""Add ghost_state table for persistent mood/availability state.

Single-row table. Ghost reads and updates this via tools during the agent loop.
Also settable externally via `make mood` CLI or Telegram /mood command.

Fields:
  energy          — current energy level (0.0–1.0)
  social_battery  — depletes across conversations over a day, resets overnight
  emotional_load  — accumulates from heavy conversations (grief, conflict, etc.)
  availability    — deep / light / minimal (set externally to gate response depth)
  notes           — free text context: "bad week", "just got back from holiday"

Revision ID: 004
Revises: 003
Create Date: 2026-03-27
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ghost_state (
            id               SERIAL PRIMARY KEY,
            energy           FLOAT        NOT NULL DEFAULT 0.6,
            social_battery   FLOAT        NOT NULL DEFAULT 1.0,
            emotional_load   FLOAT        NOT NULL DEFAULT 0.0,
            availability     VARCHAR(20)  NOT NULL DEFAULT 'deep',
            notes            TEXT,
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("INSERT INTO ghost_state DEFAULT VALUES")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghost_state")
