"""跨进程事件总线（PRD 9.15/C.8 完善）：Celery worker → API 进程 WS 推送。

- worker 进程无 WebSocket 通道：报告完成/对账补登等事件经 Redis pub/sub
  发布，API 进程订阅后转 ws_manager.send_to_user 实时推送。
- publish_event：同步发布（worker/API 均可调用，失败静默不影响主流程）
- start_event_listener：异步长循环（API 进程 lifespan 启动）
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis as redis_lib
from redis.asyncio import from_url as async_from_url

from app.core.config import get_settings

logger = logging.getLogger(__name__)

EVENT_CHANNEL = "moutalk:events"


def publish_event(payload: dict[str, Any]) -> None:
    """发布事件（同步）；Redis 不可用时静默（事件兜底=落库通知）。"""
    try:
        client = redis_lib.from_url(get_settings().redis_url)
        try:
            client.publish(EVENT_CHANNEL, json.dumps(payload, ensure_ascii=False))
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 发布失败不影响业务
        logger.warning("事件发布失败（Redis 不可用?）: %s", exc)


def publish_notification(user_id: str, message: dict[str, Any]) -> None:
    """便捷入口：发布通知事件（在线用户由 API 进程 WS 推送，离线靠落库）。"""
    publish_event({"event": "notification", "user_id": str(user_id), "message": message})


async def _handle_message(message: dict[str, Any]) -> None:
    payload = json.loads(message["data"])
    if payload.get("event") != "notification":
        return
    from app.services.ws_manager import get_ws_manager

    await get_ws_manager().send_to_user(payload["user_id"], payload["message"])


async def start_event_listener() -> None:
    """订阅事件并转发（API 进程 lifespan 常驻；连接异常重试）。"""
    client = async_from_url(get_settings().redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(EVENT_CHANNEL)
    logger.info("事件监听已启动: %s", EVENT_CHANNEL)
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await _handle_message(msg)
            except Exception as exc:  # noqa: BLE001 单条消息失败不中断监听
                logger.warning("事件处理失败: %s", exc)
    finally:
        try:
            await pubsub.unsubscribe(EVENT_CHANNEL)
        finally:
            await client.close()
