import asyncio
import sys

import pytest
from sqlalchemy import create_engine, text

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import get_settings
from app.core.db import Base
from app.engine.llm import MockLLM
from app.models import Scenario, ScenarioDomain, User


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch):
    """测试统一走 MockLLM：不依赖本机 .env 是否配了 LLM_API_KEY，也不打真实网关。"""
    from app.engine import engine

    monkeypatch.setattr(engine, "build_llm", lambda: MockLLM())


@pytest.fixture(autouse=True)
def _disable_alipay_verify(monkeypatch):
    """测试禁用支付宝验签（降级放行）：回调测试不带真实签名，也不依赖 .env 公钥。"""
    from app.services import alipay_verify

    monkeypatch.setattr(alipay_verify, "_get_public_key", lambda: "")


@pytest.fixture(autouse=True)
def _disable_alipay_query(monkeypatch):
    """测试禁用支付宝真实查单 HTTP（.env 配了真实密钥，避免真发请求导致挂起）。

    对账默认 query_order（真实 query_trade）底层 httpx.post 被替换为抛异常，
    query_trade 自身降级返回 None；需要验证真实请求/响应的用例用显式
    patch("app.services.alipay_query.httpx.post") 覆盖它。
    """
    import httpx

    def _no_network(*args, **kwargs):
        raise httpx.ConnectError("test: network disabled")

    monkeypatch.setattr("app.services.alipay_query.httpx.post", _no_network)


@pytest.fixture(autouse=True)
def _disable_alipay_page_pay(monkeypatch):
    """测试禁用支付宝 page.pay 真实跳转链接生成（不依赖 .env 密钥完整性）。

    API 层用例只关心订单创建契约，pay_url 返回固定沙箱链接；真实签名
    与 URL 构造由 test_alipay_page_pay 用显式密钥覆盖。
    """
    monkeypatch.setattr(
        "app.api.payment.build_pay_url",
        lambda *args, **kwargs: "https://openapi.alipaydev.com/gateway.do?mock=1",
    )


@pytest.fixture(autouse=True)
def _disable_rag_in_ws(monkeypatch):
    """WS 端到端测试禁用 RAG（避免真连 Milvus 文件污染 repo）；RAG 存取由
    test_rag（tmp 路径）与注入由 test_rag_injection（FakeRAG）单独覆盖。"""
    from app.api import negotiation

    monkeypatch.setattr(negotiation, "_build_rag", lambda: None)


@pytest.fixture(autouse=True)
def _disable_smtp(monkeypatch):
    """测试禁用真实 SMTP（.env 可能配了 QQ 邮箱，避免测试真发邮件）；SMTP_SSL
    替换为 no-op，email_sender 直接测试用显式 patch 覆盖它。"""
    import smtplib

    class NoopSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", NoopSMTP)


@pytest.fixture(autouse=True)
def _force_checkpointer_test_db(monkeypatch, test_engine):
    """PostgresSaver 落测试库 moutalk_test，避免污染 dev 库 moutalk。"""
    from app.engine import checkpointer

    uri = test_engine.url.render_as_string(hide_password=False)
    if uri.startswith("postgresql+psycopg://"):
        uri = "postgresql://" + uri[len("postgresql+psycopg://") :]
    monkeypatch.setattr(checkpointer, "get_checkpointer_uri", lambda: uri)


def _create_test_db() -> str:
    settings = get_settings()
    admin_engine = create_engine(
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'moutalk_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE moutalk_test"))
    admin_engine.dispose()
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/moutalk_test"
    )


@pytest.fixture(scope="session")
def test_engine():
    url = _create_test_db()
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session(test_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=test_engine, autoflush=False)
    with Session() as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        s.commit()
        yield s


@pytest.fixture
def user(session):
    u = User(email="alice@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def scenario(session):
    s = Scenario(
        id="it_procurement",
        domain=ScenarioDomain.IT_PROCUREMENT,
        title="IT 采购谈判",
        config_json={"opening": {"price": 100}},
        is_free=True,
    )
    session.add(s)
    session.commit()
    return s
