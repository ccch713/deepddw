"""ddw-website 插件 — 配置加载/持久化（独立模块避免循环导入）."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 默认站点配置（与官网建设规范 v1.0 的不可变信息一致）
DEFAULT_SITE_CONFIG: Dict[str, Any] = {
    "theme": {
        "current": "standard",          # standard / holiday / mourning
        "available": ["standard", "holiday", "mourning"],
        "note": "主题模版只能通过 DDW 底座管理后台切换，前台无切换入口",
    },
    "company": {
        "full_name": "武汉锐果互动信息技术有限公司",
        "short_name": "锐果互动",
        "english_name": "Wuhan Ruiguo Interactive Information Technology Co., Ltd.",
        "icp": "鄂ICP备2026024883号-1",
        "police": "鄂公网安备42011102006255号",
        "phone": "027-89578881",
        "email": "contact@ruigoo.com",
        "address": "武汉市东湖新技术开发区光谷大道77号",
        "github": "https://github.com/ccch713/ddw-code-cli",
    },
    "pages": {
        "home": "index.html",
        "products": "products.html",
        "platform": "platform.html",
        "plugins": "plugins.html",
        "services": "services.html",
        "industry": "industry.html",
        "service_esg": "service-esg.html",
        "service_ddw": "service-ddw.html",
        "service_it": "service-it.html",
        "service_manufacturing": "service-manufacturing.html",
    },
    "links": {
        "ddw_platform": "https://ddw.9cio.com",
        "ddw_marketplace": "https://ddw.9cio.com/marketplace",
        "quality_mgmt": "https://ddw.9cio.com/quality-mgmt",
        "quality_demo": "https://ddw.9cio.com/quality-demo",
    },
}

# 配置存储位置（可被 DDW 底座 data 目录覆盖）
CONFIG_FILE = os.environ.get(
    "DDW_WEBSITE_CONFIG",
    os.path.join(os.path.dirname(__file__), "site_config.json"),
)


def load_config() -> Dict[str, Any]:
    """读取站点配置（文件优先，缺省回退默认值）。"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 深合并默认配置
            merged = json.loads(json.dumps(DEFAULT_SITE_CONFIG))
            merged.update(data)
            if "theme" in data:
                merged["theme"].update(data["theme"])
            if "company" in data:
                merged["company"].update(data["company"])
            if "pages" in data:
                merged["pages"].update(data["pages"])
            if "links" in data:
                merged["links"].update(data["links"])
            return merged
    except Exception as e:  # noqa: BLE001
        logger.warning("ddw-website config load failed: %s", e)
    return json.loads(json.dumps(DEFAULT_SITE_CONFIG))


def save_config(cfg: Dict[str, Any]) -> None:
    """持久化站点配置。"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        logger.error("ddw-website config save failed: %s", e)
        raise
