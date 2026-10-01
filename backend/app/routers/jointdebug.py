"""联调准备接口：把命令行的固定动作也暴露给值班同事自查。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import jointdebug
from app.db import DatabaseUnavailable, get_database
from app.schemas import ActionResult

router = APIRouter(prefix="/api/jointdebug", tags=["联调准备"])


def _require_db():
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库未就绪，请先在 backend 目录运行 make prepare")
    return db


@router.get("/readiness", response_model=dict)
def readiness() -> dict:
    """查看联调准备状态：工单数量是否与固定示例数据核对通过。"""
    db = _require_db()
    return jointdebug.readiness(db)


@router.post("/prepare", response_model=ActionResult)
def prepare() -> ActionResult:
    """幂等导入固定示例数据并自动核对工单数量；重复导入同一工单编号只算一次。"""
    db = _require_db()
    report = jointdebug.prepare(db)
    verification = report["verification"]
    if verification["ok"]:
        imported = report["imported"]
        return ActionResult(
            ok=True,
            message=(
                f"联调准备完成：示例工单新增 {imported['inserted']} 条、"
                f"更新 {imported['updated']} 条，工单总数 {verification['actual_total']} 条核对通过"
            ),
            entry=report,
        )
    return ActionResult(
        ok=False,
        message="联调准备未完成：" + "；".join(verification["problems"]),
        entry=report,
    )


@router.post("/recompute", response_model=ActionResult)
def recompute() -> ActionResult:
    """核对口径规矩变更后，对存量工单重算一遍。"""
    db = _require_db()
    try:
        stats = jointdebug.recompute(db)
    except DatabaseUnavailable as exc:  # pragma: no cover - 由前置检查兜底
        return ActionResult(ok=False, message=str(exc))
    return ActionResult(
        ok=True,
        message=f"已按口径 v{stats['rule_version']} 重算存量工单，总数 {stats['total']} 条",
        entry=stats,
    )
