"""联调准备检查：起服务前按固定顺序过一遍，缺哪一步就打印哪一步。

用法：python -m app.preflight
全部检查通过返回 0；任一步不过返回 1，并列出还缺哪几步，处理完再重新起服务。
"""
from __future__ import annotations

import importlib
import socket
import sys
from collections.abc import Callable

from app.config import settings

Check = Callable[[], tuple[bool, str]]


def check_dependencies() -> tuple[bool, str]:
    """第 1 步：确认后端依赖已经装进当前环境。"""
    missing: list[str] = []
    for package in ("fastapi", "uvicorn", "pydantic"):
        try:
            importlib.import_module(package)
        except ImportError:
            missing.append(package)
    if missing:
        return False, f"缺少依赖：{'、'.join(missing)}，请先执行 pip install -r requirements.txt"
    return True, "fastapi / uvicorn / pydantic 均已安装"


def check_port() -> tuple[bool, str]:
    """第 2 步：确认服务端口空闲，能绑得上才算能起。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", settings.port))
        except OSError:
            return False, f"端口 {settings.port} 被占用，请先停掉占用进程或在 app/config.py 调整端口"
    return True, f"端口 {settings.port} 空闲"


def check_database() -> tuple[bool, str]:
    """第 3 步：确认数据层连通（真实项目里换成数据库 ping）。"""
    from app.store import store

    if not store.ping():
        return False, "数据层自检未通过，请检查数据仓库初始化"
    return True, f"数据层连通，{len(store.module_names())} 个业务模块表可读写"


def check_seed() -> tuple[bool, str]:
    """第 4 步：导入后自动核对工单数量，核对不通过就不算准备好。"""
    from app import reconcile
    from app.store import store

    ok, report = reconcile.verify(store)
    if not ok:
        return False, f"工单数量核对未通过：{report['problems']}，请执行 python -m app.seed_import 重新导入"
    suffix = "，已对存量数据重算" if report["recounted"] else ""
    return True, f"示例数据核对通过（核对规矩 v{report['rule_version']}，共核对 {report['checked']} 个工单编号{suffix}）"


CHECKS: list[tuple[str, Check]] = [
    ("依赖检查", check_dependencies),
    ("端口检查", check_port),
    ("数据库连通", check_database),
    ("示例数据核对", check_seed),
]


def main() -> int:
    print("联调准备检查开始……")
    failures: list[str] = []
    for index, (name, check) in enumerate(CHECKS, start=1):
        try:
            ok, detail = check()
        except Exception as error:  # 检查本身出错也算这一步没过
            ok, detail = False, f"检查执行出错：{error}"
        mark = "✓" if ok else "✗"
        print(f"[{index}/{len(CHECKS)}] {mark} {name}：{detail}")
        if not ok:
            failures.append(name)
    if failures:
        print(f"联调准备未就绪，还缺：{'、'.join(failures)}。补齐后重新起服务。")
        return 1
    print("联调准备就绪，可以起服务。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
