"""联调准备命令行入口：预检、导入核对、重算存量、查看准备状态。

用法（在 backend/ 目录下）：
    .venv/bin/python -m app.cli preflight   # 起服务前：查端口 + 数据库连通
    .venv/bin/python -m app.cli prepare     # 固定动作：预检→导入示例→核对工单数量
    .venv/bin/python -m app.cli recompute   # 核对口径变更后重算存量数据
    .venv/bin/python -m app.cli status      # 只查看当前是否准备好
"""
from __future__ import annotations

import json
import sys

from app import jointdebug, preflight
from app.config import resolve_sqlite_target, settings
from app.db import Database, DatabaseUnavailable, _resolve_db_path


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _ensure_database_dir() -> str | None:
    """prepare 固定动作的一部分：自动建好数据库目录；建不了时返回原因。"""
    path = _resolve_db_path(resolve_sqlite_target())
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"数据库目录 {path.parent} 无法创建：{exc}（请检查目录权限后重试）"
    return None


def _open_database() -> Database | None:
    try:
        return Database()
    except DatabaseUnavailable as exc:
        print(f"[FAIL] 数据库连通：{exc}")
        print("       缺这一步时先运行：make prepare（会自动建库目录并导入示例数据）")
        return None


def cmd_preflight() -> int:
    ok, results = preflight.run_preflight()
    print(preflight.format_report(results))
    if ok:
        print("[READY] 预检通过，可以起后端：./run.sh（或 make backend）")
    else:
        print("[BLOCKED] 预检未通过，按上面的处理办法补齐后再起服务，别让前端对着空表联调")
    return 0 if ok else 1


def cmd_prepare() -> int:
    # prepare 是固定动作的总入口：端口占用必须先解决；数据库目录由这一步自动补齐，
    # 其余连通问题（不可写等）仍按预检失败处理，打印缺了哪一步。
    port_result = preflight.check_port()
    print(port_result.line())
    if not port_result.ok:
        print("[BLOCKED] 端口未就绪，已停止导入；按处理办法释放端口后重新运行 make prepare")
        return 1

    dir_error = _ensure_database_dir()
    if dir_error:
        print(f"[FAIL] 数据库连通：{dir_error}")
        return 1

    db_result = preflight.check_database()
    print(db_result.line())
    if not db_result.ok:
        print("[BLOCKED] 预检未通过，已停止导入；按处理办法补齐后重新运行 make prepare")
        return 1

    db = _open_database()
    if db is None:
        return 1
    report = jointdebug.prepare(db)
    imported = report["imported"]
    print(
        f"[IMPORT] 固定示例工单：新增 {imported['inserted']} 条，"
        f"已存在更新 {imported['updated']} 条，当前共 {imported['total_after']} 条"
        f"（同一记录编号重复导入不叠加）"
    )
    if report["recomputed"]:
        print(f"[RECOUNT] 核对口径变更，存量工单已按 v{report['verification']['rule_version']} 重算")
    verification = report["verification"]
    if verification["ok"]:
        print(
            f"[VERIFY] 核对通过：工单总数 {verification['actual_total']} 条，"
            f"分状态 {verification['actual_by_status']}，与固定示例数据一致"
        )
        print("[READY] 联调准备完成，可以起后端联调")
        return 0
    for problem in verification["problems"]:
        print(f"[FAIL] 核对不通过：{problem}")
    print("[BLOCKED] 核对不通过，不算准备好；修正示例数据后重新运行 make prepare")
    return 1


def cmd_recompute() -> int:
    db = _open_database()
    if db is None:
        return 1
    stats = jointdebug.recompute(db)
    print(
        f"[RECOUNT] 已按口径 v{stats['rule_version']}（{stats['rule_desc']}）重算存量工单："
        f"总数 {stats['total']}，分状态 {stats['by_status']}"
    )
    verification = jointdebug.verify(db)
    if verification.ok:
        print("[VERIFY] 重算后核对通过")
        return 0
    for problem in verification.problems:
        print(f"[FAIL] 核对不通过：{problem}")
    return 1


def cmd_status() -> int:
    db = _open_database()
    if db is None:
        return 1
    report = jointdebug.readiness(db)
    _print_json(report)
    return 0 if report["ready"] else 1


COMMANDS = {
    "preflight": cmd_preflight,
    "prepare": cmd_prepare,
    "recompute": cmd_recompute,
    "status": cmd_status,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"用法：python -m app.cli {{{' | '.join(COMMANDS)}}}（当前 APP_PORT={settings.port}）")
        return 2
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
