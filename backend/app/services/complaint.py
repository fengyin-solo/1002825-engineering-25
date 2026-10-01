"""市民热线业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app import reconcile
from app.seed import SEED_ROWS
from app.store import store

MODULE = "complaint"
REQUIRED_FIELDS = ["记录编号", "来电人", "来电内容"]
OPTIONAL_FIELDS = ["问题位置", "问题类型", "转办部门", "处理结果", "记录状态"]
STATUS_ORDER = ["待转办", "已转办", "处理中", "已办结"]
ACTION_RULES = {"转办部门": "已转办", "处理反馈": "处理中", "办结归档": "已办结"}
NEGATIVE_ACTIONS = []


class ComplaintService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, Any]:
        """工单统计：与概览页读同一份数据、同一套核对口径，两个页面条数才一致。"""
        rows = store.rows(MODULE)
        by_status = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "")
            if status in by_status:
                by_status[status] += 1
        return {
            "total": reconcile.count_tickets(rows),
            "by_status": by_status,
            "rule_version": reconcile.RULE_VERSION,
        }

    def import_seed(self) -> dict[str, Any]:
        """把固定的联调示例数据幂等导入：同一记录编号再次入库只算一次。"""
        inserted, skipped = store.upsert_rows(MODULE, SEED_ROWS[MODULE])
        reconcile.recount(store)
        verified, report = reconcile.verify(store)
        return {
            "inserted": inserted,
            "skipped": skipped,
            "verified": verified,
            "problems": report["problems"],
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        code = str(values.get("记录编号") or "").strip()
        if any(str(row.get("记录编号") or "").strip() == code for row in rows):
            return None, f"记录编号 {code} 已存在，同一工单编号只入库一次"
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"热线记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于市民热线可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"热线记录已{action}"
