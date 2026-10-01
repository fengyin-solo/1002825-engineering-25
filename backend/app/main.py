"""园林绿化养护管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health

起服务前请先跑固定动作（run.sh 会自动执行）：
    make prepare  # 端口/数据库预检 → 导入固定示例工单 → 自动核对工单数量
"""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import jointdebug
from app.config import settings
from app.db import DatabaseUnavailable, get_database, get_database_error, init_database
from app.routers import ROUTERS
from app.store import store


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时把联调准备的固定动作在服务侧也走一遍：

    连库 → 幂等导入固定示例工单 → 口径过期则重算存量 → 核对工单数量。
    核对不过不阻止启动，但 /api/health 会明确报「未就绪」和原因，
    避免值班同事把没准备好误判成页面坏了。
    """
    startup: dict[str, object] = {"db_ready": False}
    try:
        db = init_database(force=True)
        startup["db_ready"] = True
        jointdebug.prepare(db)
        store.reload_complaint()
        startup["jointdebug"] = jointdebug.readiness(db)
    except DatabaseUnavailable as exc:
        startup["db_error"] = str(exc)
    app.state.startup = startup
    yield


app = FastAPI(title="园林绿化养护管理平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、数据库连通、示例工单核对通过。"""
    db = get_database()
    db_error = get_database_error()
    ready_report: dict[str, object] | None = None
    if db is not None:
        ready_report = jointdebug.readiness(db)
    healthy = bool(db is not None and ready_report and ready_report.get("ready"))
    return {
        "ok": healthy,
        "app": settings.app_name,
        "modules": len(store.module_names()),
        "database": {"ready": db is not None, "error": str(db_error) if db_error else None},
        "jointdebug": ready_report,
        "hint": None if healthy else "联调未就绪：请在 backend 目录运行 make prepare 后再起服务",
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    市民热线的工单数量与热线列表页共用同一核对口径。
    """
    return store.overview()
