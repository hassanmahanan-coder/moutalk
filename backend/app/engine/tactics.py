"""8 种战术定义 + 优先级规则引擎决策表（PRD 9.7）。

规则存为 Python 可执行配置（非 JSON，条件需要表达式）。
80% 由规则命中；全部不命中时可选 LLM 兜底；仍无则返回默认战术。
多步战术（红脸白脸）通过 tactic_context 跨轮续接。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 战术定义
# ---------------------------------------------------------------------------

GOOD_COP_BAD_COP = "good_cop_bad_cop"
TIME_PRESSURE = "time_pressure"
LAST_ULTIMATUM = "last_ultimatum"
FALSE_BOTTOM = "false_bottom"
DIVIDE_CONQUER = "divide_conquer"
SILENCE_PRESSURE = "silence_pressure"
CONCESSION_BAIT = "concession_bait"
INFO_ASYMMETRY = "info_asymmetry"
DEADLOCK_BREAK = "deadlock_break"
DEFAULT_TACTIC = "neutral"

TACTICS: dict[str, dict[str, Any]] = {
    GOOD_COP_BAD_COP: {
        "name": "红脸白脸",
        "description": "两轮对话中分别扮演强硬和温和角色，动摇对方判断",
        "multi_step": True,
        "max_steps": 2,
    },
    TIME_PRESSURE: {
        "name": "时间压迫",
        "description": "制造紧迫感迫使对方快速决策",
    },
    LAST_ULTIMATUM: {
        "name": "最后通牒",
        "description": "给出不可协商的最终条件",
    },
    FALSE_BOTTOM: {
        "name": "虚假底线",
        "description": "声称已达权限上限，压制对方预期",
    },
    DIVIDE_CONQUER: {
        "name": "分而治之",
        "description": "拆分议题逐个击破",
    },
    SILENCE_PRESSURE: {
        "name": "沉默施压",
        "description": "用简短回应/沉默迫使对方继续让步",
    },
    CONCESSION_BAIT: {
        "name": "让步诱饵",
        "description": "用小的让步换取大的利益",
    },
    INFO_ASYMMETRY: {
        "name": "信息不对称",
        "description": "利用对方不知道的信息获取优势（模拟设定内信息）",
    },
    DEADLOCK_BREAK: {
        "name": "打破僵局",
        "description": "僵局超过阈值时主动释放信号打破僵局",
    },
    DEFAULT_TACTIC: {
        "name": "中性回应",
        "description": "无规则命中时的兜底战术",
    },
}

# ---------------------------------------------------------------------------
# 战术话术骨架（prompt 提示 LLM 使用）与安全兜底模板
# ---------------------------------------------------------------------------

TACTIC_PROMPTS: dict[str, str] = {
    GOOD_COP_BAD_COP: "本轮扮演{sub_role}角色：{'bad_cop': '态度强硬、寸步不让', 'good_cop': '态度缓和、释放善意'}，与上一轮形成反差。",
    TIME_PRESSURE: "强调时间紧迫（如月底截止、名额有限、其他客户在等），敦促对方尽快决策。",
    LAST_ULTIMATUM: "给出最终条件并声明不可再让步，语气坚决但不失礼貌。",
    FALSE_BOTTOM: "声称已到权限上限/总部标准，无法继续让步。",
    DIVIDE_CONQUER: "把议题拆开逐个确认，先锁定容易达成的一致点。",
    SILENCE_PRESSURE: "回应尽量简短克制（一句话以内），不主动推进，等待对方先开口。",
    CONCESSION_BAIT: "主动做一个小幅让步，但要求对方在更大议题上让步作为交换。",
    INFO_ASYMMETRY: "利用场景设定内的信息（如行业行情、对手报价）争取有利条件，但明确是模拟设定信息。",
    DEADLOCK_BREAK: "主动抛出可落地的折中方案，打破僵局。",
    DEFAULT_TACTIC: "以正常语气推进谈判。",
}

SAFE_TEMPLATES: dict[str, list[str]] = {
    TIME_PRESSURE: [
        "我们这边月底前要确定合作方，希望您今天能给我一个明确答复。",
        "这个报价本周内有效，下周开始所有供应商都要提价了。",
    ],
    LAST_ULTIMATUM: [
        "这是我们的最终条件：180 万，包括全部服务，不能再变了。",
        "如果这个方案不行，我们只能遗憾地寻找其他合作方。",
    ],
    FALSE_BOTTOM: [
        "这已经是公司给我的最大权限了，再往下我真的做不了主。",
        "总部批的就是这个数，我没有更多空间。",
    ],
    DIVIDE_CONQUER: [
        "我们先确认付款周期，这个没问题的话，价格再单独谈。",
        "保修条款我们先定下来，其余的不急。",
    ],
    SILENCE_PRESSURE: [
        "嗯，我明白。",
        "您继续说。",
    ],
    CONCESSION_BAIT: [
        "付款周期我可以放宽到 60 天，但价格需要维持 190 万，您看如何？",
        "如果我方承担运费，贵方能否把订单量翻倍？",
    ],
    INFO_ASYMMETRY: [
        "据我所知，同行在这个价位都能提供更好的保修，希望贵方也考虑一下。",
        "行业里这个配置通常只有我们支持 7×24 服务。",
    ],
    DEADLOCK_BREAK: [
        "这样吧，价格维持 185 万，付款分三期，我们再往前走一步。",
        "各让一步：195 万，两年保修，今天就能签。",
    ],
    GOOD_COP_BAD_COP: [
        "（强硬）这个价格我们绝不让步，要么接受要么算了。",
        "（缓和）虽然刚才同事态度不好，但如果您今天能定，我可以帮您争取些优惠。",
    ],
    DEFAULT_TACTIC: [
        "好的，我们继续谈。",
        "我明白您的想法，我们聊聊具体方案。",
    ],
}

# ---------------------------------------------------------------------------
# 规则引擎（优先级匹配，参考 PRD 9.7 条件表）
# ---------------------------------------------------------------------------


@dataclass
class TacticContext:
    """战术选择节点所需的全部上下文。"""

    phase: str = "opening"
    round: int = 1
    scenario: dict[str, Any] = field(default_factory=dict)
    user_intent: dict[str, Any] = field(default_factory=dict)
    user_concede_count: int = 0
    user_firmness: str = "low"          # low / medium / high
    last_user_msg_length: int = 0
    rounds_since_last_progress: int = 0
    used_tactics: list[str] = field(default_factory=list)
    tactic_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class TacticDecision:
    name: str
    reason: str = ""
    sub_role: str | None = None
    step: int | None = None


def _rule(name: str, desc: str, fn: Callable[[TacticContext], bool]):
    return (name, desc, fn)


# (战术名, 触发说明, 条件)
RULES: list[tuple[str, str, Callable[[TacticContext], bool]]] = [
    _rule(DEADLOCK_BREAK, "僵局超过 3 轮无进展", lambda ctx: ctx.phase == "deadlock" and ctx.rounds_since_last_progress > 3),
    _rule(LAST_ULTIMATUM, "收尾阶段且用户让步≤1次", lambda ctx: ctx.phase == "closing" and ctx.user_concede_count <= 1),
    _rule(TIME_PRESSURE, "第 3 轮起且场景时间敏感", lambda ctx: ctx.round >= 3 and ctx.scenario.get("time_sensitive", False)),
    _rule(FALSE_BOTTOM, "核心阶段且用户攻击性强", lambda ctx: ctx.phase == "core" and ctx.user_intent.get("aggression_level") == "high"),
    _rule(
        DIVIDE_CONQUER,
        "多维场景且多数维度未达成",
        lambda ctx: ctx.scenario.get("multi_dimension", False)
        and ctx.scenario.get("dimension_agreement_count", 0) < max(ctx.scenario.get("dimension_total", 0) / 2, 1),
    ),
    _rule(
        GOOD_COP_BAD_COP,
        "核心阶段第 4-5 轮且近 5 轮未用",
        lambda ctx: ctx.phase == "core" and ctx.round in (4, 5) and GOOD_COP_BAD_COP not in ctx.used_tactics[-5:],
    ),
    _rule(SILENCE_PRESSURE, "用户急切且发言简短", lambda ctx: ctx.user_intent.get("emotion") == "eager" and ctx.last_user_msg_length < 20),
    _rule(CONCESSION_BAIT, "第 2 轮起且用户坚定度低", lambda ctx: ctx.round >= 2 and ctx.user_firmness == "low"),
    _rule(INFO_ASYMMETRY, "场景有内部信息且本次未用", lambda ctx: ctx.scenario.get("has_insider_info", False) and INFO_ASYMMETRY not in ctx.used_tactics),
]

MULTI_STEP_TACTICS = {GOOD_COP_BAD_COP}


def select_tactic(ctx: TacticContext) -> TacticDecision:
    """按优先级匹配规则，返回决策。全部不命中返回 DEFAULT_TACTIC。"""
    # 1) 多步战术续接：有未完成的多步战术则优先继续
    tc = ctx.tactic_context or {}
    active = tc.get("active_tactic")
    if active in MULTI_STEP_TACTICS:
        step = tc.get("step", 1) + 1
        if step <= TACTICS[active]["max_steps"]:
            return TacticDecision(
                name=active,
                reason=f"多步战术续接 step {step}",
                sub_role="good_cop" if step % 2 == 0 else "bad_cop",
                step=step,
            )
        # 已执行完的续接在此轮无效，继续走新战术匹配
    for name, desc, cond in RULES:
        if cond(ctx):
            sub_role = "bad_cop" if name in MULTI_STEP_TACTICS else None
            step = 1 if name in MULTI_STEP_TACTICS else None
            return TacticDecision(name=name, reason=desc, sub_role=sub_role, step=step)
    return TacticDecision(name=DEFAULT_TACTIC, reason="无规则命中，默认兜底")


def update_tactic_context(
    tactic_context: dict[str, Any], decision: TacticDecision
) -> dict[str, Any]:
    """回合结束后更新跨轮战术状态。"""
    ctx = dict(tactic_context or {})
    if decision.name in MULTI_STEP_TACTICS:
        step = decision.step or 1
        ctx.update(
            {
                "active_tactic": decision.name,
                "step": step,
                "sub_role": decision.sub_role,
                "started_round": ctx.get("started_round") or 1,
            }
        )
        if step >= TACTICS[decision.name]["max_steps"]:
            ctx["active_tactic"] = ""
            ctx["step"] = 0
    else:
        ctx["active_tactic"] = ""
        ctx["step"] = 0
    return ctx
