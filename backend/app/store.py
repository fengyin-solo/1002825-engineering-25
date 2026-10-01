"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

市民热线（complaint）比较特殊：联调时它落 SQLite（见 app.db），导入、核对、
概览与列表都从同一份数据读，避免「概览页一个数、热线列表另一个数」。
其余模块仍是内存示例数据。
真实项目里这里会全部换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

COMPLAINT_MODULE = "complaint"


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # complaint 的权威数据在 SQLite；DB 不可用时回退到 seed，保证服务还能起。
        self._complaint_rows: list[dict[str, Any]] | None = None
        self._complaint_fallback = True
        self.reload_complaint()

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def reload_complaint(self) -> bool:
        """从 SQLite 重新加载热线工单；返回是否成功用上了数据库这份数据。"""
        try:
            from app import jointdebug
            from app.db import get_database

            db = get_database()
            if db is None:
                self._complaint_rows = None
                self._complaint_fallback = True
                return False
            self._complaint_rows = jointdebug.load_rows(db)
            self._complaint_fallback = False
            return True
        except Exception:
            # 任何异常都回退，不能因为联调数据让整个服务起不来。
            self._complaint_rows = None
            self._complaint_fallback = True
            return False

    def complaint_uses_database(self) -> bool:
        return not self._complaint_fallback

    def rows(self, module: str) -> list[dict[str, Any]]:
        if module == COMPLAINT_MODULE and self._complaint_rows is not None:
            return self._complaint_rows
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            if name == COMPLAINT_MODULE:
                # 概览页的工单数量走统一核对口径，和热线列表、导入核对同一份。
                from app import counts

                stats = counts.count_rows(rows)
                modules.append({
                    "name": name,
                    "created": stats["total"],
                    "pending": stats["pending"],
                    "abnormal": stats["abnormal"],
                })
            else:
                modules.append({
                    "name": name,
                    "created": len(rows),
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
