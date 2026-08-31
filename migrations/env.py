from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()


def sqlalchemy_url() -> str:
    dsn = settings.postgres_dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgres://")
    return dsn


config.set_main_option("sqlalchemy.url", sqlalchemy_url().replace("%", "%%"))


def run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
