"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app import reconcile
from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {name: [] for name in SEED_ROWS}
        self._meta: dict[str, Any] = {}
        # 示例数据走幂等导入进仓：同一工单编号再次入库只算一次，重复导入不会叠成两份。
        for name, rows in SEED_ROWS.items():
            self.upsert_rows(name, rows)
        # 起服务时按当前核对规矩把存量数据重算一遍并盖戳。
        reconcile.recount(self)

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def meta(self) -> dict[str, Any]:
        """仓库元信息：核对规矩版本与重算结果都放在这里。"""
        return self._meta

    def ping(self) -> bool:
        """数据层连通性自检：真实项目里换成数据库 ping，这里确认各模块表可读写。"""
        return all(isinstance(self._tables.get(name), list) for name in SEED_ROWS)

    def upsert_rows(self, module: str, rows: list[dict[str, Any]]) -> tuple[int, int]:
        """按工单编号幂等入库：同一编号再次入库只算一次，返回（新增条数, 跳过条数）。"""
        table = self.rows(module)
        field = reconcile.code_field(table) or reconcile.code_field(rows)
        inserted = 0
        skipped = 0
        for row in rows:
            code = str(row.get(field, "") or "").strip() if field else ""
            if code and any(str(existing.get(field, "") or "").strip() == code for existing in table):
                skipped += 1
                continue
            entry = dict(row)
            existing_ids = {int(item.get("id", 0)) for item in table}
            if not entry.get("id") or int(entry["id"]) in existing_ids:
                entry["id"] = max(existing_ids, default=0) + 1
            table.append(entry)
            inserted += 1
        return inserted, skipped

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                # 工单数量与核对规矩用同一份口径，概览页与各模块页读到的条数才一致。
                "created": reconcile.count_tickets(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
