"""Git 发布核心逻辑 — 协调打包、推送、Release 创建的顶层接口。

支持 Gitea 和 GitHub 双目标，提供统一的发布入口。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import git  # gitpython

from core.marketplace.publisher.gitea_client import GiteaClient
from core.marketplace.publisher.github_client import GitHubClient
from core.marketplace.publisher.release_manager import ReleaseManager

logger = logging.getLogger(__name__)


class PublishTarget(str, Enum):
    """发布目标。"""
    GITEA = "gitea"
    GITHUB = "github"
    BOTH = "both"


@dataclass
class PublishResult:
    """发布结果。"""
    success: bool
    target: PublishTarget
    repo_url: str = ""
    release_url: str = ""
    artifact_url: str = ""
    error: str = ""
    details: dict = field(default_factory=dict)


class GitPublisher:
    """Git 插件发布器 — 顶层协调器。

    用法::

        publisher = GitPublisher(
            gitea_url="http://localhost:3001",
            gitea_token="...",
            github_token="...",
        )
        result = await publisher.publish_plugin(
            name="ddw_token_manager_plugin",
            version="1.2.0",
            plugin_dir=Path("./plugins/ddw_token_manager_plugin"),
            changelog="修复 token 过期问题",
            target=PublishTarget.BOTH,
        )
    """

    def __init__(
        self,
        *,
        gitea_url: str = "http://localhost:3001",
        gitea_token: Optional[str] = None,
        gitea_user: str = "chenye",
        github_token: Optional[str] = None,
        github_owner: Optional[str] = None,
        work_dir: Optional[Path] = None,
    ):
        self.gitea_client = GiteaClient(
            base_url=gitea_url,
            token=gitea_token or self._get_gitea_token(),
            username=gitea_user,
        )
        self.github_client = GitHubClient(
            token=github_token or self._get_github_token(),
            owner=github_owner or os.getenv("GITHUB_OWNER", ""),
        )
        self.release_manager = ReleaseManager()
        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="ddw-publish-"))
        self.work_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_gitea_token() -> str:
        """从 macOS keychain 获取 Gitea token。"""
        import subprocess
        try:
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-s", "gitea-localhost",
                    "-a", "chenye",
                    "-w",
                ],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception as e:
            logger.warning("无法从 keychain 获取 Gitea token: %s", e)
            return os.getenv("GITEA_TOKEN", "")

    @staticmethod
    def _get_github_token() -> str:
        """从环境变量获取 GitHub token。"""
        return os.getenv("GITHUB_TOKEN", "")

    async def publish_plugin(
        self,
        name: str,
        version: str,
        plugin_dir: Path,
        *,
        changelog: str = "",
        target: PublishTarget = PublishTarget.BOTH,
        dry_run: bool = False,
    ) -> list[PublishResult]:
        """发布插件到指定目标。

        Args:
            name: 插件名称
            version: 版本号
            plugin_dir: 插件源码目录
            changelog: 变更日志
            target: 发布目标 (Gitea / GitHub / Both)
            dry_run: 仅打包不推送

        Returns:
            每个目标的发布结果列表
        """
        results: list[PublishResult] = []

        # Step 1: 打包插件
        logger.info("📦 打包插件 %s v%s ...", name, version)
        artifact, manifest = self.release_manager.package_plugin(
            plugin_dir, name, version,
        )
        logger.info("  ✅ 制品: %s (%.1f KB)", artifact, artifact.stat().st_size / 1024)

        # Step 2: 生成 checksums
        checksums = self.release_manager.generate_checksums(artifact)
        logger.info("  ✅ Checksums 已生成")

        # Step 3: 推送到各目标
        targets = self._resolve_targets(target)

        for t in targets:
            try:
                result = await self._publish_to_target(
                    t, name, version, plugin_dir, artifact,
                    manifest, checksums, changelog, dry_run,
                )
                results.append(result)
            except Exception as e:
                logger.error("❌ 发布到 %s 失败: %s", t.value, e)
                results.append(PublishResult(
                    success=False,
                    target=t,
                    error=str(e),
                ))

        # 清理临时制品
        if artifact.exists():
            artifact.unlink()
        checksums_path = artifact.parent / f"{artifact.stem}_checksums.txt"
        if checksums_path.exists():
            checksums_path.unlink()

        return results

    async def create_release(
        self,
        name: str,
        version: str,
        *,
        tag: Optional[str] = None,
        changelog: str = "",
        target: PublishTarget = PublishTarget.BOTH,
        artifact_path: Optional[Path] = None,
    ) -> list[PublishResult]:
        """创建 Git Release（不重新打包）。

        Args:
            name: 插件名称
            version: 版本号
            tag: Git tag 名称，默认 v{version}
            changelog: Release 说明
            target: 发布目标
            artifact_path: 可选的已有制品路径

        Returns:
            每个目标的创建结果列表
        """
        tag = tag or f"v{version}"
        results: list[PublishResult] = []
        targets = self._resolve_targets(target)

        for t in targets:
            try:
                if t == PublishTarget.GITEA:
                    release = await self.gitea_client.create_release(
                        repo_name=name,
                        tag=tag,
                        name=f"{name} {version}",
                        body=changelog,
                        draft=False,
                        prerelease=False,
                    )
                    url = release.get("html_url", "")
                    # 上传制品
                    if artifact_path and artifact_path.exists():
                        asset = await self.gitea_client.upload_release_asset(
                            repo_name=name,
                            release_id=release["id"],
                            file_path=artifact_path,
                        )
                        url = asset.get("browser_download_url", url)

                    results.append(PublishResult(
                        success=True,
                        target=t,
                        release_url=url,
                        details=release,
                    ))

                elif t == PublishTarget.GITHUB:
                    release = await self.github_client.create_release(
                        repo_name=name,
                        tag=tag,
                        name=f"{name} {version}",
                        body=changelog,
                        draft=False,
                        prerelease=False,
                    )
                    url = release.get("html_url", "")
                    if artifact_path and artifact_path.exists():
                        asset = await self.github_client.upload_release_asset(
                            repo_name=name,
                            release_id=release["id"],
                            file_path=artifact_path,
                        )
                        url = asset.get("browser_download_url", url)

                    results.append(PublishResult(
                        success=True,
                        target=t,
                        release_url=url,
                        details=release,
                    ))

            except Exception as e:
                logger.error("❌ 创建 Release 失败 (%s): %s", t.value, e)
                results.append(PublishResult(
                    success=False,
                    target=t,
                    error=str(e),
                ))

        return results

    async def upload_artifact(
        self,
        name: str,
        version: str,
        file_path: Path,
        *,
        target: PublishTarget = PublishTarget.BOTH,
    ) -> list[PublishResult]:
        """上传插件包到已有 Release。

        Args:
            name: 插件名称
            version: 版本号
            file_path: 制品文件路径
            target: 发布目标

        Returns:
            每个目标的上传结果列表
        """
        tag = f"v{version}"
        results: list[PublishResult] = []
        targets = self._resolve_targets(target)

        for t in targets:
            try:
                if t == PublishTarget.GITEA:
                    release = await self.gitea_client.get_release_by_tag(name, tag)
                    asset = await self.gitea_client.upload_release_asset(
                        repo_name=name,
                        release_id=release["id"],
                        file_path=file_path,
                    )
                    results.append(PublishResult(
                        success=True,
                        target=t,
                        artifact_url=asset.get("browser_download_url", ""),
                        details=asset,
                    ))

                elif t == PublishTarget.GITHUB:
                    release = await self.github_client.get_release_by_tag(name, tag)
                    asset = await self.github_client.upload_release_asset(
                        repo_name=name,
                        release_id=release["id"],
                        file_path=file_path,
                    )
                    results.append(PublishResult(
                        success=True,
                        target=t,
                        artifact_url=asset.get("browser_download_url", ""),
                        details=asset,
                    ))

            except Exception as e:
                logger.error("❌ 上传制品失败 (%s): %s", t.value, e)
                results.append(PublishResult(
                    success=False,
                    target=t,
                    error=str(e),
                ))

        return results

    async def _publish_to_target(
        self,
        target: PublishTarget,
        name: str,
        version: str,
        plugin_dir: Path,
        artifact: Path,
        manifest: dict,
        checksums: str,
        changelog: str,
        dry_run: bool,
    ) -> PublishResult:
        """发布到单个目标。"""
        tag = f"v{version}"

        if dry_run:
            logger.info("  🔍 [DRY RUN] 将发布到 %s: %s %s", target.value, name, version)
            return PublishResult(
                success=True,
                target=target,
                repo_url=f"(dry-run) {target.value}/{name}",
            )

        if target == PublishTarget.GITEA:
            return await self._publish_to_gitea(
                name, version, plugin_dir, artifact,
                manifest, checksums, changelog, tag,
            )
        elif target == PublishTarget.GITHUB:
            return await self._publish_to_github(
                name, version, plugin_dir, artifact,
                manifest, checksums, changelog, tag,
            )
        else:
            raise ValueError(f"不支持的目标: {target}")

    async def _publish_to_gitea(
        self, name, version, plugin_dir, artifact,
        manifest, checksums, changelog, tag,
    ) -> PublishResult:
        """发布到 Gitea。"""
        # 确保仓库存在
        repo = await self.gitea_client.ensure_repo(
            name=name,
            description=manifest.get("description", ""),
            private=manifest.get("private", False),
        )
        repo_url = repo.get("html_url", "")

        # 用 gitpython 推送代码
        repo_dir = self.work_dir / name
        await self._push_code_gitea(
            repo_dir, name, plugin_dir, tag, version, manifest,
        )

        # 创建 Release
        release = await self.gitea_client.create_release(
            repo_name=name,
            tag=tag,
            name=f"{name} {version}",
            body=self._format_release_body(changelog, checksums, version),
            draft=False,
            prerelease="-rc" in version or "-beta" in version,
        )

        # 上传制品
        asset = await self.gitea_client.upload_release_asset(
            repo_name=name,
            release_id=release["id"],
            file_path=artifact,
        )

        logger.info("  ✅ Gitea 发布成功: %s", repo_url)
        return PublishResult(
            success=True,
            target=PublishTarget.GITEA,
            repo_url=repo_url,
            release_url=release.get("html_url", ""),
            artifact_url=asset.get("browser_download_url", ""),
        )

    async def _publish_to_github(
        self, name, version, plugin_dir, artifact,
        manifest, checksums, changelog, tag,
    ) -> PublishResult:
        """发布到 GitHub。"""
        # 确保仓库存在
        repo = await self.github_client.ensure_repo(
            name=name,
            description=manifest.get("description", ""),
            private=manifest.get("private", False),
        )
        repo_url = repo.get("html_url", "")

        # 推送代码
        repo_dir = self.work_dir / name
        await self._push_code_github(
            repo_dir, name, plugin_dir, tag, version, manifest,
        )

        # 创建 Release
        release = await self.github_client.create_release(
            repo_name=name,
            tag=tag,
            name=f"{name} {version}",
            body=self._format_release_body(changelog, checksums, version),
            draft=False,
            prerelease="-rc" in version or "-beta" in version,
        )

        # 上传制品
        asset = await self.github_client.upload_release_asset(
            repo_name=name,
            release_id=release["id"],
            file_path=artifact,
        )

        logger.info("  ✅ GitHub 发布成功: %s", repo_url)
        return PublishResult(
            success=True,
            target=PublishTarget.GITHUB,
            repo_url=repo_url,
            release_url=release.get("html_url", ""),
            artifact_url=asset.get("browser_download_url", ""),
        )

    async def _push_code_gitea(
        self, repo_dir: Path, name: str, plugin_dir: Path,
        tag: str, version: str, manifest: dict,
    ) -> None:
        """用 gitpython 推送代码到 Gitea。"""
        # Clone 或 init
        remote_url = self.gitea_client.get_clone_url(name)

        if (repo_dir / ".git").exists():
            repo = git.Repo(str(repo_dir))
            repo.remotes.origin.pull()
        else:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            try:
                repo = git.Repo.clone_from(remote_url, str(repo_dir))
            except git.exc.GitCommandError:
                repo_dir.mkdir(parents=True, exist_ok=True)
                repo = git.Repo.init(str(repo_dir))
                remote = repo.create_remote("origin", remote_url)

        # 复制插件文件（排除 .git 和 __pycache__）
        for item in plugin_dir.iterdir():
            if item.name in (".git", "__pycache__", ".venv", "node_modules"):
                continue
            dest = repo_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # 写入 manifest
        import yaml
        manifest_path = repo_dir / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest, allow_unicode=True, default_flow_style=False))

        # Git commit + tag + push
        repo.git.add(A=True)
        repo.index.commit(f"release: {name} v{version}")

        try:
            repo.create_tag(tag, force=True)
        except git.exc.GitCommandError:
            repo.delete_tag(tag)
            repo.create_tag(tag)

        # 确保 origin 存在
        if "origin" not in [r.name for r in repo.remotes]:
            repo.create_remote("origin", remote_url)

        try:
            repo.remotes.origin.push(tag, force=True)
        except git.exc.GitCommandError:
            # 首次推送，设置上游
            repo.git.push("--set-upstream", "origin", tag, force=True)

    async def _push_code_github(
        self, repo_dir: Path, name: str, plugin_dir: Path,
        tag: str, version: str, manifest: dict,
    ) -> None:
        """用 gitpython 推送代码到 GitHub。"""
        remote_url = self.github_client.get_clone_url(name)

        if (repo_dir / ".git").exists():
            repo = git.Repo(str(repo_dir))
            repo.remotes.origin.pull()
        else:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            try:
                repo = git.Repo.clone_from(remote_url, str(repo_dir))
            except git.exc.GitCommandError:
                repo_dir.mkdir(parents=True, exist_ok=True)
                repo = git.Repo.init(str(repo_dir))
                repo.create_remote("origin", remote_url)

        # 复制插件文件
        for item in plugin_dir.iterdir():
            if item.name in (".git", "__pycache__", ".venv", "node_modules"):
                continue
            dest = repo_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # 写入 manifest
        import yaml
        manifest_path = repo_dir / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest, allow_unicode=True, default_flow_style=False))

        repo.git.add(A=True)
        repo.index.commit(f"release: {name} v{version}")

        try:
            repo.create_tag(tag, force=True)
        except git.exc.GitCommandError:
            repo.delete_tag(tag)
            repo.create_tag(tag)

        if "origin" not in [r.name for r in repo.remotes]:
            repo.create_remote("origin", remote_url)

        try:
            repo.remotes.origin.push(tag, force=True)
        except git.exc.GitCommandError:
            repo.git.push("--set-upstream", "origin", tag, force=True)

    @staticmethod
    def _format_release_body(changelog: str, checksums: str, version: str) -> str:
        """格式化 Release 说明。"""
        lines = [
            f"## {version}",
            "",
        ]
        if changelog:
            lines.extend(["### 变更", "", changelog, ""])
        lines.extend([
            "### Checksums",
            "```",
            checksums.strip(),
            "```",
        ])
        return "\n".join(lines)

    def _resolve_targets(self, target: PublishTarget) -> list[PublishTarget]:
        """解析发布目标列表。"""
        if target == PublishTarget.BOTH:
            return [PublishTarget.GITEA, PublishTarget.GITHUB]
        return [target]
