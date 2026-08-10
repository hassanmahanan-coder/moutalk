"""谈判教练（新功能，PRD 未来考虑项）：用户不知如何回复时生成下一步建议。

- 输入：当前谈判状态（轮次/阶段/历史/出价/已用战术）
- 输出：局势分析 + 建议策略 + 2-3 条可直接发送的话术选项
- 建议不写入谈判历史（仅辅助用户，不影响对手行为）
- GLM 生成失败/未配置 key 时降级规则建议（MockLLM 同构）
- 调用计入 LLM 令牌桶限流（PRD 9.6）
"""

from __future__ import annotations

import logging
from typing import Any

from app.engine.llm import _check_rate_limit
from app.engine.tactics import TACTIC_PROMPTS

logger = logging.getLogger(__name__)

COACH_JSON_PROMPT = """你是资深谈判教练。基于当前谈判局势，给用户下一步行动建议，目标是**促成对手让步、改善谈判结果**。

谈判背景：
- 当前轮次：第 {round} 轮（阶段：{phase}）
- 对话历史：
{history}
- 已用战术：{used_tactics}
- 当前出价记录：{offers}

谈判要点（教练视角）：
1. 识别对手当前出价是否已僵持多轮：若连续多轮无让步，应改变施压方向（换维度/点破对方话术/引入竞争），不要继续配合对方节奏
2. 对手若用时间压迫（"最后期限""系统锁单"），建议话术应**点破或拖延**（"我需要内部审批，急不得""还有其他方案在比价"），夺回主动权，而非配合"马上走流程"
3. 避免话术过早暴露自己的底线（如"X 已是底线"），应留谈判空间
4. 报价类话术应给出具体数字，便于对方评估让步空间

要求：
1. 分析当前局势（用户处境、对手态势、关键机会/风险），1-2 句话
2. 给出下一步策略建议（可参考战术：{tactics_hint}），1 句话
3. 生成 3 条用户可直接发送给对手的话术（面向对手，符合用户利益，不突破合理谈判范围，能有效促成对手让步或打破僵局）

严格输出 JSON：
{{"analysis": "局势分析", "strategy": "策略建议", "options": ["话术1", "话术2", "话术3"]}}"""


def _history_text(state: dict) -> str:
    history = state.get("history") or []
    lines = []
    for m in history[-6:]:
        role = "用户" if m.get("role") == "user" else "对手"
        lines.append(f"{role}: {m.get('content', '')[:60]}")
    return "\n".join(lines) if lines else "（尚未有对话）"


def _offers_text(state: dict) -> str:
    offers = state.get("offers_json") or []
    return " → ".join(str(o.get("numbers")) for o in offers if o.get("numbers") is not None) or "（暂无报价）"


def build_coach_prompt(state: dict) -> str:
    """构造教练 prompt（含当前局势上下文）。"""
    used = state.get("used_tactics") or []
    used_text = "、".join(used) if used else "（无）"
    return COACH_JSON_PROMPT.format(
        round=state.get("round", 1),
        phase=state.get("phase", "opening"),
        history=_history_text(state),
        used_tactics=used_text,
        offers=_offers_text(state),
        tactics_hint="、".join(list(TACTIC_PROMPTS.keys())[:4]),
    )


def mock_advice(state: dict) -> dict[str, Any]:
    """规则兜底建议（无 LLM key / 生成失败时，结构与 GLM 输出一致）。"""
    phase = state.get("phase", "opening")
    round_no = state.get("round", 1)
    if round_no <= 1:
        analysis = "谈判刚开始，双方都在摸底阶段，不宜过早亮出底牌。"
        strategy = "先试探对方底线：提出一个试探性报价并观察反应。"
        options = [
            "我们聊聊整体方案吧，您这边对总价的心理预期大概在什么范围？",
            "这个报价我们还需要内部评估，您能说说价格构成的依据吗？",
            "如果总价能谈到 200 万以内，我们可以考虑加快决策流程。",
        ]
    elif phase == "deadlock":
        analysis = "谈判陷入僵局，继续硬顶可能导致破裂。"
        strategy = "换一个维度打破僵局（账期/保修/服务），别只盯着价格。"
        options = [
            "价格上确实有难度，但如果您能在付款周期上给些灵活性，我们可以再平衡一下。",
            "要不我们把保修和后续服务单独谈？这部分也许有空间。",
            "咱们各退一步：价格保持，但服务范围可以再商量。",
        ]
    else:
        analysis = "谈判进入实质阶段，对方已表现出谈判意愿。"
        strategy = "小幅让步换取明确承诺，避免单方面大幅降价。"
        options = [
            "我们可以适当调整，但希望您今天能给个明确意向。",
            "如果贵方能接受这个方案，我们可以尽快推进合同。",
            "这个幅度已经是我们的诚意了，您看能不能在账期上配合一下？",
        ]
    return {"analysis": analysis, "strategy": strategy, "options": options}


async def get_coach_advice(llm, state: dict) -> dict[str, Any]:
    """生成教练建议（GLM 优先，失败/超限降级规则）。"""
    if not _check_rate_limit():
        logger.warning("教练调用触发限流，返回规则建议")
        return mock_advice(state)
    try:
        raw = await llm.ainvoke_json(build_coach_prompt(state))
        options = raw.get("options") or []
        return {
            "analysis": str(raw.get("analysis", "")),
            "strategy": str(raw.get("strategy", "")),
            "options": [str(o) for o in options if str(o).strip()][:3],
        }
    except Exception as exc:  # noqa: BLE001 生成失败降级规则建议
        logger.warning("教练 LLM 生成失败，降级规则建议: %s", exc)
        return mock_advice(state)
