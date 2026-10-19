"""Alembic setup: reads our models and the same DATABASE_URL the app uses."""
from alembic import context

from app import models  # noqa: F401  (importing registers every table on Base)
from app.db import Base, engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",  # SQLite can't ALTER tables directly
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()