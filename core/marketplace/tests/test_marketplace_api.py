"""插件市场 API 测试。

测试所有 FastAPI 端点的响应和错误处理。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.marketplace.plugin_market import (
    PluginCategory,
)
from core.marketplace.router import router


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """创建测试客户端。"""
    app = FastAPI()
    app.include_router(router)

    # 创建临时插件目录
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    # 添加测试插件
    plugin_dir = plugins_dir / "test-plugin"
    plugin_dir.mkdir()
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "description": "测试插件",
        "author": "Test Author",
        "license": "MIT",
        "ecosystem": {
            "category": "ai_tools",
            "tags": ["test"],
        },
        "permissions": ["database"],
    }
    (plugin_dir / "manifest.yaml").write_text(
        yaml.dump(manifest, allow_unicode=True), encoding="utf-8"
    )

    # Mock registry
    mock_listing = MagicMock()
    mock_listing.name = "test-plugin"
    mock_listing.version = "1.0.0"
    mock_listing.description = "测试插件"
    mock_listing.author = "Test Author"
    mock_listing.license = "MIT"
    mock_listing.category = PluginCategory.AI_TOOLS
    mock_listing.rating = 4.5
    mock_listing.downloads = 100
    mock_listing.tags = ["test"]
    mock_listing.engine = ">=0.1.0"
    mock_listing.permissions = ["database"]
    mock_listing.dependencies = {}
    mock_listing.config_schema = None
    mock_listing.manifest_raw = manifest

    mock_registry = MagicMock()
    mock_registry.scan_local_plugins.return_value = [mock_listing]
    mock_registry.get_plugin_detail.return_value = mock_listing
    mock_registry.get_plugin_listings.return_value = [mock_listing]
    mock_registry.refresh_registry.return_value = [mock_listing]

    # Mock installer
    mock_installer = MagicMock()

    # Mock database session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    mock_factory = MagicMock()
    mock_factory.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.session.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "core.marketplace.router.get_plugin_registry", return_value=mock_registry
    ), patch(
        "core.marketplace.router.get_plugin_installer", return_value=mock_installer
    ), patch(
        "core.marketplace.router.get_engine_factory", return_value=mock_factory
    ):
        yield TestClient(app)


class TestMarketplaceAPI:
    """市场 API 端点测试。"""

    def test_list_plugins(self, client: TestClient) -> None:
        """测试获取插件市场列表。"""
        response = client.get("/plugins")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] >= 0

    def test_list_plugins_with_category_filter(
        self, client: TestClient
    ) -> None:
        """测试按分类过滤插件列表。"""
        response = client.get("/plugins", params={"category": "ai_tools"})
        assert response.status_code == 200

    def test_list_plugins_with_search(self, client: TestClient) -> None:
        """测试搜索插件。"""
        response = client.get("/plugins", params={"search": "test"})
        assert response.status_code == 200

    def test_get_plugin_detail(self, client: TestClient) -> None:
        """测试获取插件详情。"""
        response = client.get("/plugins/test-plugin")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-plugin"
        assert data["version"] == "1.0.0"

    def test_get_plugin_detail_not_found(self, client: TestClient) -> None:
        """测试获取不存在的插件详情。"""
        # Mock 返回 None
        with patch(
            "core.marketplace.router.get_plugin_registry"
        ) as mock_reg:
            mock_reg.return_value.get_plugin_detail.return_value = None
            response = client.get("/plugins/nonexistent")
            assert response.status_code == 404

    def test_get_market_stats(self, client: TestClient) -> None:
        """测试获取市场统计信息。"""
        response = client.get("/plugins/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_plugins" in data
        assert "installed_plugins" in data

    def test_get_installed_plugins(self, client: TestClient) -> None:
        """测试获取已安装插件列表。"""
        response = client.get("/plugins/installed")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_get_available_plugins(self, client: TestClient) -> None:
        """测试获取可安装插件列表。"""
        response = client.get("/plugins/available")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_install_plugin(self, client: TestClient) -> None:
        """测试安装插件。"""
        mock_installer = MagicMock()
        mock_installer.install_plugin = AsyncMock(
            return_value={
                "success": True,
                "message": "插件安装成功",
                "action": "install",
            }
        )

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/test-plugin/install")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_uninstall_plugin(self, client: TestClient) -> None:
        """测试卸载插件。"""
        mock_installer = MagicMock()
        mock_installer.uninstall_plugin = AsyncMock(
            return_value={
                "success": True,
                "message": "插件已卸载",
                "action": "uninstall",
            }
        )

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/test-plugin/uninstall")
            assert response.status_code == 200

    def test_enable_plugin(self, client: TestClient) -> None:
        """测试启用插件。"""
        mock_installer = MagicMock()
        mock_installer.enable_plugin = AsyncMock(
            return_value={
                "success": True,
                "message": "插件已启用",
                "action": "enable",
            }
        )

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/test-plugin/enable")
            assert response.status_code == 200

    def test_disable_plugin(self, client: TestClient) -> None:
        """测试禁用插件。"""
        mock_installer = MagicMock()
        mock_installer.disable_plugin = AsyncMock(
            return_value={
                "success": True,
                "message": "插件已禁用",
                "action": "disable",
            }
        )

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/test-plugin/disable")
            assert response.status_code == 200

    def test_install_plugin_failure(self, client: TestClient) -> None:
        """测试安装插件失败。"""
        mock_installer = MagicMock()
        mock_installer.install_plugin = AsyncMock(
            return_value={
                "success": False,
                "message": "安装失败",
                "action": "install",
            }
        )

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/test-plugin/install")
            assert response.status_code == 400

    def test_refresh_registry(self, client: TestClient) -> None:
        """测试刷新注册表。"""
        response = client.post("/plugins/refresh")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_validate_manifest(self, client: TestClient) -> None:
        """测试验证 manifest。"""
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "测试插件",
        }

        # 需要单独 mock installer 的 validate_manifest 返回值
        mock_installer = MagicMock()
        mock_installer.validate_manifest.return_value = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        with patch(
            "core.marketplace.router.get_plugin_installer", return_value=mock_installer
        ):
            response = client.post("/plugins/validate-manifest", json=manifest)
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True

    def test_create_review(self, client: TestClient) -> None:
        """测试创建插件评价。"""
        review_data = {
            "user_id": "user123",
            "rating": 5,
            "comment": "很好的插件！",
        }

        # Mock 评价创建
        mock_review = MagicMock()
        mock_review.id = 1
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_review
        mock_result.scalar.return_value = 4.5
        mock_session.execute.return_value = mock_result

        mock_factory = MagicMock()
        mock_factory.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_factory.session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "core.marketplace.router.get_engine_factory", return_value=mock_factory
        ):
            response = client.post("/plugins/test-plugin/reviews", json=review_data)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_list_reviews(self, client: TestClient) -> None:
        """测试获取插件评价列表。"""
        response = client.get("/plugins/test-plugin/reviews")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_pagination_params(self, client: TestClient) -> None:
        """测试分页参数。"""
        response = client.get("/plugins", params={"page": 1, "page_size": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_invalid_page_params(self, client: TestClient) -> None:
        """测试无效分页参数。"""
        response = client.get("/plugins", params={"page": 0})
        assert response.status_code == 422  # Validation error

        response = client.get("/plugins", params={"page_size": 200})
        assert response.status_code == 422  # Exceeds max
