"""SQLite 数据访问层：联调工单的唯一落库位置。

预检脚本、导入流程和 FastAPI 服务都通过这里连库：
- 连不上（目录缺失、路径不可写）会抛 DatabaseUnavailable，并带一句排障指引；
- 工单按「记录编号」唯一，重复导入走 UPSERT，不会叠成两份。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from app.config import BACKEND_DIR, resolve_sqlite_target

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS complaint_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS count_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class DatabaseUnavailable(RuntimeError):
    """数据库连不上时抛出，message 里直接写清缺了哪一步。"""


def _resolve_db_path(target: str) -> Path | None:
    if target == ":memory:":
        return None
    path = Path(target)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


class Database:
    """薄封装 sqlite3 连接；线程锁保证 uvicorn 多线程下的串行写入。"""

    def __init__(self, target: str | None = None, *, init_schema: bool = True) -> None:
        self.target = resolve_sqlite_target(target)
        self.path = _resolve_db_path(self.target)
        self._lock = threading.Lock()
        self.conn = self._connect()
        if init_schema:
            self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.path is not None:
            parent = self.path.parent
            if not parent.exists():
                raise DatabaseUnavailable(
                    f"数据库目录不存在：{parent}，请先执行 mkdir -p {parent}"
                    f"（或运行 make prepare 自动创建）后再起服务"
                )
        try:
            conn = sqlite3.connect(self.target, check_same_thread=False, timeout=5)
            conn.row_factory = sqlite3.Row
            # 先做一次往返，权限不足等问题在预检阶段就暴露。
            conn.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            hint = "（文件库）请确认数据库文件可写、目录存在；" if self.path else "（内存库）"
            raise DatabaseUnavailable(f"数据库连通失败：{exc}。{hint}缺这一步时先运行 make prepare") from exc
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA_SQL)
            self.conn.commit()

    # ---- 工单读写 ------------------------------------------------------

    def list_complaint_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, record_no, status, payload FROM complaint_rows ORDER BY id"
            )
            return [
                {"id": row["id"], "record_no": row["record_no"], "status": row["status"], "payload": row["payload"]}
                for row in cur.fetchall()
            ]

    def get_complaint_row(self, entry_id: int) -> dict[str, Any] | None:
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, record_no, status, payload FROM complaint_rows WHERE id = ?",
                (entry_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {"id": row["id"], "record_no": row["record_no"], "status": row["status"], "payload": row["payload"]}

    def get_complaint_row_by_no(self, record_no: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, record_no, status, payload FROM complaint_rows WHERE record_no = ?",
                (record_no,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {"id": row["id"], "record_no": row["record_no"], "status": row["status"], "payload": row["payload"]}

    def upsert_complaint_row(self, record_no: str, status: str, payload_json: str) -> tuple[int, bool]:
        """按记录编号插入或更新；返回 (id, inserted)，重复编号只算一条。"""
        with self._lock:
            cur = self.conn.execute(
                "SELECT id FROM complaint_rows WHERE record_no = ?", (record_no,)
            )
            existing = cur.fetchone()
            if existing is not None:
                self.conn.execute(
                    "UPDATE complaint_rows SET status = ?, payload = ? WHERE id = ?",
                    (status, payload_json, existing["id"]),
                )
                self.conn.commit()
                return int(existing["id"]), False
            cur = self.conn.execute(
                "INSERT INTO complaint_rows (record_no, status, payload) VALUES (?, ?, ?)",
                (record_no, status, payload_json),
            )
            self.conn.commit()
            return int(cur.lastrowid), True

    def update_complaint_status(self, entry_id: int, status: str, payload_json: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE complaint_rows SET status = ?, payload = ? WHERE id = ?",
                (status, payload_json, entry_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def count_complaint_rows(self) -> int:
        with self._lock:
            cur = self.conn.execute("SELECT COUNT(*) FROM complaint_rows")
            return int(cur.fetchone()[0])

    # ---- 核对口径元数据 ------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            cur = self.conn.execute("SELECT value FROM count_meta WHERE key = ?", (key,))
            row = cur.fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO count_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()


_db: Database | None = None
_db_error: DatabaseUnavailable | None = None
_init_lock = threading.Lock()


def init_database(force: bool = False) -> Database:
    """初始化全局数据库连接；失败时记住错误，后续 readiness 能说明缺哪一步。"""
    global _db, _db_error
    with _init_lock:
        if _db is not None and not force:
            return _db
        try:
            _db = Database()
            _db_error = None
        except DatabaseUnavailable as exc:
            _db = None
            _db_error = exc
            raise
        return _db


def get_database() -> Database | None:
    return _db


def get_database_error() -> DatabaseUnavailable | None:
    return _db_error


def ping(target: str | None = None) -> dict[str, Any]:
    """供预检脚本调用：只做一次连接往返，不改动任何业务数据。"""
    db = Database(target=target) if target is not None else init_database()
    rows: Iterable[sqlite3.Row] = db.conn.execute("SELECT 1 AS ok").fetchall()
    ok_row = list(rows)[0]
    return {"ok": int(ok_row["ok"]) == 1, "target": db.target, "path": str(db.path) if db.path else ":memory:"}
