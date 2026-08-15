"""P1 授权合规增强测试（license/info、宽限期、插件包签名、发证端点权限）。

覆盖：
1. GET /api/v1/license/info 各状态（无 license / 有效 / 宽限期 / 超宽限 / 提前警告）
2. 水印数据（customer/valid_to/days_left/warning_level）
3. .ddwplugin 插件包验签通过 / 篡改失败 / 缺签名拒绝
4. POST /api/v1/admin/license/generate-file
   （superadmin 200 / 非 superadmin 403 / 未配置私钥 400）
"""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient

from core.database.models import OnPremiseCustomer, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from core.utils.license_validator import validate_license_file

VALID_MACHINE_FP = "a" * 32


# ---------------------------------------------------------------------------
# 测试工具
# ---------------------------------------------------------------------------


def _make_keypair() -> tuple:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(priv.public_key().public_bytes_raw()).decode()
    return priv, pub_b64


def _sign_payload(priv, payload: dict) -> str:
    sign_data = {k: v for k, v in payload.items() if k != "signature"}
    message = json.dumps(sign_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(priv.sign(message)).decode()


def _build_license(
    priv, *, valid_to: str = "", machine_fp: str = VALID_MACHINE_FP
) -> dict:
    today = date.today()
    payload = {
        "license_key": "LIC-P1-001",
        "customer": "锐果合规测试公司",
        "instance_id": "p1-instance",
        "machine_fingerprint": machine_fp,
        "valid_from": today.isoformat(),
        "valid_to": valid_to or (today + timedelta(days=365)).isoformat(),
        "authorized_plugins": ["ddw-license-core"],
        "issued_by": "DDW-Admin",
        "issued_at": today.isoformat(),
        "license_format_version": 2,
        "sig_algo": "ed25519",
    }
    payload["signature"] = _sign_payload(priv, payload)
    return payload


def _point_cache_path(tmp_path: Path, monkeypatch) -> Path:
    """让 evaluate_license/load_plugins 默认读到 tmp 下的 license 缓存路径。"""
    from core.config import Settings

    lic_path = tmp_path / "license_cache.json"
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"cache_path": str(lic_path)}}),
    )
    return lic_path


@pytest.fixture
def _license_env(monkeypatch):
    """默认：本机指纹=测试值；license 公钥走环境变量。"""
    import core.utils.license_validator as lv

    monkeypatch.setattr(lv, "get_machine_fingerprint", lambda: VALID_MACHINE_FP)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token(role: str = "superadmin") -> str:
    from core.auth.jwt import create_access_token

    return create_access_token(user_id=1, tenant_id=1, role=role)


async def _ensure_customer(
    client: AsyncClient, company: str = "锐果合规测试公司"
) -> int:
    """建一个 onpremise 客户（幂等），返回 customer_id。"""
    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select

        u = (
            await session.execute(
                sa_select(User).where(User.phone == "13900009991")
            )
        ).scalar_one_or_none()
        if u is None:
            u = User(
                phone="13900009991",
                email="p1@9cio.com",
                name="P1客户",
                role="superadmin",
                user_type="saas",
                tenant_id=1,
            )
            session.add(u)
            await session.flush()
        cust = (await session.execute(
            sa_select(OnPremiseCustomer).where(OnPremiseCustomer.user_id == u.id)
        )).scalar_one_or_none()
        if cust is None:
            cust = OnPremiseCustomer(user_id=u.id, company_name=company)
            session.add(cust)
            await session.flush()
        await session.commit()
        return cust.id


# ---------------------------------------------------------------------------
# 1. GET /api/v1/license/info 各状态
# ---------------------------------------------------------------------------


async def test_license_info_no_license(client, tmp_path, monkeypatch):
    """无 license 文件 → licensed:false。"""
    _point_cache_path(tmp_path, monkeypatch)
    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["licensed"] is False
    assert data["warning_level"] == "invalid"
    assert data["days_left"] is None


async def test_license_info_valid(client, tmp_path, monkeypatch, _license_env):
    """有效 license → 全字段正确。"""
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    lic_path = _point_cache_path(tmp_path, monkeypatch)
    lic_path.write_text(
        json.dumps(_build_license(priv), ensure_ascii=False), encoding="utf-8"
    )

    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["licensed"] is True
    assert data["customer"] == "锐果合规测试公司"
    assert data["license_code"] == "LIC-P1-001"
    assert data["valid_to"] == (date.today() + timedelta(days=365)).isoformat()
    assert data["days_left"] == 365
    assert data["in_grace_period"] is False
    assert data["warning_level"] == "none"


async def test_license_info_grace_period(client, tmp_path, monkeypatch, _license_env):
    """过期 10 天（宽限期内）→ licensed:true + in_grace + grace 警告。"""
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    lic_path = _point_cache_path(tmp_path, monkeypatch)
    valid_to = (date.today() - timedelta(days=10)).isoformat()
    lic_path.write_text(
        json.dumps(_build_license(priv, valid_to=valid_to), ensure_ascii=False),
        encoding="utf-8",
    )

    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["licensed"] is True  # 宽限期内可用
    assert data["in_grace_period"] is True
    assert data["warning_level"] == "grace"
    assert data["days_left"] == -10


async def test_license_info_past_grace(client, tmp_path, monkeypatch, _license_env):
    """过期 40 天（超过 30 天宽限）→ licensed:false。"""
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    lic_path = _point_cache_path(tmp_path, monkeypatch)
    valid_to = (date.today() - timedelta(days=40)).isoformat()
    lic_path.write_text(
        json.dumps(_build_license(priv, valid_to=valid_to), ensure_ascii=False),
        encoding="utf-8",
    )

    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    data = resp.json()["data"]
    assert data["licensed"] is False
    assert data["in_grace_period"] is False


async def test_license_info_soon_warning(client, tmp_path, monkeypatch, _license_env):
    """剩余 15 天 → warning_level=soon（水印黄色预警数据）。"""
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    lic_path = _point_cache_path(tmp_path, monkeypatch)
    valid_to = (date.today() + timedelta(days=15)).isoformat()
    lic_path.write_text(
        json.dumps(_build_license(priv, valid_to=valid_to), ensure_ascii=False),
        encoding="utf-8",
    )

    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    data = resp.json()["data"]
    assert data["licensed"] is True
    assert data["warning_level"] == "soon"
    assert data["days_left"] == 15


async def test_license_info_fingerprint_mismatch(client, tmp_path, monkeypatch):
    """机器指纹不匹配 → 信息端点 licensed:false（不泄露授权）。"""
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    lic_path = _point_cache_path(tmp_path, monkeypatch)
    lic_path.write_text(
        json.dumps(_build_license(priv, machine_fp="b" * 32), ensure_ascii=False),
        encoding="utf-8",
    )

    resp = await client.get("/api/v1/license/info", headers=_auth(_token("member")))
    data = resp.json()["data"]
    assert data["licensed"] is False


# ---------------------------------------------------------------------------
# 2. .ddwplugin 插件包签名与安装验签
# ---------------------------------------------------------------------------


def _make_plugin_dir(tmp_path: Path, name: str = "ddw_p1_demo") -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.yaml").write_text(
        f"name: {name}\nlicense: commercial\nversion: 1.0.0\nconfig: {{}}\n",
        encoding="utf-8",
    )
    (d / "plugin.py").write_text(
        "class Plugin:\n    def __init__(self, app, config=None, manifest=None):\n"
        "        self.app = app\n",
        encoding="utf-8",
    )
    return d


def test_package_sign_and_install_ok(tmp_path, monkeypatch):
    """打包+验签+安装全链路通过。"""
    from core.plugin_manager import installer
    from core.plugin_manager.manager import PluginManager

    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", pub_b64)

    src = _make_plugin_dir(tmp_path)
    pkg = installer.sign_package(src, priv, tmp_path / "ddw_p1_demo.ddwplugin")
    assert pkg.exists()

    name = installer.verify_package(pkg)
    assert name == "ddw_p1_demo"

    pm = PluginManager(plugins_root=tmp_path / "plugs")
    installed = installer.install_from_package(pkg, pm=pm)
    assert installed == "ddw_p1_demo"
    assert (tmp_path / "plugs" / "ddw_p1_demo" / "manifest.yaml").exists()
    # 签名文件不落盘到插件目录
    sig_in_dst = tmp_path / "plugs" / "ddw_p1_demo" / installer.SIGNATURE_FILE_NAME
    assert not sig_in_dst.exists()


def test_package_tampered_rejected(tmp_path, monkeypatch):
    """篡改包内文件（plugin.py）→ 验签失败，拒绝安装。"""
    import zipfile

    from core.plugin_manager import installer

    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", pub_b64)

    src = _make_plugin_dir(tmp_path)
    pkg = installer.sign_package(src, priv, tmp_path / "ddw_p1_demo.ddwplugin")

    # 篡改：改包内 plugin.py 内容
    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr("plugin.py", "class Plugin:\n    pass  # tampered\n")

    with pytest.raises(ValueError) as exc:
        installer.verify_package(pkg)
    assert "签名验证失败" in str(exc.value)


def test_package_missing_signature_rejected(tmp_path, monkeypatch):
    """无签名文件的包 → 明确报错拒绝。"""
    import zipfile

    from core.plugin_manager import installer

    monkeypatch.setenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", "x" * 32)
    src = _make_plugin_dir(tmp_path)
    pkg = tmp_path / "unsigned.ddwplugin"
    with zipfile.ZipFile(pkg, "w") as zf:
        for f in src.iterdir():
            zf.write(f, f.name)

    with pytest.raises(ValueError) as exc:
        installer.verify_package(pkg)
    assert "缺少签名文件" in str(exc.value)


def test_package_missing_public_key_rejected(tmp_path, monkeypatch):
    """安装端未配置公钥 → 明确报错拒绝（防误装未验签包）。"""
    from core.plugin_manager import installer

    monkeypatch.delenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", raising=False)
    priv, _ = _make_keypair()
    src = _make_plugin_dir(tmp_path)
    pkg = installer.sign_package(src, priv, tmp_path / "ddw_p1_demo.ddwplugin")

    with pytest.raises(ValueError) as exc:
        installer.verify_package(pkg)
    assert "未配置 DDW_PLUGIN_SIGNING_PUBLIC_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. POST /api/v1/admin/license/generate-file
# ---------------------------------------------------------------------------


async def test_generate_file_superadmin_ok(client, tmp_path, monkeypatch, _license_env):
    """superadmin 调用 → 200，base64 解出的 license 可被客户端验签通过。"""
    from cryptography.hazmat.primitives import serialization

    priv, pub_b64 = _make_keypair()
    priv_pem = tmp_path / "signing_private.pem"
    priv_pem.write_bytes(
        priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("DDW_LICENSE_PRIVATE_KEY_PATH", str(priv_pem))
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)

    customer_id = await _ensure_customer(client)
    resp = await client.post(
        "/api/v1/admin/license/generate-file",
        json={
            "customer_id": customer_id,
            "instance_id": "p1-issue-instance",
            "machine_fingerprint": VALID_MACHINE_FP,
            "valid_days": 90,
            "authorized_plugins": ["ddw-license-core", "ddw-instance-binding"],
        },
        headers=_auth(_token("superadmin")),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer"] == "锐果合规测试公司"

    content = base64.b64decode(body["license_file_base64"]).decode("utf-8")
    payload = json.loads(content)
    assert payload["sig_algo"] == "ed25519"
    assert payload["machine_fingerprint"] == VALID_MACHINE_FP
    assert payload["authorized_plugins"] == ["ddw-license-core", "ddw-instance-binding"]

    # 客户端侧验签闭环
    lic_path = tmp_path / "issued.json"
    lic_path.write_text(content, encoding="utf-8")
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert is_valid, reason


async def test_generate_file_forbidden_for_non_superadmin(
    client, tmp_path, monkeypatch
):
    """owner 通过 current_admin 但非 superadmin → 403 "仅超级管理员"；member → 403。"""
    monkeypatch.setenv("DDW_LICENSE_PRIVATE_KEY_PATH", str(tmp_path / "x.pem"))

    resp = await client.post(
        "/api/v1/admin/license/generate-file",
        json={
            "customer_id": 1,
            "instance_id": "x",
            "machine_fingerprint": VALID_MACHINE_FP,
            "valid_days": 30,
        },
        headers=_auth(_token("owner")),
    )
    assert resp.status_code == 403, resp.text
    assert "仅超级管理员" in resp.json()["detail"]

    resp_member = await client.post(
        "/api/v1/admin/license/generate-file",
        json={
            "customer_id": 1,
            "instance_id": "x",
            "machine_fingerprint": VALID_MACHINE_FP,
            "valid_days": 30,
        },
        headers=_auth(_token("member")),
    )
    assert resp_member.status_code == 403
    detail = resp_member.json()["detail"]
    assert detail in ("admin role required", "仅超级管理员可签发许可证文件")


async def test_generate_file_requires_private_key_env(client, tmp_path, monkeypatch):
    """未配置 DDW_LICENSE_PRIVATE_KEY_PATH → 400 明确错误。"""
    monkeypatch.delenv("DDW_LICENSE_PRIVATE_KEY_PATH", raising=False)
    customer_id = await _ensure_customer(client)
    resp = await client.post(
        "/api/v1/admin/license/generate-file",
        json={
            "customer_id": customer_id,
            "instance_id": "x",
            "machine_fingerprint": VALID_MACHINE_FP,
            "valid_days": 30,
        },
        headers=_auth(_token("superadmin")),
    )
    assert resp.status_code == 400, resp.text
    assert "DDW_LICENSE_PRIVATE_KEY_PATH" in resp.json()["detail"]
