"""Celery 异步任务核心逻辑（PRD 8.4 / 9.10）：完整报告生成 + PDF 导出。

- `run_full_report`：异步生成并持久化复盘报告（复用 report_service.generate_report）
- `export_report_pdf`：matplotlib 让步曲线 PNG + reportlab 拼 PDF，写回 reports.pdf_url

设计：核心函数注入 session 工厂（可测试，注入测试库）；Celery task 只做薄包装。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.models import Report
from app.services.report_service import generate_report

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Any]

PDF_FILE_PREFIX = "report_"
PDF_MEDIA_PREFIX = "/media/reports/"


async def run_full_report(
    session_factory: SessionFactory,
    session_id: uuid.UUID,
    judge: Callable[..., Awaitable[dict]] | None = None,
) -> Report:
    """异步生成完整报告并持久化（幂等：已存在直接返回）。

    judge 失败不阻断：主观分置空，仅保留客观分（LLMJudge 自带兜底）。
    """
    if judge is None:
        from app.services.judge import build_judge

        judge = build_judge()

    async def _safe_judge(history, scenario):
        try:
            return await judge(history, scenario)
        except Exception as exc:  # noqa: BLE001 主观评分失败不阻断报告生成
            logger.warning("主观评分失败，主观分置空: %s", exc)
            return {}

    with session_factory() as db:
        report = await generate_report(db, session_id, judge=_safe_judge)
        # PRD 9.15 双写：报告完成后落库离线通知 + 发布事件（API 进程 WS 推送）
        try:
            from app.models import NegotiationSession
            from app.services.event_bus import publish_notification
            from app.services.notification_service import create_notification

            ns = db.get(NegotiationSession, session_id)
            if ns is not None:
                create_notification(
                    db,
                    ns.user_id,
                    "report",
                    "复盘报告已生成",
                    {
                        "session_id": str(session_id),
                        "report_id": str(report.id),
                    },
                )
                db.commit()
                # 跨进程桥接：worker 无 WS 通道，经 Redis 事件由 API 进程推送
                publish_notification(
                    str(ns.user_id),
                    {
                        "type": "notification",
                        "notification": {
                            "type": "report",
                            "title": "复盘报告已生成",
                            "report_id": str(report.id),
                        },
                    },
                )
        except Exception as exc:  # noqa: BLE001 通知失败不阻断报告
            logger.warning("报告完成通知落库失败: %s", exc)
        db.refresh(report)  # 属性加载齐全后再返回（防 detached lazy load）
        return report


def _curve_image_bytes(curve: list[dict]) -> bytes | None:
    """matplotlib 渲染让步曲线为 PNG 字节（PRD 9.10 MVP 方案）。"""
    if not curve:
        return None
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei"):
        try:
            fm.findfont(name, fallback_to_default=False)
        except Exception:  # noqa: BLE001
            logger.debug("CJK 字体不可用，跳过: %s", name)
            continue
        plt.rcParams["font.sans-serif"] = [name]
        break

    rounds = [c.get("round", i + 1) for i, c in enumerate(curve)]
    prices = [float(c["price"]) for c in curve if c.get("price") is not None]
    label = curve[0].get("label", "总价")
    if not rounds or not prices:
        return None
    plt.figure(figsize=(6, 3))
    plt.plot(rounds, prices, marker="o")
    plt.title(f"让步曲线（{label}）")
    plt.xlabel("轮次")
    plt.ylabel(label)
    plt.grid(True, linestyle="--", alpha=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close()
    return buf.getvalue()


def export_report_pdf(
    session_factory: SessionFactory,
    report_id: uuid.UUID,
    out_dir: str | None = None,
) -> str:
    """导出报告为 PDF 并写回 reports.pdf_url（PRD 9.10）。

    返回 PDF 文件路径；报告不存在抛 ValueError。
    """
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    from app.models import NegotiationSession

    # 中文支持：Helvetica 不含中文字形（drawString 会乱码），改用内置 CID 字体
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    with session_factory() as db:
        report = db.get(Report, report_id)
        if report is None:
            raise ValueError(f"报告不存在: {report_id}")
        ns = db.get(NegotiationSession, report.session_id)
        scenario_title = _scenario_title(db, ns)
        out = Path(out_dir) if out_dir else Path(get_settings().pdf_output_dir)
        out.mkdir(parents=True, exist_ok=True)
        pdf_path = out / f"{PDF_FILE_PREFIX}{report_id}.pdf"

        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        _, height = A4
        y = height - 60
        c.setFont("STSong-Light", 16)
        c.drawString(60, y, "谋谈 MouTalk 复盘报告")
        y -= 30
        c.setFont("STSong-Light", 11)
        c.drawString(60, y, f"场景: {scenario_title}    总分: {report.total_score or 0}")
        y -= 20
        c.drawString(60, y, f"报告ID: {report_id}")
        y -= 30

        objective = report.objective_json or {}
        dims = objective.get("dimensions") or {}
        dim_labels = {
            "price_attainment": "价格达成率",
            "concession_margin": "让步幅度",
            "bottom_line_hold": "底线坚守",
            "time_efficiency": "时间效率",
        }
        y -= 20
        c.setFont("STSong-Light", 13)
        c.drawString(60, y, "客观分")
        c.setFont("STSong-Light", 11)
        for key, val in dims.items():
            y -= 18
            label = dim_labels.get(key, key)
            c.drawString(80, y, f"{label}: {val}")

        curve = report.concession_curve or []
        png = _curve_image_bytes(curve)
        if png:
            img = ImageReader(io.BytesIO(png))
            c.drawImage(img, 60, max(60, y - 220), width=300, height=150)
            y -= 240

        subjective = report.subjective_json or {}
        y -= 20
        c.setFont("STSong-Light", 13)
        c.drawString(60, y, "主观分与建议")
        c.setFont("STSong-Light", 11)
        for point in report.weak_points or []:
            y -= 18
            c.drawString(80, y, f"- {point}")
        y -= 18
        advice = report.advice or subjective.get("advice") or ""
        if advice:
            c.drawString(80, y, f"建议: {advice}")

        c.showPage()
        c.save()

        report.pdf_url = f"{PDF_MEDIA_PREFIX}{PDF_FILE_PREFIX}{report_id}.pdf"
        db.commit()
        return str(pdf_path)


def _scenario_title(db, ns) -> str:
    if ns is None:
        return "未知场景"
    try:
        from sqlalchemy import select

        from app.models import Scenario

        row = db.scalar(select(Scenario.title).where(Scenario.id == ns.scenario_id))
        return row or ns.scenario_id
    except Exception:  # noqa: BLE001 标题取不到不阻断导出
        return ns.scenario_id
