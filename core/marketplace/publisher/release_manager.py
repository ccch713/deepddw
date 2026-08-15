"""版本发布管理 — 打包、校验、manifest 快照、版本号管理。

负责将插件目录打包为可发布的制品，并生成配套的校验和与清单。
"""

from __future__ import annotations

import hashlib
import logging
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ReleaseManager:
    """版本发布管理器。

    用法::

        manager = ReleaseManager()
        artifact, manifest = manager.package_plugin(
            plugin_dir=Path("./my-plugin"),
            name="my-plugin",
            version="1.0.0",
        )
        checksums = manager.generate_checksums(artifact)
        new_version = manager.bump_version("1.0.0", "minor")
    """

    @staticmethod
    def package_plugin(
        plugin_dir: Path,
        name: str,
        version: str,
        *,
        output_dir: Optional[Path] = None,
    ) -> tuple[Path, dict]:
        """将插件目录打包为 .tar.gz 制品。

        Args:
            plugin_dir: 插件源码目录
            name: 插件名称
            version: 版本号
            output_dir: 输出目录，默认在 plugin_dir 的父目录下

        Returns:
            (制品路径, manifest 字典)
        """
        plugin_dir = Path(plugin_dir)
        if not plugin_dir.exists():
            raise FileNotFoundError(f"插件目录不存在: {plugin_dir}")

        # 读取已有 manifest 或生成新的
        manifest_path = plugin_dir / "manifest.yaml"
        manifest = ReleaseManager._load_or_create_manifest(
            plugin_dir, name, version,
        )

        # 输出路径
        if output_dir is None:
            output_dir = plugin_dir.parent / "dist"
        output_dir.mkdir(parents=True, exist_ok=True)

        tarball_name = f"{name}-{version}.tar.gz"
        tarball_path = output_dir / tarball_name

        # 创建 tar.gz
        exclude = {".git", "__pycache__", ".venv", "node_modules", "dist", ".mypy_cache", ".pytest_cache"}
        with tarfile.open(tarball_path, "w:gz") as tar:
            for item in sorted(plugin_dir.iterdir()):
                if item.name in exclude:
                    continue
                if item.is_dir():
                    tar.add(str(item), arcname=f"{name}/{item.name}")
                else:
                    tar.add(str(item), arcname=f"{name}/{item.name}")

            # 写入 manifest.yaml 到 tarball 根目录
            import io

            import yaml
            manifest_content = yaml.dump(
                manifest, allow_unicode=True, default_flow_style=False,
            ).encode("utf-8")
            manifest_info = tarfile.TarInfo(name=f"{name}/manifest.yaml")
            manifest_info.size = len(manifest_content)
            manifest_info.mtime = datetime.now(timezone.utc).timestamp()
            tar.addfile(manifest_info, io.BytesIO(manifest_content))

        logger.info(
            "📦 制品已打包: %s (%.1f KB)",
            tarball_path, tarball_path.stat().st_size / 1024,
        )
        return tarball_path, manifest

    @staticmethod
    def generate_checksums(artifact: Path) -> str:
        """为制品生成 checksums 文件。

        返回 checksums 文本内容，同时写入 {base_name}_checksums.txt。
        """
        artifact = Path(artifact)
        lines = []
        for algo_name, algo in [("sha256", hashlib.sha256), ("sha512", hashlib.sha512)]:
            h = algo()
            with open(artifact, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            hex_digest = h.hexdigest()
            lines.append(f"{hex_digest}  {artifact.name}")

        content = "\n".join(lines) + "\n"

        # 处理 .tar.gz 等双后缀：去掉所有扩展名
        base_name = artifact.name
        for ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
            if base_name.endswith(ext):
                base_name = base_name[: -len(ext)]
                break
        else:
            base_name = artifact.stem

        checksums_path = artifact.parent / f"{base_name}_checksums.txt"
        checksums_path.write_text(content)
        logger.info("✅ Checksums 已生成: %s", checksums_path)
        return content

    @staticmethod
    def create_manifest_snapshot(
        plugin_dir: Path,
        name: str,
        version: str,
        *,
        output_path: Optional[Path] = None,
    ) -> dict:
        """创建 manifest.yaml 快照。

        读取插件目录信息，生成完整的 manifest 快照。
        """
        manifest = ReleaseManager._load_or_create_manifest(
            plugin_dir, name, version,
        )

        if output_path:
            import yaml
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                yaml.dump(manifest, allow_unicode=True, default_flow_style=False),
            )
            logger.info("✅ Manifest 快照已保存: %s", output_path)

        return manifest

    @staticmethod
    def bump_version(current: str, part: str = "patch") -> str:
        """版本号递增。

        Args:
            current: 当前版本号 (e.g., "1.2.3")
            part: 递增部分 (major / minor / patch)

        Returns:
            新版本号

        Raises:
            ValueError: 版本号格式不正确
        """
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(-.+)?$", current)
        if not match:
            raise ValueError(f"无效版本号: {current}")

        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        suffix = match.group(4) or ""

        if part == "major":
            return f"{major + 1}.0.0"
        elif part == "minor":
            return f"{major}.{minor + 1}.0"
        elif part == "patch":
            return f"{major}.{minor}.{patch + 1}"
        else:
            raise ValueError(f"无效的版本递增部分: {part}")

    @staticmethod
    def validate_version(version: str) -> bool:
        """验证版本号格式。"""
        return bool(re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$", version))

    @staticmethod
    def _load_or_create_manifest(
        plugin_dir: Path, name: str, version: str,
    ) -> dict:
        """加载或创建 manifest 字典。"""
        import yaml

        manifest_path = plugin_dir / "manifest.yaml"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f) or {}
                # 更新版本号
                manifest["name"] = name
                manifest["version"] = version
                return manifest
            except Exception as e:
                logger.warning("读取 manifest.yaml 失败: %s，将创建新的", e)

        # 尝试读取 setup.py / pyproject.toml 获取元数据
        description = ""
        author = "Unknown"
        license_str = "MIT"
        dependencies = []

        pyproject_path = plugin_dir / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomllib
                with open(pyproject_path, "rb") as f:
                    pyproject = tomllib.load(f)
                project = pyproject.get("project", {})
                description = project.get("description", "")
                author = project.get("authors", [{}])[0].get("name", "Unknown") if project.get("authors") else "Unknown"
                license_str = str(project.get("license", {}).get("text", "MIT")) if isinstance(project.get("license"), dict) else str(project.get("license", "MIT"))
                dependencies = project.get("dependencies", [])
            except Exception:
                pass

        setup_path = plugin_dir / "setup.py"
        if setup_path.exists() and not description:
            try:
                content = setup_path.read_text()
                if "description=" in content:
                    match = re.search(r'description\s*=\s*["\'](.+?)["\']', content)
                    if match:
                        description = match.group(1)
            except Exception:
                pass

        # 检查 README
        readme = ""
        for readme_name in ("README.md", "README.rst", "README.txt", "README"):
            readme_path = plugin_dir / readme_name
            if readme_path.exists():
                readme = readme_path.read_text()[:500]  # 截断过长的 README
                break

        return {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
            "license": license_str,
            "engine": ">=0.1.0",
            "dependencies": dependencies,
            "readme_preview": readme,
            "packaged_at": datetime.now(timezone.utc).isoformat(),
        }
