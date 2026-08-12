"""复盘报告服务：简版结果、客观分规则引擎、报告生成与持久化（PRD 7.4 / 8.4 / 9.9）。

- 简版结果：价格达成率 = (成交价 - 底线) / (首次报价 - 底线)，底线坚守，胜负判定
- 客观分（规则引擎，纯计算）：价格达成率 | 让步幅度 | 底线坚守 | 耗时
- 主观分（LLM Judge）：话术自然度 | 策略多样性 | 情绪控制 | 逻辑一致性（1-5 归一化）
- 总分：total = 0.6 * objective_total + 0.4 * subjective_normalized
- 胜负：total >= 0.6 胜，0.4-0.6 平，<0.4 负
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import NegotiationSession, Report, Scenario, SessionStatus, UserRole
from app.services.judge import build_judge

logger = logging.getLogger(__name__)

FREE_TREND_MONTHS = 3  # PRD 9.18：免费用户仅近 3 个月
TREND_CACHE_SECONDS = 3600  # 趋势缓存 1 小时（Redis）

OBJECTIVE_WEIGHTS = {
    "price_attainment": 0.4,
    "concession_margin": 0.2,
    "bottom_line_hold": 0.3,
    "time_efficiency": 0.1,
}

Judge = Callable[[list[dict], dict], Awaitable[dict[str, Any]]]


def _price_dim(scenario: dict) -> dict | None:
    for d in scenario.get("dimensions") or []:
        if d.get("key") == "price":
            return d
    return None


def _offer_prices(offers: list[dict]) -> list[float]:
    return [float(o["numbers"]) for o in offers if o.get("numbers") is not None]


def _attainment(price_dim: dict, final: float) -> float:
    """价格达成率 0-1：direction=min 时越低越优，max 时越高越优。"""
    first = float(price_dim["first_offer"])
    bottom = float(price_dim["bottom_line"])
    if price_dim.get("direction") == "max":
        best, worst = bottom, first
    else:
        best, worst = bottom, first
    if worst == best:
        return 1.0
    v = (final - worst) / (best - worst)
    return max(0.0, min(1.0, v))


def _verdict(score: float) -> str:
    if score >= 0.6:
        return "win"
    if score >= 0.4:
        return "draw"
    return "lose"


def compute_simple_result(scenario: dict, offers: list[dict]) -> dict:
    """即时简版结果（PRD 7.4，同步 <1s）。"""
    price_dim = _price_dim(scenario)
    prices = _offer_prices(offers)
    final = prices[-1] if prices else None
    attainment = _attainment(price_dim, final) if (price_dim and final is not None) else 0.0
    hold = 1.0
    if price_dim and final is not None:
        bottom = float(price_dim["bottom_line"])
        if price_dim.get("direction") == "min" and final < bottom or price_dim.get("direction") == "max" and final > bottom:
            hold = 0.0
    score = attainment * hold
    return {
        "price_attainment": attainment,
        "bottom_line_hold": hold,
        "score": score,
        "verdict": _verdict(score),
    }


def compute_objective_score(scenario: dict, offers: list[dict]) -> dict:
    """客观分（规则引擎，PRD 7.4）：四维度归一化 0-1 + 加权总分。"""
    price_dim = _price_dim(scenario)
    prices = _offer_prices(offers)
    final = prices[-1] if prices else None

    price_attainment = _attainment(price_dim, final) if (price_dim and final is not None) else 0.0

    # 让步幅度：报价发生变化的轮次数 / 总轮次数
    n = len(prices)
    changes = sum(1 for i in range(1, n) if prices[i] != prices[i - 1]) if n > 1 else 0
    concession_margin = changes / n if n else 0.0

    # 底线坚守：价格维度未突破底线为 1，突破为 0
    bottom_line_hold = 1.0
    if price_dim and final is not None:
        bottom = float(price_dim["bottom_line"])
        if price_dim.get("direction") == "min" and final < bottom or price_dim.get("direction") == "max" and final > bottom:
            bottom_line_hold = 0.0

    # 耗时：轮数越少效率越高，1 轮满分，10 轮以上为 0
    time_efficiency = max(0.0, 1.0 - (n - 1) / 9.0) if n else 1.0

    dims = {
        "price_attainment": price_attainment,
        "concession_margin": concession_margin,
        "bottom_line_hold": bottom_line_hold,
        "time_efficiency": time_efficiency,
    }
    total = sum(dims[k] * OBJECTIVE_WEIGHTS[k] for k in OBJECTIVE_WEIGHTS)
    return {"dimensions": dims, "weights": dict(OBJECTIVE_WEIGHTS), "total": total}


def _concession_curve(scenario: dict, offers: list[dict]) -> list[dict]:
    price_dim = _price_dim(scenario)
    if price_dim is None:
        return []
    return [
        {"round": i + 1, "price": float(o["numbers"]), "label": price_dim.get("label", "总价")}
        for i, o in enumerate(offers)
        if o.get("numbers") is not None
    ]


def _normalize_subjective(dims: dict[str, float]) -> float:
    """主观分 1-5 归一化到 0-1：(score - 1) / 4（PRD 9.9）。"""
    values = [float(v) for v in dims.values() if v is not None]
    if not values:
        return 0.0
    avg = sum(values) / len(values)
    return max(0.0, min(1.0, (avg - 1) / 4))


def _get(db: Session, session_id: uuid.UUID) -> NegotiationSession:
    ns = db.scalar(
        select(NegotiationSession).where(NegotiationSession.id == session_id)
    )
    if ns is None:
        raise ValueError(f"会话不存在: {session_id}")
    return ns


def _scenario_config(db: Session, scenario_id: str) -> dict:
    row = db.scalar(select(Scenario).where(Scenario.id == scenario_id))
    if row is None:
        raise ValueError(f"场景包不存在: {scenario_id}")
    # 自定义场景无 JSON 文件：DB config_json 优先，官方回退文件（C.9 自定义场景支持）
    from app.services.scenario_loader import load_scenario_for_session

    return load_scenario_for_session(db, scenario_id)


async def generate_report(
    db: Session,
    session_id: uuid.UUID,
    judge: Judge | None = None,
) -> Report:
    """生成复盘报告并持久化；已存在则幂等返回（PRD 8.4）。"""
    existing = db.scalar(select(Report).where(Report.session_id == session_id))
    if existing is not None:
        return existing

    ns = _get(db, session_id)
    scenario = _scenario_config(db, ns.scenario_id)
    offers = list(ns.offers_json or [])

    objective = compute_objective_score(scenario, offers)
    history = list(ns.messages_json or [])

    subjective = {"dimensions": {}, "normalized": 0.0, "weak_points": [], "advice": ""}
    judge = judge or build_judge()
    result = await judge(history, scenario)
    dims = {
        k: result.get(k)
        for k in ("naturalness", "strategy_diversity", "emotion_control", "logic_consistency")
        if result.get(k) is not None
    }
    subjective = {
        "dimensions": dims,
        "normalized": _normalize_subjective(dims),
        "weak_points": list(result.get("weak_points") or []),
        "advice": result.get("advice", ""),
    }

    total = 0.6 * objective["total"] + 0.4 * subjective["normalized"]

    report = Report(
        session_id=ns.id,
        total_score=round(total, 2),
        objective_json=objective,
        subjective_json=subjective,
        concession_curve=_concession_curve(scenario, offers),
        weak_points=subjective["weak_points"],
        advice=subjective["advice"],
    )
    db.add(report)
    ns.status = SessionStatus.REPORTED
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """用户的历史复盘报告列表（按生成时间倒序）。"""
    rows = db.execute(
        select(Report, NegotiationSession.scenario_id, NegotiationSession.ended_at)
        .join(NegotiationSession, Report.session_id == NegotiationSession.id)
        .where(NegotiationSession.user_id == user_id)
        .order_by(Report.generated_at.desc())
    ).all()
    return [
        {
            "id": str(rep.id),
            "session_id": str(rep.session_id),
            "scenario_id": scenario_id,
            "total_score": float(rep.total_score) if rep.total_score is not None else None,
            "objective_json": rep.objective_json,
            "subjective_json": rep.subjective_json,
            "concession_curve": rep.concession_curve,
            "weak_points": rep.weak_points or [],
            "advice": rep.advice,
            "generated_at": rep.generated_at.isoformat() if rep.generated_at else None,
        }
        for rep, scenario_id, _ in rows
    ]


def report_exists(db: Session, report_id: uuid.UUID) -> bool:
    """报告是否存在（不限归属，供 API 区分 403/404）。"""
    return db.scalar(
        select(Report.id).where(Report.id == report_id)
    ) is not None


def get_report(db: Session, report_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
    """按 id 取报告，校验归属（数据隔离）。"""
    row = db.execute(
        select(Report, NegotiationSession.scenario_id, NegotiationSession.ended_at)
        .join(NegotiationSession, Report.session_id == NegotiationSession.id)
        .where(Report.id == report_id, NegotiationSession.user_id == user_id)
    ).first()
    if row is None:
        return None
    rep, scenario_id, ended_at = row
    return {
        "id": str(rep.id),
        "session_id": str(rep.session_id),
        "scenario_id": scenario_id,
        "total_score": float(rep.total_score) if rep.total_score is not None else None,
        "objective_json": rep.objective_json,
        "subjective_json": rep.subjective_json,
        "concession_curve": rep.concession_curve,
        "weak_points": rep.weak_points or [],
        "advice": rep.advice,
        "pdf_url": rep.pdf_url,
        "generated_at": rep.generated_at.isoformat() if rep.generated_at else None,
        "ended_at": ended_at.isoformat() if ended_at else None,
    }


class CompareError(Exception):
    """报告对比参数/权限错误（code 供 API 映射 HTTP 状态）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


COMPARE_MIN = 2
COMPARE_MAX = 5


def compare_reports(
    db: Session,
    user_id: uuid.UUID,
    report_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    """对比多份报告（PRD 故事 4 / 阶段 2）：数据隔离 + 按总分降序。

    数量限制 2-5 份；任一报告不存在或不属于该用户即报错（防探测他人数据）。
    """
    if not (COMPARE_MIN <= len(report_ids) <= COMPARE_MAX):
        raise CompareError(
            "INVALID_COMPARE_COUNT",
            f"对比数量须为 {COMPARE_MIN}-{COMPARE_MAX} 份",
        )
    reports: list[dict[str, Any]] = []
    for rid in report_ids:
        report = get_report(db, rid, user_id)
        if report is None:
            if report_exists(db, rid):
                raise CompareError("FORBIDDEN", "无权对比他人报告")
            raise CompareError("REPORT_NOT_FOUND", "报告不存在")
        reports.append(report)
    reports.sort(key=lambda r: (r.get("total_score") or 0.0), reverse=True)
    return reports


def report_trends(
    db: Session,
    user_id: uuid.UUID,
    role: UserRole,
    scenario_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    """进步曲线（PRD 9.18 / 故事 11）：按月聚合总分与双轨得分。

    - 免费用户仅近 FREE_TREND_MONTHS 个月；Pro 完整历史
    - 数据点 < 2 → insufficient=True（前端提示"继续训练解锁趋势"）
    - 场景过滤：scenario_id 可选
    """
    now = now or datetime.now(UTC)
    month_expr = func.date_trunc("month", Report.generated_at)
    query = (
        select(
            month_expr.label("month"),
            func.avg(Report.total_score).label("total"),
            func.avg(Report.objective_json["total"].as_float()).label("objective"),
            func.avg(Report.subjective_json["normalized"].as_float()).label("subjective"),
        )
        .join(NegotiationSession, Report.session_id == NegotiationSession.id)
        .where(NegotiationSession.user_id == user_id)
    )
    if scenario_id:
        query = query.where(NegotiationSession.scenario_id == scenario_id)
    if role != UserRole.PRO:
        cutoff = now - timedelta(days=FREE_TREND_MONTHS * 30)
        query = query.where(Report.generated_at >= cutoff)
    rows = db.execute(
        query.group_by(month_expr).order_by(month_expr)
    ).all()

    points = [
        {
            "month": str(row.month)[:7] if row.month else "",
            "total": round(float(row.total), 3) if row.total is not None else 0.0,
            "objective": round(float(row.objective), 3) if row.objective is not None else 0.0,
            "subjective": round(float(row.subjective), 3) if row.subjective is not None else 0.0,
        }
        for row in rows
    ]
    return {
        "insufficient": len(points) < 2,
        "points": points if len(points) >= 2 else [],
    }
