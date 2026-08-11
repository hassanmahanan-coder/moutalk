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


def test_run_py_uses_selector_loop():
    """run.py 必须：先设 Selector policy，再手动建 loop 驱动 Server（绕过 uvicorn 的 Proactor 硬编码）。"""
    text = (ROOT / "run.py").read_text(encoding="utf-8")
    policy_pos = text.index("set_event_loop_policy")
    new_loop_pos = text.index("asyncio.new_event_loop")
    assert policy_pos < new_loop_pos, "policy 必须早于 loop 创建"
    assert "Server" in text and "server.serve" in text, "必须手动驱动 Server.serve（绕过 asyncio.run）"
    assert "uvicorn.run(" not in text, "不得使用 uvicorn.run（Windows 硬编码 Proactor）"


ROOT = Path(__file__).resolve().parents[1]
