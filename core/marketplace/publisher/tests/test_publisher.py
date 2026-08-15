"""Publisher 模块单元测试。

测试 ReleaseManager（纯逻辑）和 GitPublisher（mock 外部依赖）。
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.marketplace.publisher.git_publisher import (
    GitPublisher,
    PublishResult,
    PublishTarget,
)
from core.marketplace.publisher.gitea_client import GiteaClient
from core.marketplace.publisher.github_client import GitHubClient
from core.marketplace.publisher.release_manager import ReleaseManager

# ---------------------------------------------------------------------------
# ReleaseManager 测试
# ---------------------------------------------------------------------------


class TestReleaseManager:
    """ReleaseManager 纯逻辑测试。"""

    def test_bump_version_patch(self):
        assert ReleaseManager.bump_version("1.2.3") == "1.2.4"
        assert ReleaseManager.bump_version("0.0.1") == "0.0.2"

    def test_bump_version_minor(self):
        assert ReleaseManager.bump_version("1.2.3", "minor") == "1.3.0"
        assert ReleaseManager.bump_version("0.0.1", "minor") == "0.1.0"

    def test_bump_version_major(self):
        assert ReleaseManager.bump_version("1.2.3", "major") == "2.0.0"
        assert ReleaseManager.bump_version("0.0.1", "major") == "1.0.0"

    def test_bump_version_with_prerelease(self):
        assert ReleaseManager.bump_version("1.2.3-beta.1") == "1.2.4"
        assert ReleaseManager.bump_version("1.2.3-beta.1", "minor") == "1.3.0"

    def test_bump_version_invalid(self):
        with pytest.raises(ValueError):
            ReleaseManager.bump_version("invalid")
        with pytest.raises(ValueError):
            ReleaseManager.bump_version("1.2.3", "invalid")

    def test_validate_version(self):
        assert ReleaseManager.validate_version("1.0.0") is True
        assert ReleaseManager.validate_version("0.0.1") is True
        assert ReleaseManager.validate_version("1.2.3-beta.1") is True
        assert ReleaseManager.validate_version("1.2.3-rc.1") is True
        assert ReleaseManager.validate_version("invalid") is False
        assert ReleaseManager.validate_version("1.2") is False
        assert ReleaseManager.validate_version("v1.0.0") is False

    def test_package_plugin(self, tmp_path):
        """测试插件打包。"""
        # 创建临时插件目录
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text('# test plugin\n')
        (plugin_dir / "main.py").write_text('print("hello")\n')
        sub = plugin_dir / "submod"
        sub.mkdir()
        (sub / "__init__.py").write_text("# sub\n")

        # 打包
        output_dir = tmp_path / "dist"
        artifact, manifest = ReleaseManager.package_plugin(
            plugin_dir, "test-plugin", "1.0.0",
            output_dir=output_dir,
        )

        assert artifact.exists()
        assert artifact.suffix == ".gz"
        assert "test-plugin-1.0.0.tar.gz" == artifact.name
        assert manifest["name"] == "test-plugin"
        assert manifest["version"] == "1.0.0"

        # 验证 tarball 内容
        import tarfile
        with tarfile.open(artifact, "r:gz") as tar:
            names = tar.getnames()
            assert "test-plugin/__init__.py" in names
            assert "test-plugin/main.py" in names
            assert "test-plugin/submod/__init__.py" in names
            assert "test-plugin/manifest.yaml" in names

    def test_package_plugin_with_existing_manifest(self, tmp_path):
        """测试已有 manifest.yaml 时的打包。"""
        import yaml

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test\n")

        # 写入已有 manifest
        existing = {"name": "old-name", "version": "0.1.0", "custom_field": "value"}
        (plugin_dir / "manifest.yaml").write_text(
            yaml.dump(existing, allow_unicode=True)
        )

        output_dir = tmp_path / "dist"
        artifact, manifest = ReleaseManager.package_plugin(
            plugin_dir, "test-plugin", "1.0.0",
            output_dir=output_dir,
        )

        # 版本号应被更新
        assert manifest["name"] == "test-plugin"
        assert manifest["version"] == "1.0.0"
        # 自定义字段应保留
        assert manifest["custom_field"] == "value"

    def test_generate_checksums(self, tmp_path):
        """测试 checksums 生成。"""
        artifact = tmp_path / "test.tar.gz"
        content = b"fake tarball content"
        artifact.write_bytes(content)

        checksums = ReleaseManager.generate_checksums(artifact)

        # checksums 格式: "<hex>  <filename>" (标准 sha256sum/sha512sum 风格)
        lines = [l for l in checksums.strip().splitlines() if l.strip()]
        assert len(lines) == 2, f"应有 2 行 checksums，实际 {len(lines)}"
        assert "test.tar.gz" in lines[0]
        assert "test.tar.gz" in lines[1]

        # 验证文件已写入
        checksums_file = tmp_path / "test_checksums.txt"
        assert checksums_file.exists()
        assert checksums_file.read_text() == checksums

        # 验证 sha256 值正确（64 字符 hex = sha256）
        expected_sha256 = hashlib.sha256(content).hexdigest()
        assert expected_sha256 in checksums
        # 验证 sha512 值正确（128 字符 hex = sha512）
        expected_sha512 = hashlib.sha512(content).hexdigest()
        assert expected_sha512 in checksums

    def test_create_manifest_snapshot(self, tmp_path):
        """测试 manifest 快照。"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test\n")

        snapshot = ReleaseManager.create_manifest_snapshot(
            plugin_dir, "test-plugin", "2.0.0",
        )

        assert snapshot["name"] == "test-plugin"
        assert snapshot["version"] == "2.0.0"
        assert "packaged_at" in snapshot

    def test_package_plugin_excludes_unwanted_dirs(self, tmp_path):
        """测试打包时排除不需要的目录。"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test\n")

        # 创建应被排除的目录
        for d in (".git", "__pycache__", ".venv", "node_modules", "dist"):
            (plugin_dir / d).mkdir()
            (plugin_dir / d / "junk.txt").write_text("junk")

        output_dir = tmp_path / "dist"
        artifact, _ = ReleaseManager.package_plugin(
            plugin_dir, "test-plugin", "1.0.0",
            output_dir=output_dir,
        )

        import tarfile
        with tarfile.open(artifact, "r:gz") as tar:
            names = tar.getnames()
            for excluded in (".git", "__pycache__", ".venv", "node_modules", "dist"):
                for n in names:
                    assert excluded not in n


# ---------------------------------------------------------------------------
# GiteaClient 测试
# ---------------------------------------------------------------------------


class TestGiteaClient:
    """GiteaClient 单元测试（mock HTTP）。"""

    def test_get_clone_url(self):
        client = GiteaClient(
            base_url="http://localhost:3001",
            token="test-token",
            username="chenye",
        )
        url = client.get_clone_url("my-plugin")
        assert url == "http://localhost:3001/chenye/my-plugin.git"

    @pytest.mark.asyncio
    async def test_ensure_repo_existing(self):
        """测试 ensure_repo 在仓库已存在时。"""
        client = GiteaClient(
            base_url="http://localhost:3001",
            token="test-token",
            username="chenye",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "html_url": "http://localhost:3001/chenye/test-plugin",
            "name": "test-plugin",
        }

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            repo = await client.ensure_repo("test-plugin")
            assert repo["name"] == "test-plugin"
            # 不应调用 create
            mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_repo_creates_new(self):
        """测试 ensure_repo 在仓库不存在时创建新仓库。"""
        client = GiteaClient(
            base_url="http://localhost:3001",
            token="test-token",
            username="chenye",
        )

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "html_url": "http://localhost:3001/chenye/new-plugin",
            "name": "new-plugin",
        }

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_get_resp
            mock_http.post.return_value = mock_post_resp
            mock_get.return_value = mock_http

            repo = await client.ensure_repo("new-plugin", description="New plugin")
            assert repo["name"] == "new-plugin"
            mock_http.post.assert_called_once()


# ---------------------------------------------------------------------------
# GitHubClient 测试
# ---------------------------------------------------------------------------


class TestGitHubClient:
    """GitHubClient 单元测试（mock HTTP）。"""

    def test_get_clone_url(self):
        client = GitHubClient(token="ghp_test", owner="chenye")
        url = client.get_clone_url("my-plugin")
        assert url == "https://github.com/chenye/my-plugin.git"

    @pytest.mark.asyncio
    async def test_ensure_repo_existing(self):
        client = GitHubClient(token="ghp_test", owner="chenye")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "html_url": "https://github.com/chenye/test-plugin",
            "name": "test-plugin",
        }

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            repo = await client.ensure_repo("test-plugin")
            assert repo["name"] == "test-plugin"
            mock_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_repo_creates_new(self):
        client = GitHubClient(token="ghp_test", owner="chenye")

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "html_url": "https://github.com/chenye/new-plugin",
            "name": "new-plugin",
        }

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_get_resp
            mock_http.post.return_value = mock_post_resp
            mock_get.return_value = mock_http

            repo = await client.ensure_repo("new-plugin", description="New plugin")
            assert repo["name"] == "new-plugin"
            mock_http.post.assert_called_once()


# ---------------------------------------------------------------------------
# GitPublisher 测试
# ---------------------------------------------------------------------------


class TestGitPublisher:
    """GitPublisher 单元测试（mock 外部依赖）。"""

    def test_publish_target_enum(self):
        assert PublishTarget.GITEA.value == "gitea"
        assert PublishTarget.GITHUB.value == "github"
        assert PublishTarget.BOTH.value == "both"

    def test_publish_result(self):
        result = PublishResult(
            success=True,
            target=PublishTarget.GITEA,
            repo_url="http://localhost:3001/chenye/test",
        )
        assert result.success is True
        assert result.target == PublishTarget.GITEA
        assert result.error == ""

    def test_resolve_targets(self):
        publisher = GitPublisher.__new__(GitPublisher)
        assert publisher._resolve_targets(PublishTarget.GITEA) == [PublishTarget.GITEA]
        assert publisher._resolve_targets(PublishTarget.GITHUB) == [PublishTarget.GITHUB]
        assert publisher._resolve_targets(PublishTarget.BOTH) == [
            PublishTarget.GITEA, PublishTarget.GITHUB,
        ]

    def test_format_release_body(self):
        body = GitPublisher._format_release_body(
            changelog="修复了一个 bug",
            checksums="abc123  test.tar.gz\n",
            version="1.0.0",
        )
        assert "## 1.0.0" in body
        assert "修复了一个 bug" in body
        assert "abc123" in body
        assert "Checksums" in body

    @pytest.mark.asyncio
    async def test_publish_plugin_dry_run(self, tmp_path):
        """测试 dry-run 模式。"""
        # 创建临时插件目录
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test\n")

        publisher = GitPublisher(
            gitea_url="http://localhost:3001",
            gitea_token="test",
            github_token="test",
            work_dir=tmp_path / "work",
        )

        results = await publisher.publish_plugin(
            name="test-plugin",
            version="1.0.0",
            plugin_dir=plugin_dir,
            changelog="测试发布",
            target=PublishTarget.BOTH,
            dry_run=True,
        )

        assert len(results) == 2
        for r in results:
            assert r.success is True
            assert "dry-run" in r.repo_url

    @pytest.mark.asyncio
    async def test_publish_plugin_mock_gitea(self, tmp_path):
        """测试发布到 mock Gitea。"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test\n")

        publisher = GitPublisher(
            gitea_url="http://localhost:3001",
            gitea_token="test",
            github_token="",  # 无 GitHub token
            work_dir=tmp_path / "work",
        )

        # Mock Gitea 客户端
        mock_repo = {"html_url": "http://localhost:3001/chenye/test-plugin"}
        mock_release = {"id": 1, "html_url": "http://localhost:3001/chenye/test-plugin/releases/1"}
        mock_asset = {"browser_download_url": "http://example.com/test.tar.gz"}

        publisher.gitea_client.ensure_repo = AsyncMock(return_value=mock_repo)
        publisher.gitea_client.create_release = AsyncMock(return_value=mock_release)
        publisher.gitea_client.upload_release_asset = AsyncMock(return_value=mock_asset)

        # Mock git push (避免实际 git 操作)
        with patch.object(publisher, "_push_code_gitea", new_callable=AsyncMock):
            results = await publisher.publish_plugin(
                name="test-plugin",
                version="1.0.0",
                plugin_dir=plugin_dir,
                target=PublishTarget.GITEA,
            )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].target == PublishTarget.GITEA
        assert "test.tar.gz" in results[0].artifact_url
