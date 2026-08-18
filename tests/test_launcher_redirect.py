"""M1（v0.5.0 架构重写）：launcher 删除 + 跳转测试。

验收：launcher.html 不存在；/ 与 /ui/deepddw-launcher.html
均 307/302 跳转到 /dsh/；现有端点不变。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-m1-redirect-token")


def test_launcher_file_removed():
    """v0.5.0：frontend/deepddw-launcher.html 已删除。"""
    import os

    assert not os.path.exists("frontend/deepddw-launcher.html")


async def test_root_redirects_to_dsh(client):
    """根路径 / → /dsh/（v0.5.0 统一入口）。"""
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 307)
    assert resp.headers.get("location") == "/dsh/"


async def test_legacy_launcher_path_redirects_to_dsh(client):
    """旧 /ui/deepddw-launcher.html 路径 → /dsh/（兼容旧书签）。"""
    resp = await client.get("/ui/deepddw-launcher.html", follow_redirects=False)
    assert resp.status_code in (301, 302, 307)
    assert resp.headers.get("location") == "/dsh/"
