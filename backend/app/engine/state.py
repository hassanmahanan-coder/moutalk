"""LangGraph 谈判引擎状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class NegotiationState(TypedDict, total=False):
    """一次谈判会话的 LangGraph 状态。所有字段均为可选，便于增量写入。"""

    session_id: str
    scenario_id: str
    scenario: dict[str, Any]  # 场景包配置

    round: int                 # 当前轮次，从 1 开始
    phase: str                 # opening / core / deadlock / closing

    user_message: str
    history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": ...}]

    intent: dict[str, Any]     # 意图解析结果
    selected_tactic: str
    tactic_reason: str
    tactic_sub_role: str | None
    tactic_context: dict[str, Any]  # 跨轮战术状态（红脸白脸等）
    used_tactics: list[str]    # 本会话已用战术（规则引擎参考）

    opponent_offer: dict[str, Any] | None   # 本轮的对手报价（结构化）
    last_offer: dict[str, Any] | None       # 最近一次结构化报价
    offers_json: list[dict[str, Any]]       # 每轮报价记录

    retry_count: int           # 底线检查重试计数
    retry_reason: str | None   # 上次被驳回的原因
    reply: str | None          # 生成的对手话术
    reply_blocked: bool
    bottom_line_status: str    # ok / blocked / fallback

    meta: dict[str, Any]       # 看板数据：分数、战术提示等
