"""Alembic 迁移环境。

数据库 URL 从 app.core.config.get_settings().database_url 读取（凭据在 .env，
不写入 alembic.ini，符合 AGENTS.md「密钥只放 .env」约定）。测试可用环境变量
MOUTALK_TEST_DB_URL 覆盖（指向独立迁移库），避免污染 dev 库。
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import app.models  # noqa: F401  注册所有表
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get("MOUTALK_TEST_DB_URL") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()