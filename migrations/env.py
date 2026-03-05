"""Alembic environment script.

The DB connection string is read from the ``DATABASE_URL`` environment variable.
Before running migrations, populate it from SSM:

    export DATABASE_URL=$(aws ssm get-parameter \\
        --name /ghost/db/connection_string \\
        --with-decryption --query Parameter.Value --output text)

Or use ``make migrate`` which performs this check automatically.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy metadata — we use raw SQL in migration scripts.
target_metadata = None


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Run: export DATABASE_URL=$(aws ssm get-parameter "
            "--name /ghost/db/connection_string --with-decryption "
            "--query Parameter.Value --output text)"
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, does not connect)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the DB)."""
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
