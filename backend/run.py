"""应用启动入口。

Windows 说明：uvicorn.run 在 Windows 硬编码 Proactor；psycopg async（PostgresSaver）
在 Proactor 下报错、在 Selector 下挂起且无法被超时取消（troubleshooting #52/#60），
两种事件循环均不可靠——Windows 开发机保持 Proactor + open_checkpointer 超时降级
JSON 持久化（sessions.messages_json/offers_json 双写，断线续谈功能完整）；
Linux/生产环境 PostgresSaver 正常启用。

热重载权衡：MOUTALK_RELOAD=1 走 uvicorn.run(reload=True)（Windows reload 的 spawn
清理不可靠且回退 Proactor 降级，见 #58）；默认关闭，改后端代码手动重启。
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    reload = os.getenv("MOUTALK_RELOAD", "0") == "1"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8765,
        log_level="info",
        reload=reload,
    )


if __name__ == "__main__":
    main()
