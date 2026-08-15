"""DDW AI Hub 插件 Git 仓库自动发布模块。

支持 Gitea 和 GitHub 双目标，当插件更新时自动推送到 Git 仓库。
"""

from core.marketplace.publisher.git_publisher import GitPublisher
from core.marketplace.publisher.gitea_client import GiteaClient
from core.marketplace.publisher.github_client import GitHubClient
from core.marketplace.publisher.release_manager import ReleaseManager

__all__ = [
    "GitPublisher",
    "GiteaClient",
    "GitHubClient",
    "ReleaseManager",
]
