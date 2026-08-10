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
    """单例连接管理器（绑定 session_id，支持按 user_id 推送）。"""

    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}
        self._user_sessions: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    def register(self, session_id: str, ws: WebSocket, user_id: str | None = None) -> None:
        old = self.connections.get(session_id)
        if old is not None and old is not ws:
            try:
                self._user_sessions.setdefault(self._owner(session_id), set()).discard(session_id)
            except KeyError:
                pass
        self.connections[session_id] = ws
        if user_id is not None:
            self._user_sessions.setdefault(user_id, set()).add(session_id)

    def unregister(self, session_id: str) -> None:
        self.connections.pop(session_id, None)
        for sessions in self._user_sessions.values():
            sessions.discard(session_id)

    @staticmethod
    def _owner(session_id: str) -> str:
        # 推送通道会话（notif:{user_id}）可反解出所属用户
        if session_id.startswith("notif:"):
            return session_id[len("notif:") :]
        raise KeyError(session_id)

    async def send_to(self, session_id: str, message: dict[str, Any]) -> None:
        ws = self.connections.get(session_id)
        if ws is not None:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 发送失败视为断开
                self.unregister(session_id)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        """PRD 9.15 双写：向该用户全部在线连接推送（离线无连接则静默）。"""
        for sid in list(self._user_sessions.get(user_id, ())):
            await self.send_to(sid, message)

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
