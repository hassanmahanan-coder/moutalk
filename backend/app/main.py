import asyncio
import sys

# Windows：psycopg 异步驱动与默认 ProactorEventLoop 不兼容（PostgresSaver 需
# SelectorEventLoop，PRD 9.1）。必须在应用启动前设置事件循环策略。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.negotiation import router as negotiation_router
from app.api.notifications import router as notifications_router
from app.api.payment import router as payment_router
from app.api.quota import router as quota_router
from app.api.reports import router as reports_router
from app.api.scenarios import router as scenarios_router
from app.api.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.db import Base, engine
from app.services.scenario_seed import seed_scenarios

settings = get_settings()

app = FastAPI(
    title="谋谈 MouTalk API",
    version="0.1.0",
    debug=settings.debug,
)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(negotiation_router)
app.include_router(reports_router)
app.include_router(scenarios_router)
app.include_router(payment_router)
app.include_router(quota_router)
app.include_router(notifications_router)

from pathlib import Path

Path(settings.pdf_output_dir).mkdir(parents=True, exist_ok=True)
app.mount(
    "/media/reports",
    StaticFiles(directory=settings.pdf_output_dir),
    name="report-pdfs",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": detail.get("code", "HTTP_ERROR"), "message": detail.get("message", "")}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法"}},
    )


@app.on_event("startup")
def init_db() -> None:
    """开发环境自动建表 + 场景包入库（生产环境改用 Alembic 迁移）。"""
    Base.metadata.create_all(engine)
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        seed_scenarios(db)
        db.commit()


@app.on_event("shutdown")
async def shutdown_ws() -> None:
    """优雅关闭（PRD 9.8）：向所有 WebSocket 推送 server_shutdown 并等待 5s。"""
    from app.services.ws_manager import get_ws_manager

    manager = get_ws_manager()
    if not manager.connections:
        return
    await manager.broadcast({"type": "server_shutdown"})
    await asyncio.sleep(5)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
