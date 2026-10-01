"""联调准备固定动作的端到端测试。

覆盖：
1. 起服务前预检：端口、数据库连通，缺步骤时明确报错并返回非零；
2. 固定示例数据导入后自动核对工单数量，核对不通过不算准备好；
3. 重复导入按记录编号幂等，工单不叠成两份；
4. 核对口径版本升级后，存量数据自动重算；
5. 概览页、热线列表页、导出接口读到的是同一份条数。
"""
from __future__ import annotations

import json
import socket


def _prepare(db_module):
    from app import jointdebug
    return jointdebug.prepare(db_module.get_database())


def test_prepare_imports_and_verifies_fixture(db_env):
    db_module, _, db_path = db_env
    assert not db_path.exists() or db_module.get_database() is not None
    report = _prepare(db_module)
    assert report["ready"] is True
    assert report["imported"]["inserted"] == 6
    assert report["verification"]["actual_total"] == 6
    assert report["verification"]["actual_by_status"] == {
        "待转办": 2, "已转办": 2, "处理中": 1, "已办结": 1
    }
    assert db_path.exists()


def test_repeated_import_is_idempotent_by_record_no(db_env):
    db_module, _, _ = db_env
    first = _prepare(db_module)
    second = _prepare(db_module)
    assert first["imported"]["inserted"] == 6
    assert second["imported"]["inserted"] == 0
    assert second["imported"]["updated"] == 6
    assert second["imported"]["total_after"] == 6

    db = db_module.get_database()
    assert db.count_complaint_rows() == 6
    record_nos = [row["record_no"] for row in db.list_complaint_rows()]
    assert len(record_nos) == len(set(record_nos))


def test_create_same_record_no_is_rejected(client):
    dup = client.post(
        "/api/complaint",
        json={"values": {"记录编号": "COMP-JD-001", "来电人": "甲", "来电内容": "重复"}},
    ).json()
    assert dup["ok"] is False
    assert "COMP-JD-001" in dup["message"]
    assert client.get("/api/complaint").json()["total"] == 6


def test_verification_fails_when_count_mismatch(db_env):
    db_module, _, _ = db_env
    _prepare(db_module)
    db = db_module.get_database()
    extra = {"记录编号": "COMP-X-99", "记录状态": "待转办", "status": "待转办",
             "pending": True, "abnormal": False}
    db.upsert_complaint_row("COMP-X-99", "待转办", json.dumps(extra, ensure_ascii=False))

    from app import jointdebug
    report = jointdebug.prepare(db)
    assert report["ready"] is False
    assert any("工单总数 7" in p for p in report["verification"]["problems"])


def test_stale_rule_version_triggers_recompute(db_env):
    db_module, _, _ = db_env
    _prepare(db_module)
    db = db_module.get_database()
    db.set_meta("count_rule_version", "0")  # 存量数据停留在旧口径

    from app import counts, jointdebug
    assert counts.is_stale(db)
    stats = jointdebug.recompute_if_stale(db)
    assert stats is not None
    assert stats["total"] == 6
    assert not counts.is_stale(db)
    assert jointdebug.verify(db).ok is True


def test_overview_list_export_share_one_count(client):
    overview = client.get("/api/overview").json()
    complaint_overview = [m for m in overview["modules"] if m["name"] == "complaint"][0]
    listed = client.get("/api/complaint").json()
    exported = client.get("/api/complaint/export").json()

    assert complaint_overview["created"] == listed["total"] == exported["total"] == 6
    # 列表页卡片的分状态数与总数也来自同一口径
    assert listed["stats"]["total"] == 6
    assert listed["stats"]["by_status"]["已办结"] == 1
    assert complaint_overview["pending"] == listed["stats"]["pending"]


def test_options_come_from_fixed_fixture(client):
    options = client.get("/api/complaint/options").json()["options"]
    assert "绿化修剪" in options["问题类型"]
    assert "绿化养护科" in options["转办部门"]

    filtered = client.get("/api/complaint", params={"issue_type": "设施维修"}).json()
    assert filtered["total"] == 2
    by_dept = client.get("/api/complaint", params={"department": "执法大队"}).json()
    assert by_dept["total"] == 1


def test_cold_start_prepares_fixture_and_reports_ready(fresh_app):
    # 全新库直接起服务：lifespan 会自动幂等导入并核对，健康检查报就绪
    health = fresh_app.get("/api/health").json()
    assert health["ok"] is True
    assert health["database"]["ready"] is True
    assert health["jointdebug"]["ready"] is True
    assert health["jointdebug"]["verification"]["actual_total"] == 6


def test_health_reports_not_ready_when_data_missing(db_env):
    # 库连通但工单被清空（模拟没跑导入）：健康检查必须说未就绪并给出补做动作
    db_module, _, _ = db_env
    db = db_module.get_database()
    db.conn.execute("DELETE FROM complaint_rows")
    db.conn.commit()

    from app import store as store_module

    store_module.store.reload_complaint()

    # 不经过 lifespan（它会自动导入），直接调用健康检查路由函数
    from app.main import health as health_view

    payload = health_view()
    assert payload["ok"] is False
    assert payload["database"]["ready"] is True
    assert payload["jointdebug"]["ready"] is False
    assert "make prepare" in payload["hint"]


def test_preflight_port_conflict_message(db_env, monkeypatch):
    from app import preflight

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            pass

        def settimeout(self, *_):
            pass

        def connect(self, _):
            return None  # 能连上 = 端口被占

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *a, **k: FakeSocket())
    result = preflight.check_port()
    assert result.ok is False
    assert "8000" in result.detail
    assert "APP_PORT" in result.remedy


def test_preflight_database_missing_dir(tmp_path, monkeypatch):
    missing = tmp_path / "nope" / "db.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{missing}")
    from app import preflight as pf

    result = pf.check_database()
    assert result.ok is False
    assert "数据库目录不存在" in result.detail
    assert "mkdir" in result.remedy


def test_action_keeps_overview_and_list_consistent(client):
    assert client.post("/api/complaint/1/actions", json={"values": {"action": "办结归档"}}).json()["ok"]
    overview = client.get("/api/overview").json()
    complaint_overview = [m for m in overview["modules"] if m["name"] == "complaint"][0]
    listed = client.get("/api/complaint").json()
    assert complaint_overview["created"] == listed["total"] == listed["stats"]["total"]
    assert complaint_overview["pending"] == listed["stats"]["pending"]
