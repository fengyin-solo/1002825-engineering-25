"""起服务前的固定预检动作：先查端口占用，再查数据库连通。

任一步不过都打印「缺了哪一步」的中文指引并以非零码退出：
    python -m app.cli preflight
"""
from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

from app.config import BACKEND_DIR, settings
from app.db import DatabaseUnavailable


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    remedy: str = ""

    def line(self) -> str:
        if self.ok:
            return f"[PASS] {self.name}：{self.detail}"
        tip = f"，处理办法：{self.remedy}" if self.remedy else ""
        return f"[FAIL] {self.name}：{self.detail}{tip}"


def check_port(host: str = settings.host, port: int = settings.port) -> CheckResult:
    """起服务前确认端口空闲；已被占用时给出换端口或停占用进程的指引。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((host, port))
    except OSError:
        return CheckResult("端口检查", True, f"{host}:{port} 空闲，可以起服务")
    else:
        return CheckResult(
            "端口检查",
            False,
            f"{host}:{port} 已被占用，后端起不来页面只能看空表",
            f"停掉占用 {port} 端口的进程（lsof -i :{port}），或用 APP_PORT 换端口后重启",
        )
    finally:
        sock.close()


def check_database() -> CheckResult:
    """数据库连通检查：连不上时说明缺了建目录/可写权限哪一步。"""
    try:
        # 预检必须按当前配置新建连接，不能复用全局单例（配置可能刚改过）；
        # 只做连通性往返，不建表、不建文件，保持「检查」只读。
        from app.db import Database

        probe = Database(init_schema=False)
        path = str(probe.path) if probe.path is not None else ":memory:"
        probe.close()
    except DatabaseUnavailable as exc:
        message = str(exc)
        if "数据库目录不存在" in message:
            remedy = f"先执行 mkdir -p {BACKEND_DIR / 'data'}（或直接运行 make prepare 自动建目录），确认 DATABASE_URL 指向可写路径"
        else:
            remedy = "检查 DATABASE_URL 是否指向可写路径，或直接运行 make prepare 完成联调准备"
        return CheckResult("数据库连通", False, message, remedy)
    except Exception as exc:  # pragma: no cover - 兜底，保证报错可读
        return CheckResult(
            "数据库连通",
            False,
            f"数据库连通失败：{exc}",
            "检查 DATABASE_URL 配置后重新运行 make prepare",
        )
    return CheckResult("数据库连通", True, f"已连通 {path}，读写正常")


def run_preflight(*, check_port_occupied: bool = True) -> tuple[bool, list[CheckResult]]:
    results: list[CheckResult] = []
    if check_port_occupied:
        results.append(check_port())
    results.append(check_database())
    return all(item.ok for item in results), results


def format_report(results: list[CheckResult]) -> str:
    return "\n".join(item.line() for item in results)


def readiness_dict(results: list[CheckResult]) -> list[dict[str, Any]]:
    return [
        {"name": item.name, "ok": item.ok, "detail": item.detail, "remedy": item.remedy}
        for item in results
    ]
