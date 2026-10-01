"""运行配置：端口、跨域、运行环境与数据库连接。

配置全部可通过环境变量覆盖，命令行预检脚本与服务进程读的是同一份配置，
避免「脚本能过、服务连不上」这种口径不一致。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value is not None and value.strip() else default


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "jointdebug.sqlite3"


def _default_database_url() -> str:
    # 相对路径统一锚定到 backend/ 目录，不论从哪个工作目录启动。
    return str(DEFAULT_DB_PATH)


@dataclass(frozen=True)
class Settings:
    app_name: str = "园林绿化养护管理平台"
    env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    # 联调用 SQLite 做数据库连通检查；sqlite:// 表示纯内存库，
    # 其余形如 sqlite:////abs/path.db 或 sqlite:///rel.db 的指向文件库。
    database_url: str = field(default_factory=_default_database_url)
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200


settings = Settings(
    env=_env("APP_ENV", "local"),
    host=_env("APP_HOST", "127.0.0.1"),
    port=int(_env("APP_PORT", "8000")),
    database_url=_env("DATABASE_URL", _default_database_url()),
)


def resolve_database_url() -> str:
    """每次连接时读取环境变量，便于在不重启进程的情况下切换目标库（测试用）。"""
    return _env("DATABASE_URL", _default_database_url())


def resolve_sqlite_target(url: str | None = None) -> str:
    """把数据库 URL 归一化成 sqlite3.connect 能用的目标串。

    - sqlite:// 或 sqlite://:memory:：内存库
    - sqlite:////abs/path.db（四个斜杠）：绝对路径文件库
    - sqlite:///rel/path.db（三个斜杠）：相对 backend/ 的文件库
    - 也支持直接写文件路径
    """
    url = url if url is not None else resolve_database_url()
    if url in ("sqlite://", "sqlite://:memory:"):
        return ":memory:"
    if url.startswith("sqlite:////"):
        return "/" + url[len("sqlite:////"):]
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    return url
