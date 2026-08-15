"""GitHub API 客户端 — 仓库管理、Release 创建、制品上传。

使用 httpx 异步 HTTP 客户端与 GitHub REST API v3 交互。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub REST API 客户端。

    用法::

        client = GitHubClient(
            token="ghp_xxx",
            owner="chenye",
        )
        repo = await client.ensure_repo("my-plugin", description="A plugin")
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str = "",
        owner: str = "",
    ):
        self.token = token
        self.owner = owner
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端。"""
        if self._client is None or self._client.is_closed:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # 仓库操作
    # ------------------------------------------------------------------

    async def get_repo(self, name: str) -> Optional[dict]:
        """获取仓库信息。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{name}"
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.json()
        return None

    async def create_repo(
        self,
        name: str,
        *,
        description: str = "",
        private: bool = False,
        auto_init: bool = True,
        default_branch: str = "main",
    ) -> dict:
        """创建仓库。"""
        client = await self._get_client()
        payload = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "default_branch": default_branch,
        }
        resp = await client.post("/user/repos", json=payload)
        resp.raise_for_status()
        repo = resp.json()
        logger.info("✅ GitHub 仓库已创建: %s", repo.get("html_url"))
        return repo

    async def ensure_repo(
        self,
        name: str,
        *,
        description: str = "",
        private: bool = False,
    ) -> dict:
        """确保仓库存在，不存在则创建。"""
        repo = await self.get_repo(name)
        if repo:
            logger.info("📋 GitHub 仓库已存在: %s", repo.get("html_url"))
            return repo
        return await self.create_repo(
            name, description=description, private=private,
        )

    async def delete_repo(self, name: str) -> bool:
        """删除仓库。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{name}"
        resp = await client.delete(url)
        return resp.status_code == 204

    def get_clone_url(self, name: str) -> str:
        """获取仓库 HTTPS clone URL。"""
        return f"https://github.com/{self.owner}/{name}.git"

    # ------------------------------------------------------------------
    # Release 操作
    # ------------------------------------------------------------------

    async def create_release(
        self,
        repo_name: str,
        tag: str,
        *,
        name: str = "",
        body: str = "",
        draft: bool = False,
        prerelease: bool = False,
        target_commitish: str = "main",
    ) -> dict:
        """创建 Git Release。"""
        client = await self._get_client()
        payload = {
            "tag_name": tag,
            "name": name or tag,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
            "target_commitish": target_commitish,
        }
        url = f"/repos/{self.owner}/{repo_name}/releases"
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        release = resp.json()
        logger.info("✅ GitHub Release 已创建: %s", release.get("html_url"))
        return release

    async def get_release(self, repo_name: str, release_id: int) -> dict:
        """获取 Release 信息。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/releases/{release_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_release_by_tag(self, repo_name: str, tag: str) -> dict:
        """通过 tag 名称获取 Release。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/releases/tags/{quote(tag)}"
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def list_releases(
        self, repo_name: str, *, page: int = 1, per_page: int = 10,
    ) -> list[dict]:
        """列出 Releases。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/releases"
        resp = await client.get(url, params={"page": page, "per_page": per_page})
        resp.raise_for_status()
        return resp.json()

    async def delete_release(self, repo_name: str, release_id: int) -> bool:
        """删除 Release。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/releases/{release_id}"
        resp = await client.delete(url)
        return resp.status_code == 204

    # ------------------------------------------------------------------
    # 制品上传
    # ------------------------------------------------------------------

    async def upload_release_asset(
        self,
        repo_name: str,
        release_id: int,
        file_path: Path,
        *,
        label: str = "",
    ) -> dict:
        """上传制品到 Release。

        GitHub API: POST /repos/{owner}/{repo}/releases/{release_id}/assets
        Content-Type: application/octet-stream
        """
        client = await self._get_client()
        file_path = Path(file_path)
        filename = file_path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        url = (
            f"/repos/{self.owner}/{repo_name}/releases/{release_id}/assets"
            f"?name={quote(filename)}"
        )
        if label:
            url += f"&label={quote(label)}"

        with open(file_path, "rb") as f:
            resp = await client.post(
                url,
                content=f.read(),
                headers={"Content-Type": content_type},
            )

        resp.raise_for_status()
        asset = resp.json()
        logger.info("✅ GitHub 制品已上传: %s", asset.get("browser_download_url"))
        return asset

    # ------------------------------------------------------------------
    # 内容操作
    # ------------------------------------------------------------------

    async def get_file_content(
        self, repo_name: str, path: str, ref: str = "main",
    ) -> Optional[str]:
        """获取仓库中文件内容。"""
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/contents/{quote(path)}"
        resp = await client.get(url, params={"ref": ref})
        if resp.status_code == 200:
            data = resp.json()
            import base64
            return base64.b64decode(data["content"]).decode("utf-8")
        return None

    async def create_or_update_file(
        self,
        repo_name: str,
        path: str,
        content: str,
        *,
        message: str = "Update file",
        branch: str = "main",
    ) -> dict:
        """创建或更新仓库中的文件。"""
        import base64
        client = await self._get_client()
        url = f"/repos/{self.owner}/{repo_name}/contents/{quote(path)}"

        sha = None
        resp = await client.get(url, params={"ref": branch})
        if resp.status_code == 200:
            sha = resp.json().get("sha")

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        resp = await client.put(url, json=payload)
        resp.raise_for_status()
        return resp.json()
