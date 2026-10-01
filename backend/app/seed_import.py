"""示例数据导入动作：幂等入库 + 导入后自动核对工单数量。

用法：python -m app.seed_import
可以重复执行：同一工单编号再次入库只算一次，不会把工单叠成两份。
核对不通过时退出码为 1，联调准备不算完成。
"""
from __future__ import annotations

import sys

from app import reconcile
from app.seed import SEED_ROWS
from app.store import store


def import_seed() -> dict[str, dict[str, int]]:
    """把固定的示例数据按工单编号幂等导入，返回每个模块的导入结果。"""
    report: dict[str, dict[str, int]] = {}
    for module, rows in SEED_ROWS.items():
        inserted, skipped = store.upsert_rows(module, rows)
        report[module] = {"inserted": inserted, "skipped": skipped}
    return report


def main() -> int:
    report = import_seed()
    inserted = sum(item["inserted"] for item in report.values())
    skipped = sum(item["skipped"] for item in report.values())
    print(f"示例数据导入完成：新增 {inserted} 条，跳过重复 {skipped} 条。")
    reconcile.recount(store)
    ok, verify_report = reconcile.verify(store)
    if not ok:
        print(f"工单数量核对未通过：{verify_report['problems']}")
        return 1
    print(f"工单数量核对通过（核对规矩 v{verify_report['rule_version']}），联调准备就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
