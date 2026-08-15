"""P2 授权换码广播机制测试（license_state 状态机 / 数据同步拦截）。

覆盖：
1. 状态机流转：首次激活 → 换码 superseded → 新码回归清除 → 宽限到期
2. 7 天倒计时：宽限内旧码放行 + "授权即将更新"；超期拒绝 + 明确文案
3. 并发写 state 原子性（多线程 → 文件始终合法 JSON）
4. license/info 端点上报 supersede 状态（新码激活检测点）
5. 知识库文档上传拦截（403 + 明确提示文案）
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.utils.license_state import (
    check_sync_allowed,
    get_supersede_status,
    supersede,
    sync_license_state,
)

OLD_KEY = "LIC-OLD-001"
NEW_KEY = "LIC-NEW-002"


# ---------------------------------------------------------------------------
# 1. 状态机流转
# ---------------------------------------------------------------------------


def test_record_active_first_time(tmp_path):
    """首次 sync → active 记录，无替换记录。"""
    state = sync_license_state(OLD_KEY, path=tmp_path / "license_state.json")
    assert state["active_license_key"] == OLD_KEY
    assert state["superseded_by"] is None


def test_supersede_on_key_change(tmp_path):
    """cache 换新码 → 旧码 superseded + grace_ends_at = +7 天。"""
    state_path = tmp_path / "license_state.json"
    sync_license_state(OLD_KEY, path=state_path)
    state = sync_license_state(NEW_KEY, path=state_path)

    assert state["active_license_key"] == OLD_KEY  # 旧码仍是"当前生效"记录主体
    assert state["superseded_by"] == NEW_KEY
    assert state["superseded_at"] is not None
    ends = datetime.fromisoformat(state["grace_ends_at"])
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    diff_days = (ends - datetime.now(timezone.utc)).total_seconds() / 86400
    assert 6.9 <= diff_days <= 7.1  # 7 天倒计时


def test_new_code_regression_clears_supersede(tmp_path):
    """新码回归（sync 到 superseded_by）→ 清除替换记录。"""
    state_path = tmp_path / "license_state.json"
    sync_license_state(OLD_KEY, path=state_path)
    sync_license_state(NEW_KEY, path=state_path)
    state = sync_license_state(NEW_KEY, path=state_path)

    assert state["active_license_key"] == NEW_KEY
    assert state["superseded_by"] is None
    assert state["grace_ends_at"] is None


def test_state_file_structure_and_persistence(tmp_path):
    """license_state.json 落盘结构符合验收字段。"""
    state_path = tmp_path / "license_state.json"
    sync_license_state(OLD_KEY, path=state_path)
    sync_license_state(NEW_KEY, path=state_path)

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    # P3 起格式为 {data, sig}；data 内为 4 个状态字段
    assert set(raw.keys()) == {"data", "sig"}
    assert set(raw["data"].keys()) == {
        "active_license_key", "superseded_by", "superseded_at", "grace_ends_at",
    }


# ---------------------------------------------------------------------------
# 2. 7 天倒计时：宽限内放行 / 超期拒绝
# ---------------------------------------------------------------------------


def _supersede_state(tmp_path, grace_ends_at: str | None = None) -> Path:
    """构造 {active: OLD, superseded_by: NEW, ...} 状态，返回路径。"""
    state_path = tmp_path / "license_state.json"
    state = supersede(OLD_KEY, NEW_KEY, path=state_path)
    if grace_ends_at is not None:
        state["grace_ends_at"] = grace_ends_at
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state_path


def test_grace_window_status(tmp_path):
    """宽限期内：superseded=True, grace_expired=False。"""
    _supersede_state(tmp_path)
    status = get_supersede_status(path=tmp_path / "license_state.json")
    assert status["superseded"] is True
    assert status["superseded_by"] == NEW_KEY
    assert status["grace_expired"] is False
    assert 6 <= status["grace_days_left"] <= 7


def test_grace_expired(tmp_path):
    """超 7 天：grace_expired=True（安全方向：时间格式异常也按失效）。"""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _supersede_state(tmp_path, grace_ends_at=past)
    status = get_supersede_status(path=tmp_path / "license_state.json")
    assert status["grace_expired"] is True


def test_check_sync_allowed_old_key_in_grace(tmp_path):
    """宽限期内旧码同步 → 放行 + 提示"授权即将更新"。"""
    _supersede_state(tmp_path)
    allowed, reason = check_sync_allowed(OLD_KEY, path=tmp_path / "license_state.json")
    assert allowed is True
    assert "授权即将更新" in reason


def test_check_sync_allowed_old_key_expired(tmp_path):
    """超 7 天后旧码同步 → 拒绝 + 明确文案。"""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _supersede_state(tmp_path, grace_ends_at=past)
    allowed, reason = check_sync_allowed(OLD_KEY, path=tmp_path / "license_state.json")
    assert allowed is False
    assert reason == "授权已更新，请联系经销商获取新授权码"


def test_check_sync_allowed_new_key_and_unknown(tmp_path):
    """新码 / 未知码 → 放行（不误伤）。"""
    _supersede_state(tmp_path)
    allowed, _ = check_sync_allowed(NEW_KEY, path=tmp_path / "license_state.json")
    assert allowed is True
    allowed2, _ = check_sync_allowed(
        "LIC-UNKNOWN-999", path=tmp_path / "license_state.json"
    )
    assert allowed2 is True


# ---------------------------------------------------------------------------
# 3. 并发写原子性
# ---------------------------------------------------------------------------


def test_concurrent_writes_atomic(tmp_path):
    """多线程并发写 license_state.json → 文件始终为完整合法 JSON。"""
    state_path = tmp_path / "license_state.json"
    errors: list = []

    def writer(key: str):
        try:
            for _ in range(15):
                sync_license_state(key, path=state_path)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(OLD_KEY,)),
        threading.Thread(target=writer, args=(NEW_KEY,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    # 最终文件可解析且字段完整（P3 格式：{data, sig}）
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"data", "sig"}
    assert set(raw["data"].keys()) == {
        "active_license_key", "superseded_by", "superseded_at", "grace_ends_at",
    }
    assert raw["data"]["active_license_key"] in (OLD_KEY, NEW_KEY)


# ---------------------------------------------------------------------------
# 4. license/info 端点上报 supersede（新码激活检测点）
# ---------------------------------------------------------------------------


def _point_paths(tmp_path, monkeypatch) -> tuple:
    """让 license 模块的 cache/state 路径指向 tmp。"""
    from core.config import Settings

    lic_path = tmp_path / "license_cache.json"
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"cache_path": str(lic_path)}}),
    )
    return lic_path, tmp_path / "license_state.json"


async def test_license_info_reports_supersede(client, tmp_path, monkeypatch):
    """info 端点：新码激活 → supersede 字段上报；超时后 licensed:false。"""
    from core.auth.jwt import create_access_token
    from core.utils.license_validator import validate_license_file as _  # noqa: F401

    lic_path, state_path = _point_paths(tmp_path, monkeypatch)
    # cache 中是旧码（校验不依赖签名：check 只读 key；evaluate 验签失败→licensed:false
    # 也会被 superseded 超时覆盖为 superseded）
    lic_path.write_text(
        json.dumps(
            {"license_key": OLD_KEY, "customer": "换码测试客户"}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _supersede_state(tmp_path, grace_ends_at=past)

    token = create_access_token(user_id=1, tenant_id=1, role="member")
    resp = await client.get(
        "/api/v1/license/info", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["supersede"]["superseded"] is True
    assert data["supersede"]["superseded_by"] == NEW_KEY
    assert data["supersede"]["grace_expired"] is True
    assert data["licensed"] is False  # 超时 → 信息层 fail-closed
    assert data["warning_level"] == "superseded"


# ---------------------------------------------------------------------------
# 5. 知识库文档上传拦截（403 + 明确文案）
# ---------------------------------------------------------------------------


def _build_upload_app(tmp_path, monkeypatch):
    """挂载知识库 router 的 mini app；state 指向 tmp。"""
    from fastapi import FastAPI
    from httpx import ASGITransport

    lic_path, state_path = _point_paths(tmp_path, monkeypatch)
    from plugins.ddw_knowledge_hierarchy.router import router as kh_router

    app = FastAPI()
    app.include_router(kh_router, prefix="/api/v1/plugins/ddw-knowledge-hierarchy")
    return ASGITransport(app=app), lic_path, state_path


async def test_upload_document_blocked_after_grace(tmp_path, monkeypatch):
    """旧码超 7 天倒计时 → 知识库文档上传 403 + 明确文案。"""
    from httpx import AsyncClient

    transport, lic_path, state_path = _build_upload_app(tmp_path, monkeypatch)

    lic_path.write_text(
        json.dumps(
            {"license_key": OLD_KEY, "customer": "克隆容器"}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _supersede_state(tmp_path, grace_ends_at=past)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-knowledge-hierarchy/documents/upload",
            files={"file": ("note.md", b"# test doc\ncontent", "text/markdown")},
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"
    # 宽限内放行路径由 test_check_sync_allowed_old_key_in_grace 单元覆盖


# ---------------------------------------------------------------------------
# 6. 扩展拦截点（P2 后续批次）：ent_knowledge / doc_assistant 上传 403
# ---------------------------------------------------------------------------


def _build_upload_app_generic(tmp_path, monkeypatch, router_module, prefix):
    """挂载任意上传 router 的 mini app；state 指向 tmp。"""
    from fastapi import FastAPI
    from httpx import ASGITransport

    lic_path, state_path = _point_paths(tmp_path, monkeypatch)
    from importlib import import_module

    router = import_module(router_module).router
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    return ASGITransport(app=app), lic_path, state_path


async def _assert_upload_blocked(tmp_path, monkeypatch, router_module, prefix, path):
    from httpx import AsyncClient

    transport, lic_path, state_path = _build_upload_app_generic(
        tmp_path, monkeypatch, router_module, prefix
    )
    lic_path.write_text(
        json.dumps(
            {"license_key": OLD_KEY, "customer": "克隆容器"}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _supersede_state(tmp_path, grace_ends_at=past)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            path,
            files={"file": ("note.md", b"# test doc\ncontent", "text/markdown")},
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"


async def test_ent_knowledge_upload_blocked_after_grace(tmp_path, monkeypatch):
    """企业知识库上传：旧码超期 → 403。"""
    # 注意：ddw_ent_knowledge.router 自带 prefix，include 时不能再加
    await _assert_upload_blocked(
        tmp_path,
        monkeypatch,
        "plugins.ddw_ent_knowledge.router",
        "",
        "/api/v1/plugins/ddw-ent-knowledge/documents/upload",
    )


async def test_doc_assistant_upload_blocked_after_grace(tmp_path, monkeypatch):
    """文档助手上传：旧码超期 → 403。"""
    await _assert_upload_blocked(
        tmp_path,
        monkeypatch,
        "plugins.ddw_doc_assistant.router",
        "/api/v1/plugins/ddw-doc-assistant",
        "/api/v1/plugins/ddw-doc-assistant/documents/upload",
    )
