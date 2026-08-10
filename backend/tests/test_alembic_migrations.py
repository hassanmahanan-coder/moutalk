"""Alembic 迁移测试：upgrade/downgrade 往返、模型无漂移（alembic check）。

使用独立临时库 moutalk_migtest（env MOUTALK_TEST_DB_URL），不污染 dev/moutalk_test。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _admin_url() -> str:
    from app.core.config import get_settings

    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/postgres"
    )


def _mig_url() -> str:
    from app.core.config import get_settings

    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/moutalk_migtest"
    )


@pytest.fixture(scope="module")
def mig_db_url():
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS moutalk_migtest WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE moutalk_migtest"))
    admin.dispose()
    yield _mig_url()


def run_alembic(*args: str, env_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["MOUTALK_TEST_DB_URL"] = env_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        tables = set(rows)
    engine.dispose()
    return tables


def _alembic_version(url: str) -> str | None:
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
        value = list(rows)
    engine.dispose()
    return value[0] if value else None


EXPECTED_TABLES = {
    "users",
    "scenarios",
    "sessions",
    "orders",
    "payment_log",
    "reports",
    "user_scenario_access",
    "notifications",
    "admin_audit_log",
}


class TestMigrateUpgrade:
    def test_upgrade_head_creates_all_tables(self, mig_db_url):
        result = run_alembic("upgrade", "head", env_url=mig_db_url)
        assert result.returncode == 0, result.stderr
        tables = _table_names(mig_db_url)
        assert EXPECTED_TABLES <= tables
        assert _alembic_version(mig_db_url) == "b9239a8602ae"

    def test_alembic_check_no_drift(self, mig_db_url):
        """守卫：模型 metadata 与迁移脚本一致，模型改动必须生成新迁移。"""
        result = run_alembic("check", env_url=mig_db_url)
        assert result.returncode == 0, result.stdout + result.stderr


class TestMigrateDowngrade:
    def test_downgrade_base_drops_tables(self, mig_db_url):
        run_alembic("upgrade", "head", env_url=mig_db_url)
        result = run_alembic("downgrade", "base", env_url=mig_db_url)
        assert result.returncode == 0, result.stderr
        leftovers = _table_names(mig_db_url)
        assert not EXPECTED_TABLES & leftovers

    def test_reupgrade_after_downgrade(self, mig_db_url):
        """down -> up 往返（含 PG enum 清理）；枚举不残留否则 CREATE TYPE 冲突。"""
        run_alembic("upgrade", "head", env_url=mig_db_url)
        run_alembic("downgrade", "base", env_url=mig_db_url)
        result = run_alembic("upgrade", "head", env_url=mig_db_url)
        assert result.returncode == 0, result.stderr
        assert EXPECTED_TABLES <= _table_names(mig_db_url)

    def test_downgrade_removes_enum_types(self, mig_db_url):
        run_alembic("upgrade", "head", env_url=mig_db_url)
        run_alembic("downgrade", "base", env_url=mig_db_url)
        engine = create_engine(mig_db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT typname FROM pg_type JOIN pg_namespace "
                    "ON pg_type.typnamespace = pg_namespace.oid "
                    "WHERE nspname = 'public' AND typcategory = 'E'"
                )
            ).scalars()
            enums = set(rows)
        engine.dispose()
        assert not enums