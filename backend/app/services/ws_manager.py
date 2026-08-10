"""WebSocket 连接管理（PRD 9.8）：单例 + 会话绑定 + 优雅关闭广播。

- 全局维护 `connections: dict[session_id, WebSocket]`
- 同一 session 重连时替换旧连接（旧连接不再接收）
- broadcast：关闭时推送 {type:'server_shutdown'}，发送失败/断开的连接自动移除
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WsConnectionManager:
    """单例连接管理器（绑定 session_id）。"""

    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    def register(self, session_id: str, ws: WebSocket) -> None:
        self.connections[session_id] = ws

    def unregister(self, session_id: str) -> None:
        self.connections.pop(session_id, None)

    async def send_to(self, session_id: str, message: dict[str, Any]) -> None:
        ws = self.connections.get(session_id)
        if ws is not None:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 发送失败视为断开
                self.unregister(session_id)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """向所有连接推送；发送失败/断开的连接自动移除。"""
        for sid, ws in list(self.connections.items()):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 死连接清理
                self.unregister(sid)


_ws_manager: WsConnectionManager | None = None


def get_ws_manager() -> WsConnectionManager:
    """单例访问。"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WsConnectionManager()
    return _ws_manager
