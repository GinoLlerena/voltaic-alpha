"""Alembic environment.

The URL comes from the application's own `Settings`, not from `alembic.ini`, so
a migration cannot be pointed at a database the application itself would refuse
to open. `target_metadata` is the live model metadata, which lets `--autogenerate`
diff a real database against the code.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from options_alpha_lab.config import load_settings
from options_alpha_lab.persistence.models import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    # An explicit -x url= wins, so a rehearsal can target a scratch copy without
    # editing configuration or exporting a variable over the real one. A URL the
    # caller already set on the Config comes next: `create_schema` and
    # `upgrade_schema` pass the engine they are working on, and reaching past it
    # to `Settings` would make an in-process migration depend on the ambient
    # environment - which is how a test database ends up demanding BOT_MODE.
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return str(override)
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return load_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode rebuilds the
            # table instead, so the same revision runs on both backends.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
