"""测试夹具：每个用例使用独立的临时 SQLite 文件库。

数据库目标在连接时从 DATABASE_URL 现读（见 app.config.resolve_database_url），
因此只需在初始化前设置环境变量，不用热重载业务模块。需要冷启动 lifespan 的
用例通过 fresh_main 拿一个全新构建的 FastAPI 实例，避免单例串扰。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    db_path = tmp_path / "jointdebug.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")

    from app import db as db_module  # noqa: PLC0415
    from app import store as store_module  # noqa: PLC0415

    db_module._db = None
    db_module._db_error = None
    db_module.init_database(force=True)
    store_module.store.reload_complaint()

    import app.main as main_module  # noqa: PLC0415

    yield db_module, main_module, db_path


@pytest.fixture()
def client(db_env):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    _, main_module, _ = db_env
    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture()
def fresh_app(tmp_path, monkeypatch):
    """全新库文件 + 全新应用实例：lifespan 冷启动一次，导入核对都在启动时完成。"""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    db_path = tmp_path / "cold-jointdebug.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")

    from app import db as db_module  # noqa: PLC0415

    db_module._db = None
    db_module._db_error = None
    sys.modules.pop("app.main", None)
    import app.main as main_module  # noqa: PLC0415

    with TestClient(main_module.app) as test_client:
        yield test_client
