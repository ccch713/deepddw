"""DDW 机器指纹模块（独立成模块，便于测试 monkeypatch）。

指纹算法：
1. 按平台探测“主指纹源”：
   - Linux: 优先 ``/etc/machine-id``，其次 ``/var/lib/dbus/machine-id``
   - macOS: ``system_profiler SPHardwareDataType`` 解析 IOPlatformUUID
     （Hardware UUID），失败时回退 ``platform.node()``
   - Docker: 宿主 machine-id（``/hostfs/etc/machine-id`` 挂载，跨机复制可区分）
     + 容器 ID（cgroup 解析，同宿主多容器可区分）；宿主未挂载时降级并告警
2. 最终指纹 = sha256(主指纹源 + "\\n" + hostname) 的 hex 前 32 位

指纹不落盘、不传远端，仅用于本地许可证与机器绑定校验。
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 指纹长度（hex 前 32 位 = 128 bit）
FINGERPRINT_LENGTH = 32

_LINUX_MACHINE_ID_PATHS = (
    "/etc/machine-id",
    "/var/lib/dbus/machine-id",
)

_MAC_UUID_PATTERN = re.compile(r"Hardware UUID:\s*(\S+)")

_DOCKERENV = Path("/.dockerenv")


def get_hostname() -> str:
    """返回本机 hostname（socket 优先，platform.node() 兜底）。"""
    try:
        name = socket.gethostname()
    except OSError:
        name = platform.node()
    return name or "unknown-host"


def _read_first_existing(paths: tuple[str, ...]) -> Optional[str]:
    """依次读取存在的文件内容，去掉首尾空白；全部不可读返回 None。"""
    for p in paths:
        path = Path(p)
        try:
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    return content
        except OSError:
            continue
    return None


def _is_docker() -> bool:
    try:
        return _DOCKERENV.exists()
    except OSError:
        return False


def _mac_platform_uuid() -> Optional[str]:
    """macOS 通过 system_profiler 读取 IOPlatformUUID（Hardware UUID）。"""
    try:
        out = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("machine fingerprint: system_profiler unavailable: %s", e)
        return None
    match = _MAC_UUID_PATTERN.search(out or "")
    return match.group(1).strip() if match else None


def _docker_container_id() -> Optional[str]:
    """从 /proc/self/cgroup 解析容器 ID
    （cgroup v2: docker-<64hex>.scope；v1: /docker/<64hex>）。
    """
    try:
        text = Path("/proc/self/cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _docker_container_id_from_text(text)


def _docker_container_id_from_text(cgroup_text: str) -> Optional[str]:
    """纯函数：解析 cgroup 文本中的容器 ID（便于测试）。"""
    for line in cgroup_text.splitlines():
        m = re.search(r"docker-([0-9a-f]{64})", line)
        if m:
            return m.group(1)
        m = re.search(r"/docker/([0-9a-f]{64})", line)
        if m:
            return m.group(1)
    return None


# 宿主 machine-id 挂载点
# （部署时 docker run -v /etc/machine-id:/hostfs/etc/machine-id:ro）
_HOST_MACHINE_ID_PATHS = (
    "/hostfs/etc/machine-id",
    "/hostfs/var/lib/dbus/machine-id",
)


def _docker_primary_source() -> str:
    """Docker 指纹主源：宿主 machine-id（跨机复制可区分）+ 容器 ID（同宿主可区分）。

    同镜像多容器 /etc/machine-id 相同（镜像层），仅靠它会产生一码多用；
    宿主 machine-id 需部署端挂载（:ro），未挂载时降级为容器 ID + hostname 并告警。
    """
    host_id = _read_first_existing(_HOST_MACHINE_ID_PATHS)
    container_id = _docker_container_id() or get_hostname()
    if host_id:
        return f"docker:host={host_id}:container={container_id}"
    logger.warning(
        "docker fingerprint: host machine-id not mounted (/hostfs/etc/machine-id) — "
        "cross-host clone detection degraded; mount it with "
        "-v /etc/machine-id:/hostfs/etc/machine-id:ro"
    )
    return f"docker:container={container_id}:host=unknown"


def _get_primary_fingerprint_source() -> str:
    """按平台返回主指纹源字符串（调用方组合 hostname 后 sha256）。"""
    system = platform.system().lower()

    if _is_docker():
        return _docker_primary_source()

    if system == "darwin":
        return _mac_platform_uuid() or platform.node()

    # Linux 及其他 Unix：machine-id 优先
    return _read_first_existing(_LINUX_MACHINE_ID_PATHS) or platform.node()


def get_machine_fingerprint() -> str:
    """计算本机指纹：sha256(主指纹源 + 换行 + hostname) 的 hex 前 32 位。

    - 同一台机器多次调用结果稳定；
    - 主指纹源读取失败时以 hostname 兜底（保证总有值可算）。
    """
    primary = _get_primary_fingerprint_source() or get_hostname()
    hostname = get_hostname()
    digest = hashlib.sha256(f"{primary}\n{hostname}".encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_LENGTH]


__all__ = [
    "FINGERPRINT_LENGTH",
    "get_hostname",
    "get_machine_fingerprint",
    "_docker_container_id_from_text",
]
