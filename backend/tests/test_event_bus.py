"""事件总线测试（PRD 9.15/C.8）：Redis pub/sub 发布与监听转发。"""

import json

import pytest

from app.services.event_bus import _handle_message, publish_notification


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_handle_message_forwards_to_user_ws():
    from app.services.ws_manager import WsConnectionManager

    manager = WsConnectionManager()
    ws = FakeWS()
    manager.register("s1", ws, user_id="u-1")
    # 注入单例（get_ws_manager 返回模块单例）
    import app.services.ws_manager as wm

    original = wm._ws_manager
    wm._ws_manager = manager
    try:
        await _handle_message(
            {
                "data": json.dumps(
                    {
                        "event": "notification",
                        "user_id": "u-1",
                        "message": {"type": "notification", "notification": {"type": "report"}},
                    }
                )
            }
        )
        assert ws.sent == [
            {"type": "notification", "notification": {"type": "report"}}
        ], "事件应转发给对应在线用户"
    finally:
        wm._ws_manager = original


@pytest.mark.asyncio
async def test_handle_message_ignores_other_events():
    await _handle_message({"data": json.dumps({"event": "other", "x": 1})})  # 不抛异常


def test_publish_notification_roundtrip():
    """发布-订阅闭环（真实 Redis）：监听收到发布的消息。"""
    import redis as redis_lib

    from app.core.config import get_settings
    from app.services.event_bus import EVENT_CHANNEL

    client = redis_lib.from_url(get_settings().redis_url)
    pubsub = client.pubsub()
    pubsub.subscribe(EVENT_CHANNEL)
    try:
        publish_notification("u-9", {"type": "notification", "text": "hello"})
        import time

        end = time.time() + 5
        got = None
        while time.time() < end:
            msg = pubsub.get_message(ignore_subscribe_messages=True)
            if msg and msg.get("type") == "message":
                got = json.loads(msg["data"])
                break
            time.sleep(0.1)
        assert got is not None, "应收到发布的事件"
        assert got["event"] == "notification"
        assert got["user_id"] == "u-9"
    finally:
        pubsub.close()
        client.close()
