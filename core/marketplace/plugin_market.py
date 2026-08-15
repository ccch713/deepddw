"""插件市场数据模型 — Pydantic schemas 用于 API 请求/响应。

定义市场列表、分类、评价等数据结构，确保 API 层数据校验。
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 枚举类型
# ---------------------------------------------------------------------------


class PluginCategory(str, Enum):
    """插件分类。"""

    INFRASTRUCTURE = "infrastructure"  # 基础设施
    DATA_ANALYTICS = "data_analytics"  # 数据分析
    AI_TOOLS = "ai_tools"  # AI 工具
    BUSINESS = "business"  # 业务插件
    OTHER = "other"  # 其他


class PluginStatus(str, Enum):
    """插件安装状态。"""

    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class PluginInstallRequest(BaseModel):
    """安装插件请求。"""

    version: Optional[str] = Field(None, description="指定版本（默认最新版）")
    force: bool = Field(False, description="强制重装")


class PluginReviewCreate(BaseModel):
    """创建插件评价请求。"""

    user_id: str = Field(..., description="用户 ID")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: Optional[str] = Field(None, description="评价内容")


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class PluginListingResponse(BaseModel):
    """插件市场列表项响应。"""

    name: str = Field(..., description="插件唯一标识")
    version: str = Field(..., description="当前版本")
    description: str = Field("", description="插件描述")
    author: str = Field("Unknown", description="作者")
    license: str = Field("MIT", description="开源协议")
    category: PluginCategory = Field(PluginCategory.OTHER, description="分类")
    rating: float = Field(0.0, description="平均评分")
    downloads: int = Field(0, description="下载次数")
    status: PluginStatus = Field(PluginStatus.NOT_INSTALLED, description="安装状态")
    enabled: Optional[bool] = Field(None, description="是否启用（已安装时有值）")
    tags: List[str] = Field(default_factory=list, description="标签")
    icon_url: Optional[str] = Field(None, description="图标 URL")
    homepage: Optional[str] = Field(None, description="主页链接")
    engine: str = Field(">=0.1.0", description="引擎版本要求")
    permissions: List[str] = Field(default_factory=list, description="所需权限")
    dependencies: Dict[str, Any] = Field(default_factory=dict, description="依赖关系")
    config_schema: Optional[Dict[str, Any]] = Field(None, description="配置 Schema")


class PluginDetailResponse(PluginListingResponse):
    """插件详情响应（含评价和版本历史）。"""

    reviews: List[PluginReviewResponse] = Field(default_factory=list, description="评价列表")
    versions: List[PluginVersionInfo] = Field(default_factory=list, description="版本历史")


class PluginReviewResponse(BaseModel):
    """插件评价响应。"""

    id: int
    plugin_name: str
    user_id: str
    rating: int
    comment: Optional[str] = None
    created_at: dt.datetime


class PluginVersionInfo(BaseModel):
    """插件版本信息。"""

    version: str
    released_at: Optional[dt.datetime] = None
    changelog: Optional[str] = None


class PluginInstalledResponse(BaseModel):
    """已安装插件响应。"""

    name: str
    version: str
    enabled: bool
    installed_at: dt.datetime
    isolation: str = "inline"


class PluginActionResponse(BaseModel):
    """插件操作结果响应。"""

    success: bool
    message: str
    plugin_name: str
    action: str  # install / uninstall / enable / disable


class PluginMarketStats(BaseModel):
    """市场统计信息。"""

    total_plugins: int = 0
    installed_plugins: int = 0
    enabled_plugins: int = 0
    total_downloads: int = 0
    categories: Dict[str, int] = Field(default_factory=dict)


# 修复循环引用：在定义完所有模型后重新赋值
PluginDetailResponse.model_rebuild()
