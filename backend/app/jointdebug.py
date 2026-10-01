"""联调准备固定动作：导入固定示例数据 → 自动核对工单数量 → 给出是否准备好。

命令行入口见 app.cli（make prepare / python -m app.cli prepare），
服务启动时 lifespan 也会跑同一套，保证两条路径口径一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app import counts
from app.db import Database
from app.fixtures import (
    EXPECTED_STATUS_COUNTS,
    EXPECTED_TOTAL,
    JOINTDEBUG_ROWS,
    MODULE,
    OPTIONS,
)

STATUS_TO_INTERNAL = {
    "待转办": "待转办",
    "已转办": "已转办",
    "处理中": "处理中",
    "已办结": "已办结",
}
OPEN_STATUSES = {"待转办", "已转办", "处理中"}


@dataclass
class ImportReport:
    inserted: int = 0
    updated: int = 0
    record_nos: list[str] = field(default_factory=list)
    total_after: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "total_after": self.total_after,
            "record_nos": self.record_nos,
        }


@dataclass
class VerificationReport:
    ok: bool
    expected_total: int
    actual_total: int
    expected_by_status: dict[str, int]
    actual_by_status: dict[str, int]
    rule_version: int
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "expected_total": self.expected_total,
            "actual_total": self.actual_total,
            "expected_by_status": self.expected_by_status,
            "actual_by_status": self.actual_by_status,
            "rule_version": self.rule_version,
            "problems": list(self.problems),
        }


def _row_to_payload(row: dict[str, Any]) -> tuple[str, str]:
    """把示例工单转成 (内部 status, payload json)；payload 含完整展示字段。"""
    display_status = str(row.get("记录状态") or "").strip()
    status = STATUS_TO_INTERNAL.get(display_status, display_status)
    payload = dict(row)
    payload["status"] = status
    payload["pending"] = status in OPEN_STATUSES
    payload["abnormal"] = False
    return status, json.dumps(payload, ensure_ascii=False)


def _decode_row(record: dict[str, Any]) -> dict[str, Any]:
    """把数据库记录还原成业务行（与旧 seed 行结构兼容）。"""
    try:
        payload = json.loads(record.get("payload") or "{}")
    except json.JSONDecodeError:
        payload = {}
    row = dict(payload)
    row.setdefault("id", record["id"])
    row.setdefault("status", record["status"])
    row.setdefault("记录编号", record["record_no"])
    row.setdefault("记录状态", record["status"])
    row.setdefault("pending", record["status"] in OPEN_STATUSES)
    row.setdefault("abnormal", False)
    row["id"] = record["id"]
    return row


def load_rows(db: Database) -> list[dict[str, Any]]:
    """读全部热线工单，概览页和列表页共用，保证两边条数同一份。"""
    return [_decode_row(record) for record in db.list_complaint_rows()]


def import_fixture(db: Database) -> ImportReport:
    """幂等导入固定示例数据：同一记录编号再次入库只算一次（走更新）。"""
    report = ImportReport()
    for row in JOINTDEBUG_ROWS:
        record_no = str(row["记录编号"])
        status, payload_json = _row_to_payload(row)
        _, inserted = db.upsert_complaint_row(record_no, status, payload_json)
        if inserted:
            report.inserted += 1
        else:
            report.updated += 1
        report.record_nos.append(record_no)
    recompute(db)
    report.total_after = counts.count_rows(load_rows(db))["total"]
    return report


def recompute(db: Database) -> dict[str, Any]:
    """按当前口径重算存量数据，并把口径版本落库。"""
    rows = load_rows(db)
    stats = counts.count_rows(rows)
    db.set_meta("count_rule_version", str(counts.COUNT_RULE_VERSION))
    db.set_meta("complaint_total", str(stats["total"]))
    db.set_meta("complaint_by_status", json.dumps(stats["by_status"], ensure_ascii=False))
    return stats


def recompute_if_stale(db: Database) -> dict[str, Any] | None:
    """口径规矩变更后，对存量数据重算一遍；未变更则不动。"""
    if counts.is_stale(db):
        return recompute(db)
    return None


def verify(db: Database) -> VerificationReport:
    """核对工单数量：总量与分状态数都要和固定示例数据一致，否则不算准备好。"""
    stats = counts.count_rows(load_rows(db))
    problems: list[str] = []
    if stats["total"] != EXPECTED_TOTAL:
        problems.append(
            f"工单总数 {stats['total']} 与示例数据 {EXPECTED_TOTAL} 不一致"
        )
    for status, expected in EXPECTED_STATUS_COUNTS.items():
        actual = stats["by_status"].get(status, 0)
        if actual != expected:
            problems.append(f"状态「{status}」条数 {actual} 与示例 {expected} 不一致")
    if counts.is_stale(db):
        problems.append(
            f"核对口径已升级到 v{counts.COUNT_RULE_VERSION}，存量数据还没重算"
        )
    return VerificationReport(
        ok=not problems,
        expected_total=EXPECTED_TOTAL,
        actual_total=stats["total"],
        expected_by_status=dict(EXPECTED_STATUS_COUNTS),
        actual_by_status=dict(stats["by_status"]),
        rule_version=counts.COUNT_RULE_VERSION,
        problems=problems,
    )


def prepare(db: Database) -> dict[str, Any]:
    """固定动作全流程：幂等导入 → 口径过期则重算 → 自动核对。"""
    imported = import_fixture(db)
    recomputed = recompute_if_stale(db)
    verification = verify(db)
    return {
        "module": MODULE,
        "ready": verification.ok,
        "imported": imported.as_dict(),
        "recomputed": recomputed,
        "verification": verification.as_dict(),
        "options": OPTIONS,
    }


def readiness(db: Database) -> dict[str, Any]:
    """服务健康检查用：不改动数据，只报告当前准备状态。"""
    verification = verify(db)
    return {
        "module": MODULE,
        "ready": verification.ok,
        "verification": verification.as_dict(),
        "options": OPTIONS,
    }
