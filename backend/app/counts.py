"""工单数量核对口径：概览页、热线列表页、导入核对都必须走这里。

口径变更时把 COUNT_RULE_VERSION 加一并改 apply_rule，存量数据会在下次
prepare / 服务启动时自动按新口径重算一遍（见 jointdebug.recompute_if_stale）。
"""
from __future__ import annotations

from typing import Any

from app.db import Database

MODULE = "complaint"

# 核对口径版本：v1=按记录编号去重后统计全部工单。
# 口径规矩改动时必须 +1，触发存量数据重算。
COUNT_RULE_VERSION = 1
COUNT_RULE_DESC = "按记录编号去重，统计全部工单"

# 非办结状态：概览卡片的「待处理」口径
OPEN_STATUSES = ["待转办", "已转办", "处理中"]


def apply_rule(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """对一批工单执行当前核对口径，返回总量与分状态数量。

    同一记录编号在数据里只会出现一条（落库即 UNIQUE），这里仍再去重一次，
    保证从任何来源拿到的行集合都按同一规矩计数。
    """
    seen: set[str] = set()
    by_status: dict[str, int] = {}
    pending = 0
    abnormal = 0
    for row in rows:
        record_no = str(row.get("记录编号") or "").strip()
        if not record_no or record_no in seen:
            continue
        seen.add(record_no)
        status = str(row.get("记录状态") or row.get("status") or "").strip()
        by_status[status] = by_status.get(status, 0) + 1
        if status in OPEN_STATUSES:
            pending += 1
        if row.get("abnormal"):
            abnormal += 1
    return {
        "total": len(seen),
        "by_status": by_status,
        "pending": pending,
        "abnormal": abnormal,
        "rule_version": COUNT_RULE_VERSION,
        "rule_desc": COUNT_RULE_DESC,
    }


def count_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return apply_rule(rows)


def stored_rule_version(db: Database) -> int:
    raw = db.get_meta("count_rule_version")
    return int(raw) if raw else 0


def is_stale(db: Database) -> bool:
    """存量数据的核对口径是否落后于当前代码。"""
    return stored_rule_version(db) < COUNT_RULE_VERSION
