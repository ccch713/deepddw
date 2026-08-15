"""Plugin installer（P1：支持 .ddwplugin 签名包安装）。

- ``install_from_directory``：目录安装（Phase 1 原有）
- ``sign_package`` / ``verify_package`` / ``install_from_package``：
  ``.ddwplugin`` 包（zip）签名与安装验签

签名方案：
- 包为 zip，根目录含 ``manifest.yaml``、插件代码、``.ddwplugin.sig``
- 签名对象 = 包内全部文件（除签名文件自身）的相对路径+sha256 清单（排序拼接）
- 算法 Ed25519，签名 base64 写入 ``.ddwplugin.sig``
- 安装时重算清单并验签，失败拒绝安装并报明确错误

密钥：
- 打包端：Ed25519 私钥 PEM（复用 ``scripts/gen_license_keys.py`` 生成的密钥对）
- 安装端：公钥来自显式参数或环境变量 ``DDW_PLUGIN_SIGNING_PUBLIC_KEY``（base64）
"""

from __future__ import annotations

import base64
import hashlib
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.plugin_manager.manager import PLUGINS_ROOT, PluginManager

logger = logging.getLogger(__name__)

# 包内签名文件名与包扩展名
SIGNATURE_FILE_NAME = ".ddwplugin.sig"
PACKAGE_EXTENSION = ".ddwplugin"


def _package_file_manifest(src_root: Path) -> str:
    """包内文件清单（相对路径:sha256，排序拼接，排除签名文件）。"""
    entries = []
    for f in sorted(src_root.rglob("*")):
        if f.is_file() and f.name != SIGNATURE_FILE_NAME:
            rel = f.relative_to(src_root).as_posix()
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            entries.append(f"{rel}:{digest}")
    return "\n".join(entries)


def _resolve_plugin_public_key(
    public_key: Union[str, bytes, Ed25519PublicKey, None],
) -> Ed25519PublicKey:
    """插件包验签公钥：显式参数 → 环境变量 DDW_PLUGIN_SIGNING_PUBLIC_KEY。"""
    if isinstance(public_key, Ed25519PublicKey):
        return public_key
    if isinstance(public_key, bytes):
        return Ed25519PublicKey.from_public_bytes(public_key)
    if isinstance(public_key, str):
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))

    import os

    env_key = os.environ.get("DDW_PLUGIN_SIGNING_PUBLIC_KEY", "").strip()
    if not env_key:
        raise ValueError("未配置 DDW_PLUGIN_SIGNING_PUBLIC_KEY，无法验签插件包")
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(env_key))


def sign_package(
    src_dir: Path,
    private_key: Ed25519PrivateKey,
    output_path: Path,
) -> Path:
    """把插件目录打成 .ddwplugin（zip）并写入签名文件。

    Args:
        src_dir: 含 manifest.yaml + 代码的插件目录。
        private_key: Ed25519 私钥（发证端持有，复用 gen_license_keys.py 产物）。
        output_path: 输出 .ddwplugin 文件路径。

    Returns:
        输出文件路径。
    """
    src_dir = Path(src_dir)
    if not (src_dir / "manifest.yaml").exists():
        raise FileNotFoundError(f"manifest.yaml not found in {src_dir}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ddw_pkg_") as tmp:
        tmp_root = Path(tmp)
        # 拷贝源码（排除旧签名文件），写入新签名
        for item in src_dir.iterdir():
            if item.name == SIGNATURE_FILE_NAME:
                continue
            dst = tmp_root / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
        manifest_text = _package_file_manifest(tmp_root)
        signature = base64.b64encode(
            private_key.sign(manifest_text.encode("utf-8"))
        ).decode()
        (tmp_root / SIGNATURE_FILE_NAME).write_text(signature, encoding="utf-8")

        # zip 打包（根目录包含 manifest.yaml / 代码 / .ddwplugin.sig）
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tmp_root.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(tmp_root).as_posix())

    logger.info("signed plugin package: %s → %s", src_dir, output_path)
    return output_path


def verify_package(
    package_path: Path,
    public_key: Union[str, bytes, Ed25519PublicKey, None] = None,
) -> str:
    """验签 .ddwplugin 包（解压到临时目录后重算清单比对）。

    Returns:
        插件名（manifest 的 name）。

    Raises:
        ValueError: 包结构非法 / 缺签名 / 签名不匹配（含篡改）。
    """
    package_path = Path(package_path)
    if not package_path.exists():
        raise FileNotFoundError(f"插件包不存在: {package_path}")

    try:
        zf = zipfile.ZipFile(package_path)
    except zipfile.BadZipFile as e:
        raise ValueError(f"插件包不是合法的 zip 文件: {e}") from e

    with zf:
        names = zf.namelist()
        if "manifest.yaml" not in names:
            raise ValueError("插件包缺少 manifest.yaml，拒绝安装")
        if SIGNATURE_FILE_NAME not in names:
            raise ValueError("插件包缺少签名文件，拒绝安装（未经签名或包已损坏）")
        # 路径穿越防护：拒绝绝对路径与 ".." 条目
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError(f"插件包包含非法路径: {n}")

        with tempfile.TemporaryDirectory(prefix="ddw_verify_") as tmp:
            tmp_root = Path(tmp)
            zf.extractall(tmp_root)
            manifest_text = _package_file_manifest(tmp_root)
            sig_path = tmp_root / SIGNATURE_FILE_NAME
            sig_b64 = sig_path.read_text(encoding="utf-8").strip()
            try:
                signature = base64.b64decode(sig_b64, validate=True)
            except (ValueError, TypeError) as e:
                raise ValueError("插件包签名文件格式错误") from e
            try:
                pub = _resolve_plugin_public_key(public_key)
                pub.verify(signature, manifest_text.encode("utf-8"))
            except InvalidSignature as e:
                raise ValueError(
                    "插件包签名验证失败（包已被篡改或公钥不匹配），拒绝安装"
                ) from e

            import yaml

            manifest_text2 = (tmp_root / "manifest.yaml").read_text(encoding="utf-8")
            data = yaml.safe_load(manifest_text2) or {}
            name = data.get("name")
            if not name:
                raise ValueError("manifest.yaml 缺少 'name'，拒绝安装")

    logger.info("plugin package verified: %s (name=%s)", package_path, name)
    return name


def install_from_package(
    package_path: Path,
    public_key: Union[str, bytes, Ed25519PublicKey, None] = None,
    *,
    pm: Optional[PluginManager] = None,
    runtime: Any = None,
) -> str:
    """安装 .ddwplugin 包：先验签，通过后才落盘到 plugins/<name>/。

    P4 热加载：传入 ``runtime``（PluginRuntime）时，落盘成功后立即
    ``runtime.load_one(name)``——安装即生效（在线业务不中断）。

    Returns:
        插件名。

    Raises:
        ValueError / FileExistsError / OSError: 验签失败或安装失败（拒绝安装）。
    """
    name = verify_package(package_path, public_key)
    pm = pm or PluginManager()
    dst = pm.plugins_root / name
    if dst.exists():
        raise FileExistsError(f"plugin '{name}' already installed at {dst}")

    with tempfile.TemporaryDirectory(prefix="ddw_install_") as tmp:
        tmp_root = Path(tmp)
        with zipfile.ZipFile(package_path) as zf:
            zf.extractall(tmp_root)
        # 签名文件不落盘到插件目录
        sig_file = tmp_root / SIGNATURE_FILE_NAME
        if sig_file.exists():
            sig_file.unlink()
        shutil.copytree(tmp_root, dst)

    logger.info("installed signed plugin package %s -> %s", package_path, dst)
    if runtime is not None:
        # 安装即生效（失败隔离：加载失败不影响已安装状态，registry 记 error）
        instance = runtime.load_one(name, operator="installer")
        if instance is None:
            logger.warning(
                "plugin %s installed but failed to load (check runtime registry)", name
            )
    return name


def install_from_directory(src: Path, *, pm: Optional[PluginManager] = None) -> str:
    """Copy ``src`` into ``plugins/`` and register it.

    Returns the plugin name (from manifest). Raises on failure.
    """

    pm = pm or PluginManager()
    manifest_path = src / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.yaml not found in {src}")
    import yaml

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    name = data.get("name")
    if not name:
        raise ValueError("manifest.yaml missing 'name'")

    dst = pm.plugins_root / name
    if dst.exists():
        raise FileExistsError(f"plugin '{name}' already installed at {dst}")
    shutil.copytree(src, dst)
    logger.info("installed plugin %s -> %s", name, dst)
    return name


def uninstall(name: str) -> bool:
    """Remove the plugin directory and forget it from the manager."""

    target = PLUGINS_ROOT / name
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
