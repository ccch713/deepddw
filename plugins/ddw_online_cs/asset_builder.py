"""资产包构建：prompt+scripts+knowledge+config+README 打包 tar.gz.

用法：python3 asset_builder.py [--out /path]
"""
from __future__ import annotations

import argparse
import logging
import re
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_DIST_DIR = _BASE_DIR / "dist"


def _extract_prompts() -> dict:
    """从 router.py 源码提取两段 prompt 文本."""
    router_path = _BASE_DIR / "router.py"
    try:
        source = router_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read router.py: %s", exc)
        return {"presales": "", "postsales": ""}

    presales = ""
    postsales = ""

    # 提取 _PRESALES_PROMPT
    m = re.search(
        r'_PRESALES_PROMPT\s*=\s*"""(.*?)"""',
        source,
        re.DOTALL,
    )
    if m:
        presales = m.group(1).strip()

    # 提取 _POSTSALES_PROMPT
    m = re.search(
        r'_POSTSALES_PROMPT\s*=\s*"""(.*?)"""',
        source,
        re.DOTALL,
    )
    if m:
        postsales = m.group(1).strip()

    return {"presales": presales, "postsales": postsales}


def _collect_scripts() -> dict:
    """收集 scripts/*.json 全量话术库."""
    scripts_dir = _BASE_DIR / "scripts"
    result = {}
    if not scripts_dir.exists():
        return result
    for p in scripts_dir.glob("*.json"):
        try:
            result[p.name] = p.read_bytes()
        except Exception as exc:
            logger.warning("Failed to read script %s: %s", p, exc)
    return result


def _collect_knowledge() -> dict:
    """收集 knowledge/*.md 知识库."""
    kb_dir = _BASE_DIR / "knowledge"
    result = {}
    if not kb_dir.exists():
        return result
    for p in kb_dir.glob("*.md"):
        try:
            result[p.name] = p.read_bytes()
        except Exception as exc:
            logger.warning("Failed to read KB %s: %s", p, exc)
    return result


def _build_config_yaml() -> bytes:
    """构建资产包 config.yaml."""
    lines = [
        "# DDW 客服资产包配置",
        "log_retention_days: 30",
        "script_top_k: 3",
        "auto_approve_threshold: 0.9",
        "mode_inject_enabled: true",
    ]
    return "\n".join(lines).encode("utf-8")


def _build_readme(version: str) -> bytes:
    """构建 README.md（含隐私声明）."""
    text = (
        f"# DDW 客服资产包 {version}\n"
        "\n"
        "## 部署说明\n"
        "\n"
        "1. 解压到目标服务器\n"
        "2. 配置 MiniMax API key（环境变量"
        " `DDW_MINIMAX_API_KEY` 或"
        " `config/deployment.yaml`）\n"
        "3. 启动 DDW AI Hub 服务\n"
        "\n"
        "## 内容说明\n"
        "\n"
        "- `prompt/` — 售前/售后 system prompt\n"
        "- `scripts/` — 话术库（经审核的优秀回答范例）\n"
        "- `knowledge/` — 知识库文档\n"
        "- `config.yaml` — 运行配置\n"
        "\n"
        "## 隐私声明\n"
        "\n"
        "**本资产包不含原始对话数据。**\n"
        "话术库仅包含经审核脱敏的问答范例，\n"
        "不包含用户个人信息、会话记录或任何"
        "可识别用户身份的数据。\n"
    )
    return text.encode("utf-8")


def build_asset(
    out_dir: Optional[Path] = None,
) -> Optional[Path]:
    """构建资产包 tar.gz."""
    try:
        prefix = "v1"
        try:
            import yaml as _yaml
            cfg_path = _BASE_DIR / "manifest.yaml"
            if cfg_path.exists():
                d = _yaml.safe_load(
                    cfg_path.read_text(encoding="utf-8")
                ) or {}
                prefix = (
                    d.get("config", {})
                    .get("optional", {})
                    .get("asset_version_prefix", {})
                    .get("default", "v1")
                )
        except Exception:
            pass

        today = time.strftime("%Y%m%d")
        version = f"{prefix}.1.{today}"
        filename = f"ruiguo-ai-cs-assets-{version}.tar.gz"

        dest = out_dir or _DIST_DIR
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / filename

        prompts = _extract_prompts()
        scripts = _collect_scripts()
        knowledge = _collect_knowledge()
        config_bytes = _build_config_yaml()
        readme_bytes = _build_readme(version)

        with tarfile.open(out_path, "w:gz") as tar:
            # prompt/
            for name, content in prompts.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(
                    name=f"prompt/{name}.txt"
                )
                info.size = len(data)
                tar.addfile(info, BytesIO(data))

            # scripts/
            for name, data in scripts.items():
                info = tarfile.TarInfo(
                    name=f"scripts/{name}"
                )
                info.size = len(data)
                tar.addfile(info, BytesIO(data))

            # knowledge/
            for name, data in knowledge.items():
                info = tarfile.TarInfo(
                    name=f"knowledge/{name}"
                )
                info.size = len(data)
                tar.addfile(info, BytesIO(data))

            # config.yaml
            info = tarfile.TarInfo(name="config.yaml")
            info.size = len(config_bytes)
            tar.addfile(info, BytesIO(config_bytes))

            # README.md
            info = tarfile.TarInfo(name="README.md")
            info.size = len(readme_bytes)
            tar.addfile(info, BytesIO(readme_bytes))

        logger.info("Asset built: %s", out_path)
        return out_path
    except Exception as exc:
        logger.warning("build_asset failed: %s", exc)
        return None


def main() -> None:
    """CLI 入口."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="DDW 客服资产包构建"
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出目录（默认 dist/）",
    )
    args = parser.parse_args()
    out = Path(args.out) if args.out else None
    result = build_asset(out)
    if result:
        print(f"Asset built: {result}")
    else:
        print("Asset build failed")


if __name__ == "__main__":
    main()
