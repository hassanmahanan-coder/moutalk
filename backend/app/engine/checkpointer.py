"""LangGraph PostgresSaver 状态持久化封装（PRD 9.1 / 9.13）。

用法（WS 每轮）：
    async with open_checkpointer() as cp:
        graph = build_graph(llm, checkpointer=cp)
        await graph.ainvoke(inputs, config={"configurable": {"thread_id": session_id}})
        # 退出上下文时连接自动关闭，checkpoint 已落库

断线重连：用同一 thread_id 的 aget_state(config) 取回完整状态。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHECKPOINTER_TIMEOUT = 8  # 秒：连接/建表超时即降级（Windows psycopg async 兼容兜底）


def get_checkpointer_uri() -> str:
    """PostgresSaver 连接串：与业务库相同（psycopg 原生格式，去 SQLAlchemy 方言前缀）。"""
    settings = get_settings()
    uri = settings.database_url
    if uri.startswith("postgresql+psycopg://"):
        uri = "postgresql://" + uri[len("postgresql+psycopg://") :]
    return uri


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """打开 PostgresSaver（首次自动建表 setup），退出自动关闭连接。

    Windows 兼容：psycopg async 在 Windows 可能挂起（Selector loop）或
    不支持（Proactor），用超时兜底——快速失败降级，避免谈判卡死。
    """
    uri = get_checkpointer_uri()
    try:
        async with asyncio.timeout(CHECKPOINTER_TIMEOUT):
            async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
                await checkpointer.setup()
                yield checkpointer
    except Exception as exc:
        logger.warning("PostgresSaver 不可用（%s），降级无 checkpointer 运行", exc)
        raise
