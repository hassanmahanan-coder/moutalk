"""应用启动入口（PRD 9.1/C.8）：Windows 下使用 Selector 事件循环启 uvicorn。

uvicorn 0.36+ 在 Windows 硬编码 ProactorEventLoop（psycopg 异步不兼容，
PostgresSaver 会降级 JSON 持久化）。此处绕过 uvicorn.run 的 asyncio.run，
手动创建 Selector 事件循环（policy 已在 main 前设置）并驱动 Server.serve。

用法：python run.py   （等价 uvicorn app.main:app --port 8765 --host 0.0.0.0）
"""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from uvicorn.config import Config
    from uvicorn.server import Server

    cfg = Config("app.main:app", host="0.0.0.0", port=8765, log_level="info")
    server = Server(cfg)

    loop = asyncio.new_event_loop()  # policy 已为 Selector → SelectorEventLoop
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.serve())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
