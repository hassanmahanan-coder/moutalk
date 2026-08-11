"""应用入口测试：Windows 事件循环策略（PostgresSaver 兼容，PRD 9.1/C.8）。

psycopg 异步驱动与 ProactorEventLoop 不兼容；main.py 须在 loop 创建前
设置 SelectorEventLoopPolicy，否则断点续谈降级 JSON 持久化。
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_win32_uses_selector_event_loop_policy():
    """Windows 上应用导入后事件循环策略必须为 Selector（否则 PostgresSaver 降级）。"""
    import app.main  # noqa: F401 触发模块级 policy 设置

    if sys.platform == "win32":
        policy = asyncio.get_event_loop_policy()
        assert isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy), (
            "Windows 必须使用 SelectorEventLoopPolicy（psycopg 异步兼容）"
        )


def test_run_py_uses_standard_uvicorn():
    """run.py 使用标准 uvicorn（Windows Proactor + checkpointer 超时降级是既定约束）。"""
    text = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "uvicorn.run" in text
    cp = (ROOT / "app" / "engine" / "checkpointer.py").read_text(encoding="utf-8")
    assert "asyncio.timeout" in cp, "checkpointer 必须有超时兜底（防 Selector 挂起）"
    assert "CHECKPOINTER_TIMEOUT" in cp


ROOT = Path(__file__).resolve().parents[1]
