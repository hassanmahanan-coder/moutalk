"""应用启动入口。

说明：uvicorn 0.36+ 在 Windows 硬编码 ProactorEventLoop。psycopg async
（PostgresSaver）在 Windows 的 Selector loop 下会**挂起**而非报错——因此
保持 uvicorn 默认（Proactor）并依赖 open_checkpointer 的超时快速降级
（见 PRD C.8：Windows 下断点续谈降级 JSON 持久化，Linux/生产正常）。

用法：python run.py   （等价 uvicorn app.main:app --port 8765 --host 0.0.0.0）
"""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8765, log_level="info")


if __name__ == "__main__":
    main()
