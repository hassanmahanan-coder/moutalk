"""复盘报告 API：列表 + 详情 + PDF 下载（PRD 8.4 / 9.9 / 9.10，数据隔离）。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.services import report_service
from app.services.celery_tasks import PDF_FILE_PREFIX, export_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    items = report_service.list_reports(db, current_user.id)
    return {"items": items}


@router.get("/compare")
def compare_reports(
    ids: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """对比 2-5 份报告（PRD 故事 4 / 阶段 2）：按总分降序 + 数据隔离。"""
    try:
        report_ids = [uuid.UUID(part) for part in ids.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "报告不存在"})
    try:
        reports = report_service.compare_reports(db, current_user.id, report_ids)
    except report_service.CompareError as exc:
        status_code = {  # 显式映射便于扩展
            "INVALID_COMPARE_COUNT": 400,
            "FORBIDDEN": 403,
            "REPORT_NOT_FOUND": 404,
        }.get(exc.code, 400)
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})
    return {"count": len(reports), "reports": reports}


@router.get("/trends")
def get_report_trends(
    scenario_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """进步曲线（PRD 9.18 / 故事 11）：按月聚合总分与双轨得分。"""
    return report_service.report_trends(db, current_user.id, current_user.role, scenario_id)


@router.get("/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "报告不存在"})
    report = report_service.get_report(db, rid, current_user.id)
    if report is None:
        if report_service.report_exists(db, rid):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "无权访问该报告"})
        raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "报告不存在"})
    return report


def _trigger_pdf_export(db: Session, rid: uuid.UUID) -> None:
    """触发 PDF 导出（优先 Celery 异步，dev/无 broker 时降级同步）。"""
    if get_settings().app_env != "dev":
        try:
            from app.celery_app import export_pdf

            export_pdf.delay(str(rid))
            return
        except Exception as exc:  # noqa: BLE001 broker 不可用（本机 Redis 未启）降级同步导出
            logger.warning("Celery 提交失败，降级同步导出: %s", exc)
    try:
        export_report_pdf(sessionmaker(bind=db.get_bind(), autoflush=False), rid)
    except Exception as inner:  # noqa: BLE001 导出失败不阻断，返回 404 待重试
        logger.warning("PDF 同步导出失败: %s", inner)


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """下载报告 PDF（PRD 9.10）。未导出时触发导出并返回 404 待重试。"""
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "报告不存在"})
    report = report_service.get_report(db, rid, current_user.id)
    if report is None:
        if report_service.report_exists(db, rid):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "无权访问该报告"})
        raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "报告不存在"})

    if not report.get("pdf_url"):
        _trigger_pdf_export(db, rid)
        db.expire_all()
        report = report_service.get_report(db, rid, current_user.id)
        if report and report.get("pdf_url"):
            pdf_path = Path(get_settings().pdf_output_dir) / f"{PDF_FILE_PREFIX}{rid}.pdf"
            if pdf_path.exists():
                return FileResponse(pdf_path, media_type="application/pdf", filename=f"moutalk-report-{rid}.pdf")
        raise HTTPException(status_code=404, detail={"code": "PDF_NOT_READY", "message": "PDF 生成中，请稍后重试"})

    pdf_path = Path(get_settings().pdf_output_dir) / f"{PDF_FILE_PREFIX}{rid}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail={"code": "PDF_NOT_READY", "message": "PDF 生成中，请稍后重试"})
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"moutalk-report-{rid}.pdf")
