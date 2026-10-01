"""工单数量核对规矩：口径按版本管理，规矩变更后存量数据要重算一遍。

当前核对口径：同一工单编号只算一条，工单数量 = 编号去重后的条数；
示例数据里的每个工单编号在库里必须恰好出现一次。

规矩调整时把 RULE_VERSION 加一：服务启动、联调准备检查与健康检查都会发现
版本对不上，自动对存量数据重算一遍并重盖版本戳；核对不通过就不算准备好。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

RULE_VERSION = 1


def code_field(rows: list[dict[str, Any]]) -> str | None:
    """找到这批记录里的工单编号字段（各模块的编号字段都叫「xx编号」）。"""
    for row in rows:
        for key in row:
            if key.endswith("编号"):
                return key
    return None


def count_tickets(rows: list[dict[str, Any]]) -> int:
    """按核对口径数工单：有编号的按编号去重，没有编号的逐条计数。"""
    field = code_field(rows)
    if field is None:
        return len(rows)
    seen: set[str] = set()
    total = 0
    for row in rows:
        code = str(row.get(field) or "").strip()
        if not code:
            total += 1
            continue
        if code in seen:
            continue
        seen.add(code)
        total += 1
    return total


def recount(store: Any) -> dict[str, int]:
    """按当前规矩把存量数据重算一遍，并把规矩版本盖戳到仓库元信息里。"""
    counts = {name: count_tickets(store.rows(name)) for name in store.module_names()}
    store.meta()["rule_version"] = RULE_VERSION
    store.meta()["ticket_counts"] = counts
    return counts


def verify(store: Any) -> tuple[bool, dict[str, Any]]:
    """核对工单数量：示例数据里的每个工单编号在库里必须恰好出现一次。

    规矩版本对不上时先对存量数据重算一遍再核对；核对不通过时联调不算准备好。
    核对只看示例数据覆盖的工单编号，后来登记的工单不影响就绪状态。
    """
    recounted = False
    if store.meta().get("rule_version") != RULE_VERSION:
        recount(store)
        recounted = True
    problems: dict[str, dict[str, list[str]]] = {}
    checked = 0
    for module, seed_rows in SEED_ROWS.items():
        field = code_field(seed_rows)
        if field is None:
            continue
        tally: dict[str, int] = {}
        for row in store.rows(module):
            code = str(row.get(field) or "").strip()
            if code:
                tally[code] = tally.get(code, 0) + 1
        missing: list[str] = []
        duplicated: list[str] = []
        for seed_row in seed_rows:
            code = str(seed_row.get(field) or "").strip()
            checked += 1
            times = tally.get(code, 0)
            if times == 0:
                missing.append(code)
            elif times > 1:
                duplicated.append(code)
        module_problems: dict[str, list[str]] = {}
        if missing:
            module_problems["missing"] = missing
        if duplicated:
            module_problems["duplicated"] = duplicated
        if module_problems:
            problems[module] = module_problems
    report = {
        "rule_version": RULE_VERSION,
        "recounted": recounted,
        "checked": checked,
        "problems": problems,
    }
    return (not problems, report)
