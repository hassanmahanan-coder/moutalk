"""Agent 链路 smoke 测试（CI 专用，本地亦可跑）。

用真实 LLM 验证：create_agent 构建 + run_round 一轮真实对话（含工具调用）。
失败以非零码退出（CI 门禁）。无 key 时跳过（等价工作流可离线全测）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.engine.engine import NegotiationEngine
from app.scenarios import load_scenario


async def main() -> None:
    settings = get_settings()
    if not settings.llm_api_key:
        print("SKIP: LLM_API_KEY 未配置")
        sys.exit(0)
    from app.engine.llm import build_llm

    llm = build_llm()
    engine = NegotiationEngine(load_scenario("it_procurement"), llm=llm)
    if not engine.agent_mode:
        print("FAIL: 配置真实 key 后应处于 Agent 模式")
        raise SystemExit(1)
    print(f"agent_mode={engine.agent_mode} model={settings.llm_model}")

    state = engine.initial_state("agent-smoke")
    out = await engine.run_round(state, "235 万太贵了，能降到 200 万吗？")
    reply = (out.get("reply") or "").strip()
    assert reply, "Agent 未产出回复"
    assert reply != "235 万太贵了，能降到 200 万吗？", "回显 bug"
    print(f"reply({len(reply)}字): {reply[:80]}...")
    print("AGENT SMOKE PASS")


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=120))
    except TimeoutError:
        print("AGENT SMOKE TIMEOUT")
        raise SystemExit(1)
