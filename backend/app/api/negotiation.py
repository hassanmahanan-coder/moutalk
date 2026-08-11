"""WebSocket 谈判端点：实时对话 + 流式输出 + 会话持久化 + 断线缓冲回放。

协议（PRD 8.2 / 9.1）：
- 客户端 → 服务端：{type:'user_msg', text} / {type:'end_negotiation'} / {type:'ping'} /
                    {type:'ack'}（确认收到 meta，清空断线缓冲）/
                    {type:'resume'}（重连后请求回放缓冲轮次）
- 服务端 → 客户端：{type:'opening', text} / {type:'history', messages, offers, round} /
                    {type:'token', text} / {type:'meta', tactic, bottom_line} /
                    {type:'replay', messages:[{user_text, reply, meta}, ...]} /
                    {type:'simple_result', ...} / {type:'pong'} / {type:'error', code, message}

断线缓冲（9.1）：每轮完成先写 Redis 缓冲再发送；客户端收到 meta 回 ack 清空；
连接断开时缓冲保留，重连 resume 后回放，断线不丢轮次。
心跳：服务端 60s 内无任何消息判定断线主动关闭（HEARTBEAT_TIMEOUT）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.engine.checkpointer import open_checkpointer
from app.engine.engine import NegotiationEngine
from app.engine.llm import MockLLM, set_rate_limit_user
from app.models import NegotiationSession, Scenario, SessionStatus
from app.services.negotiation_lock import NegotiationLock
from app.services.rag import build_rag_memory
from app.services.report_service import generate_report
from app.services.scenario_loader import load_scenario_for_session
from app.services.security import TokenType, decode_token
from app.services.session_store import end_session, get_session_state, save_round
from app.services.ws_buffer import WsBuffer
from app.services.ws_manager import get_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/negotiation", tags=["negotiation"])

CHUNK_SIZE = 12          # 伪流式：每片字符数（PRD 9.2 推荐 MVP 伪流式）
CHUNK_INTERVAL = 0.05    # 伪流式：片间隔秒
HEARTBEAT_TIMEOUT = 60   # 秒：60s 无心跳判定断线（PRD 8.2）


async def _reject(ws: WebSocket, code: str, message: str, close: bool = True) -> None:
    await ws.send_json({"type": "error", "code": code, "message": message})
    if close:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)


async def _stream_text(ws: WebSocket, text: str) -> None:
    """伪流式分片发送（真流式在 Phase 2 升级）。"""
    for i in range(0, len(text), CHUNK_SIZE):
        await ws.send_json({"type": "token", "text": text[i : i + CHUNK_SIZE]})
        await asyncio.sleep(CHUNK_INTERVAL)


def _meta_from_state(state: dict) -> dict:
    intent = state.get("intent") or {}
    meta = {
        "type": "meta",
        "tactic": state.get("selected_tactic", ""),
        "tactic_reason": state.get("tactic_reason", ""),
        "bottom_line": state.get("bottom_line_status", "ok"),
        "round": state.get("round", 1),
        "intent": intent.get("intent_type", "other"),
    }
    # PRD 8.2 协议字段：实时分数（基于已出报价的即时评分，失败降级 None 不阻断）
    try:
        from app.services.report_service import compute_simple_result

        result = compute_simple_result(
            state.get("scenario") or {}, state.get("offers_json") or []
        )
        meta["score"] = round(float(result.get("score", 0.0)), 3)
    except Exception as exc:  # noqa: BLE001 分数计算失败不影响 meta 推送
        logger.warning("实时分数计算失败: %s", exc)
        meta["score"] = None
    return meta


def _simple_result(state: dict) -> dict:
    offers = state.get("offers_json") or []
    return {
        "type": "simple_result",
        "rounds": state.get("round", 1),
        "offers_count": len(offers),
        "last_offer": state.get("last_offer"),
        "bottom_line_status": state.get("bottom_line_status", ""),
        "summary": "谈判已结束，详细复盘报告生成中",
    }


@router.websocket("/{session_id}")
async def negotiate(ws: WebSocket, session_id: str, db: Session = Depends(get_db)) -> None:
    await ws.accept()
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        await _reject(ws, "INVALID_SESSION", "会话 ID 格式非法")
        return

    token = ws.query_params.get("token", "")
    if not token:
        await _reject(ws, "UNAUTHORIZED", "缺少访问令牌")
        return
    try:
        payload = decode_token(token, TokenType.ACCESS)
    except JWTError:
        await _reject(ws, "INVALID_TOKEN", "访问令牌无效或已过期")
        return

    ns = db.get(NegotiationSession, session_uuid)
    if ns is None:
        await _reject(ws, "SESSION_NOT_FOUND", "会话不存在")
        return
    if str(ns.user_id) != payload["sub"]:
        await _reject(ws, "FORBIDDEN", "无权访问该会话")
        return
    if ns.status == SessionStatus.ENDED:
        await _reject(ws, "SESSION_ENDED", "会话已结束")
        return

    try:
        async with open_checkpointer() as checkpointer:
            rag = _build_rag()
            buffer = WsBuffer()
            nlock = NegotiationLock()
            manager = get_ws_manager()
            manager.register(str(ns.id), ws)
            try:
                await _negotiate_loop(ws, db, ns, checkpointer, rag, buffer, nlock)
            finally:
                manager.unregister(str(ns.id))
                if rag is not None:
                    rag.close()
    except WebSocketDisconnect:
        logger.info("WebSocket 断开: %s", session_id)
    except Exception as exc:  # noqa: BLE001 仅 PostgresSaver 类异常才降级 JSON 持久化
        exc_text = str(exc).lower()
        if "postgressaver" not in exc_text and "psycopg" not in exc_text:
            # 非 checkpointer 异常（如 WS 已关闭后的发送竞态）：记录后正常结束，不重跑
            logger.warning("谈判连接异常结束: %s", exc)
            return
        logger.warning("PostgresSaver 不可用，降级 JSON 持久化: %s", exc)
        rag = _build_rag()
        buffer = WsBuffer()
        nlock = NegotiationLock()
        try:
            await _negotiate_loop(ws, db, ns, None, rag, buffer, nlock)
        except WebSocketDisconnect:
            logger.info("WebSocket 断开: %s", session_id)
        finally:
            if rag is not None:
                rag.close()


def _build_rag():
    """构建 RAG 记忆（Milvus Lite）。不可用时返回 None，RAG 静默关闭。"""
    try:
        return build_rag_memory()
    except Exception as exc:  # noqa: BLE001 观测组件故障不阻断谈判
        logger.warning("RAG 记忆不可用，跳过历史参考: %s", exc)
        return None


async def _negotiate_loop(
    ws: WebSocket,
    db: Session,
    ns: NegotiationSession,
    checkpointer: Any | None,
    rag=None,
    buffer: WsBuffer | None = None,
    nlock: NegotiationLock | None = None,
) -> None:
    scenario_row = db.scalar(select(Scenario).where(Scenario.id == ns.scenario_id))
    if scenario_row is None:
        await _reject(ws, "SCENARIO_NOT_FOUND", "场景包不存在")
        return

    engine = NegotiationEngine(
        load_scenario_for_session(db, ns.scenario_id),
        checkpointer=checkpointer,
        rag=rag,
        # PRD 9.4 真流式：utterance 节点边生成边转发（重试轮自动退回伪流式）
        stream_callback=lambda piece: ws.send_json({"type": "token", "text": piece}),
    )
    llm_mode = "mock" if isinstance(engine.llm, MockLLM) else "glm"

    if ns.messages_json:
        if checkpointer is not None:
            restored = await engine.restore_state(str(ns.id))
            if restored is not None:
                restored["scenario"] = engine.scenario
                state = restored
            else:
                state = get_session_state(db, ns.id)
                state["scenario"] = engine.scenario
        else:
            state = get_session_state(db, ns.id)
            state["scenario"] = engine.scenario
    else:
        state = engine.initial_state(str(ns.id))

    if state.get("history"):
        await ws.send_json(
            {
                "type": "history",
                "messages": list(state.get("history") or []),
                "offers": list(state.get("offers_json") or []),
                "round": state.get("round", 1),
                "llm_mode": llm_mode,
            }
        )
    else:
        await ws.send_json({"type": "opening", "text": engine.opening_line(), "llm_mode": llm_mode})

    while True:
        try:
            async with asyncio.timeout(HEARTBEAT_TIMEOUT):
                raw = await ws.receive_text()
        except TimeoutError:
            logger.info("心跳超时 %ss 判定断线: %s", HEARTBEAT_TIMEOUT, ns.id)
            await ws.close(code=status.WS_1001_GOING_AWAY)
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await _reject(ws, "BAD_MESSAGE", "消息必须为 JSON", close=False)
            continue

        msg_type = msg.get("type", "")
        if msg_type == "ping":
            await ws.send_json({"type": "pong"})
            continue
        if msg_type == "ack":
            buffer.drain(str(ns.id))
            continue
        if msg_type == "resume":
            buffered = buffer.drain(str(ns.id))
            await ws.send_json({"type": "replay", "messages": buffered})
            continue
        if msg_type == "coach":
            # 谈判教练：基于当前状态生成建议（不写入历史，不影响对手）
            from app.services.coach_service import get_coach_advice

            advice = await get_coach_advice(engine.llm, state)
            await ws.send_json({"type": "coach_advice", **advice})
            continue
        if msg_type == "user_msg":
            text = str(msg.get("text", "")).strip()
            if not text:
                await _reject(ws, "EMPTY_MESSAGE", "消息不能为空", close=False)
                continue
            # PRD 9.13：Redis 分布式锁防同一 session 并发 invoke（上一条未完成则 429）
            if not nlock.acquire(str(ns.id)):
                await _reject(ws, "PROCESSING_PREVIOUS_MESSAGE", "上一条消息处理中，请稍候", close=False)
                continue
            # PRD 9.6：设置用户 ID 供 LLM 令牌桶限流
            set_rate_limit_user(str(ns.user_id))
            try:
                state = await engine.run_round(state, text, thread_id=str(ns.id))
            finally:
                set_rate_limit_user(None)
                nlock.release(str(ns.id))
            reply = state.get("reply") or ""
            if rag is not None:
                try:
                    rag.add_round(str(ns.id), "user", text)
                    rag.add_round(str(ns.id), "assistant", reply)
                except Exception as exc:  # noqa: BLE001 记忆写入失败不阻断
                    logger.warning("RAG 记忆写入失败: %s", exc)
            meta = _meta_from_state(state)
            buffer.push(
                str(ns.id),
                {"user_text": text, "reply": reply, "meta": meta},
            )
            await _stream_text(ws, reply)
            await ws.send_json(meta)
            save_round(db, ns.id, state)
            db.commit()
            continue
        if msg_type == "end_negotiation":
            result = _simple_result(state)
            end_session(db, ns.id, simple_result=result)
            db.commit()
            await ws.send_json(result)
            try:
                await _submit_report_generation(db, ns.id, ws)
            except Exception as exc:  # noqa: BLE001 报告生成失败不阻断收尾
                logger.warning("复盘报告生成失败: %s", exc)
            await ws.close()
            return
        await _reject(ws, "UNKNOWN_TYPE", f"未知消息类型: {msg_type}", close=False)


async def _submit_report_generation(db: Session, session_id: uuid.UUID, ws: WebSocket) -> None:
    """提交异步报告生成（PRD 8.4）。

    dev 环境（本机无 Celery worker）直接同步生成；其他环境走 Celery 异步，
    broker 不可用时降级同步。同步生成后推送 report_ready。
    """
    settings = get_settings()
    if settings.app_env != "dev":
        try:
            from app.celery_app import generate_full_report

            generate_full_report.delay(str(session_id))
            await ws.send_json({"type": "report_submitted", "message": "复盘报告异步生成中"})
            return
        except Exception as exc:  # noqa: BLE001 broker 不可用（本机 Redis 未启/测试环境）降级同步
            logger.warning("Celery 提交失败，降级同步生成: %s", exc)
    report = await generate_report(db, session_id)
    # PRD 9.15 双写：先落库通知（再发 WS——客户端可能已断开，发送失败不阻断落库）
    try:
        from app.models import NegotiationSession as _NS
        from app.services.notification_service import create_notification

        ns_row = db.get(_NS, session_id)
        if ns_row is not None:
            create_notification(
                db,
                ns_row.user_id,
                "report",
                "复盘报告已生成",
                {"report_id": str(report.id), "session_id": str(session_id)},
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 通知失败不阻断
        logger.warning("报告通知落库失败: %s", exc)
    try:
        await ws.send_json({"type": "report_ready", "rid": str(report.id)})
    except Exception as exc:  # noqa: BLE001 WS 已断开时忽略
        logger.debug("report_ready 发送失败（客户端已断开）: %s", exc)
    # 用户级推送：其他页面/重连后的全局通知通道也能收到
    try:
        from app.services.ws_manager import get_ws_manager

        await get_ws_manager().send_to_user(
            str(ns_row.user_id),
            {
                "type": "notification",
                "notification": {
                    "type": "report",
                    "title": "复盘报告已生成",
                    "report_id": str(report.id),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 推送失败不阻断
        logger.warning("报告完成 WS 推送失败: %s", exc)
