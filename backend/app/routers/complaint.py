"""市民热线接口：维护热线记录，覆盖转办部门、处理反馈、办结归档等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.complaint import ComplaintService

router = APIRouter(prefix="/api/complaint", tags=["市民热线"])

service = ComplaintService()

LIST_FIELDS = ["记录编号", "来电人", "来电内容", "问题位置", "问题类型", "转办部门", "处理结果", "记录状态"]
STATUSES = ["待转办", "已转办", "处理中", "已办结"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待转办、已转办、处理中、已办结"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与状态过滤市民热线列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 固定路径要放在 /{entry_id} 前面，否则 "stats"、"export" 会被当成编号解析成 422。
@router.get("/stats")
def stats() -> dict[str, Any]:
    """工单统计：概览页与本页卡片读同一份数据，条数一致。"""
    return service.stats()


@router.post("/import", response_model=ActionResult)
def import_seed() -> ActionResult:
    """重复导入联调示例数据：同一记录编号只算一次；导入后自动核对工单数量。"""
    result = service.import_seed()
    if not result["verified"]:
        return ActionResult(ok=False, message=f"示例数据已导入但工单数量核对未通过：{result['problems']}", entry=result)
    return ActionResult(
        ok=True,
        message=f"示例数据已导入并核对通过（新增 {result['inserted']} 条，跳过重复 {result['skipped']} 条）",
        entry=result,
    )


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出市民热线清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "complaint", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条热线记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"热线记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条热线记录，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="热线记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条热线记录执行转办部门、处理反馈、办结归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
