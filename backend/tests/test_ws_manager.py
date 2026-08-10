"""WebSocket 连接管理测试（PRD 9.8）：单例 + 会话绑定 + 优雅关闭广播。

- register/unregister：按 session_id 维护连接
- broadcast：向所有连接推送（关闭时 server_shutdown）
"""

import pytest

from app.services.ws_manager import WsConnectionManager


class FakeWS:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True


@pytest.fixture
def manager():
    m = WsConnectionManager()
    yield m
    m.connections.clear()


async def test_register_and_broadcast(manager):
    ws1 = FakeWS()
    ws2 = FakeWS()
    manager.register("s1", ws1)
    manager.register("s2", ws2)
    await manager.broadcast({"type": "server_shutdown"})
    assert ws1.sent == [{"type": "server_shutdown"}]
    assert ws2.sent == [{"type": "server_shutdown"}]


async def test_unregister_stops_broadcast(manager):
    ws = FakeWS()
    manager.register("s1", ws)
    manager.unregister("s1")
    await manager.broadcast({"type": "server_shutdown"})
    assert ws.sent == []


async def test_broadcast_skips_dead_connections(manager):
    ws = FakeWS()

    async def _fail_send(data):
        raise ConnectionError("gone")

    ws.send_json = _fail_send
    manager.register("s1", ws)
    await manager.broadcast({"type": "server_shutdown"})  # 不抛异常
    assert "s1" not in manager.connections, "死连接应被移除"


async def test_re_register_same_session(manager):
    old, new = FakeWS(), FakeWS()
    manager.register("s1", old)
    manager.register("s1", new)
    await manager.broadcast({"type": "x"})
    assert old.sent == [], "旧连接不再接收"
    assert new.sent == [{"type": "x"}]
