"""Migration configuration shares application settings without logging credentials."""

from sqlalchemy import create_engine, pool

from alembic import context
from backend.app import models  # noqa: F401 -- register every mapped table
from backend.app.core.config import get_settings
from backend.app.db.base import Base

target_metadata = Base.metadata


def run_migrations():
    # A supplied connection supports isolated migration tests without service access.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    url = get_settings().database_url.get_secret_value()
    if not url:
        raise RuntimeError("DATABASE_URL must be configured for migrations")
    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool, echo=False, hide_parameters=True)
        try:
            with engine.connect() as connection:
                context.configure(
                    connection=connection, target_metadata=target_metadata, compare_type=True
                )
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()


run_migrations()
