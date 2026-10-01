"""市民热线接口：维护热线记录，覆盖转办部门、处理反馈、办结归档等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.fixtures import OPTIONS
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.complaint import ComplaintService

router = APIRouter(prefix="/api/complaint", tags=["市民热线"])

service = ComplaintService()

LIST_FIELDS = ["记录编号", "来电人", "来电内容", "问题位置", "问题类型", "转办部门", "处理结果", "记录状态"]
STATUSES = ["待转办", "已转办", "处理中", "已办结"]


@router.get("/options")
def list_options() -> dict[str, Any]:
    """联调固定选项：问题类型与转办部门取自同一份示例数据。"""
    return {"module": "complaint", "options": OPTIONS}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出市民热线清单：返回当前过滤条件下的全量数据。

    条数与列表接口、概览页走同一核对口径。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "complaint", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待转办、已转办、处理中、已办结"),
    issue_type: str | None = Query(default=None, description="问题类型，固定选项之一"),
    department: str | None = Query(default=None, description="转办部门，固定选项之一"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、状态、问题类型、转办部门过滤市民热线列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        issue_type=issue_type,
        department=department,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size, stats=service.stats())


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条热线记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"热线记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条热线记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段或数据冲突：{'、'.join(missing)}")
    return ActionResult(ok=True, message="热线记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条热线记录执行转办部门、处理反馈、办结归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
