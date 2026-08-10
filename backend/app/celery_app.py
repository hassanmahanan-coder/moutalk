"""Celery 应用与异步任务注册（PRD 8.4 / 9.10 / 9.2）。

- `generate_full_report(session_id)`：完整复盘报告生成（LLM Judge 在 worker 内跑）
- `export_pdf(report_id)`：PDF 导出子任务

Windows 开发机不支持 Celery worker（官方不推荐），统一走 Docker：
`docker compose up -d celery_worker`（--pool=solo 单进程）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from celery import Celery

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.celery_tasks import export_report_pdf, run_full_report
from app.services.payment_service import reconcile_pending_payments

logger = logging.getLogger(__name__)

settings = get_settings()

app = Celery(
    "moutalk",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)

app.conf.beat_schedule = {
    "reconcile-pending-payments": {
        "task": "reconcile_pending_payments",
        "schedule": 3600.0,  # 每小时主动对账一次（PRD 7.5）
        "options": {"expires": 1800.0},
    },
}


@app.task(name="generate_full_report")
def generate_full_report(session_id: str) -> str:
    """异步生成完整复盘报告（worker 内自建 DB session）。"""
    return asyncio.run(run_full_report(SessionLocal, uuid.UUID(session_id)))


@app.task(name="export_pdf")
def export_pdf(report_id: str) -> str:
    """异步导出报告 PDF（写回 reports.pdf_url）。"""
    return export_report_pdf(SessionLocal, uuid.UUID(report_id))


@app.task(name="reconcile_pending_payments")
def reconcile_pending_payments_task(timeout_minutes: int = 30) -> dict:
    """主动对账（PRD 7.5）：真实 alipay.trade.query 查单补登记。

    未配置支付宝密钥时 query_order 内部自动降级（每单跳过，仅扫计数）。
    """
    with SessionLocal() as db:
        return reconcile_pending_payments(db, query_order=None, timeout_minutes=timeout_minutes)
