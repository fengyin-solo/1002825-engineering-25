"""市民热线业务规则：状态流转、字段校验与筛选口径都收在这里。

工单数量统一走 app.counts 的核对口径，概览页与列表页不会各算各的；
落库按「记录编号」唯一，重复导入同一编号只算一条。
"""
from __future__ import annotations

import json
from typing import Any

from app import counts
from app.db import get_database
from app.store import store

MODULE = "complaint"
REQUIRED_FIELDS = ["记录编号", "来电人", "来电内容"]
STATUS_ORDER = ["待转办", "已转办", "处理中", "已办结"]
ACTION_RULES = {"转办部门": "已转办", "处理反馈": "处理中", "办结归档": "已办结"}
NEGATIVE_ACTIONS = []


class ComplaintService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        issue_type: str | None = None,
        department: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if issue_type:
            rows = [row for row in rows if str(row.get("问题类型") or "") == issue_type]
        if department:
            rows = [row for row in rows if str(row.get("转办部门") or "") == department]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(self) -> dict[str, int]:
        """页面卡片用：总数与分状态数，口径与概览页、导入核对完全一致。"""
        summary = counts.count_rows(store.rows(MODULE))
        return {
            "total": summary["total"],
            "pending": summary["pending"],
            "abnormal": summary["abnormal"],
            "by_status": dict(summary["by_status"]),
            "rule_version": summary["rule_version"],
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        record_no = str(values["记录编号"]).strip()
        db = get_database()
        if db is not None and db.get_complaint_row_by_no(record_no) is not None:
            return None, [f"记录编号 {record_no} 已存在，同一工单编号不能重复入库"]
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for optional in ("问题位置", "问题类型", "转办部门", "处理结果"):
            entry[optional] = values.get(optional, "")
        entry["status"] = STATUS_ORDER[0]
        entry["记录状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        if db is not None:
            db.upsert_complaint_row(record_no, entry["status"], json.dumps(entry, ensure_ascii=False))
            stored = db.get_complaint_row_by_no(record_no)
            entry["id"] = stored["id"] if stored else entry["id"]
            store.reload_complaint()
        else:
            rows.append(entry)
        return self.get_entry(entry["id"]) or entry, []

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
        entry["记录状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        db = get_database()
        if db is not None:
            db.update_complaint_status(entry_id, target, json.dumps(entry, ensure_ascii=False))
            store.reload_complaint()
        return entry, f"热线记录已{action}"
