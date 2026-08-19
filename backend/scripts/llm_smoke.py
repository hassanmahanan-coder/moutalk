"""真实 LLM 网关 smoke 测试（CI 专用，本地亦可跑）。

用法：LLM_API_KEY=xxx python scripts/llm_smoke.py
- 验证 OpenAIClient 初始化、ainvoke、astream 三条主链路
- 失败以非零码退出（CI 门禁）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend 根入 path

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.llm_api_key:
        print("SKIP: LLM_API_KEY 未配置")
        sys.exit(0)

    from app.engine.llm import OpenAIClient

    llm = OpenAIClient(settings)
    print(f"model: {settings.llm_model} / light: {settings.llm_light_model}")

    reply = await llm.ainvoke("请只回复两个字：正常")
    assert reply and reply.strip(), "ainvoke 返回空"
    print(f"ainvoke ok: {reply.strip()[:20]}")

    light = await llm.ainvoke("请只回复两个字：正常", light=True)
    assert light and light.strip(), "light ainvoke 返回空"
    print(f"light ainvoke ok: {light.strip()[:20]}")

    parts = []
    async for chunk in llm.astream("请只回复两个字：流式"):
        parts.append(chunk)
    assert "".join(parts).strip(), "astream 返回空"
    print(f"astream ok: {len(parts)} 片")

    print("LLM SMOKE PASS")


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=90))
    except TimeoutError:
        print("LLM SMOKE TIMEOUT (gateway slow)")
        raise SystemExit(1)
