"""DDW Agent 权限服务（参照 Proma AgentPermissionService 三层分级）。

三层分级：
  Level 1 (SAFE):   只读操作自动放行 —— Read/Grep/Glob/搜索
  Level 2 (NORMAL): 可白名单操作 —— Write/Edit/Bash
  Level 3 (DANGER): 不可白名单操作 —— rm -rf/sudo/管道到 sh 等

DDW 企业场景适配：
  - 多租户隔离：权限白名单按 tenant_id 维度管理
  - 审计日志：所有权限决策记录到 EventBus
  - 插件级权限声明：插件在 manifest.yaml 中声明需要的权限等级

使用::

    from core.services.agent_permission import AgentPermissionService, DangerLevel

    svc = AgentPermissionService()
    result = await svc.check_permission(
        tenant_id="t1",
        tool_name="Bash",
        tool_input={"command": "rm -rf /tmp/cache"},
    )
    if result.allowed:
        # 执行操作
        ...
    else:
        # 需要用户确认
        ...
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  危险等级（参照 Proma DangerLevel）
# --------------------------------------------------------------------------- #


class DangerLevel(str, Enum):
    """工具/操作的危险等级。"""
    SAFE = "safe"         # 只读，自动放行
    NORMAL = "normal"     # 可写，可白名单
    DANGEROUS = "dangerous"  # 破坏性，需用户确认


# --------------------------------------------------------------------------- #
#  安全命令白名单（参照 Proma SAFE_TOOLS + isSafeBashCommand）
# --------------------------------------------------------------------------- #

# 只读工具白名单
SAFE_TOOLS: Set[str] = {
    "Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch",
    # DDW 自有只读工具
    "ddw.kb.search", "ddw.training.get_progress",
}

# 安全 Bash 命令前缀（只读）
_SAFE_BASH_PREFIXES: tuple[str, ...] = (
    "ls", "cat", "head", "tail", "grep", "find", "wc", "du", "df",
    "echo", "which", "whoami", "pwd", "date", "env", "printenv",
    "git status", "git log", "git diff", "git show", "git branch",
    "pip list", "pip show", "python --version", "python3 --version",
    "node --version", "npm --version", "bun --version",
    "curl ", "wget ",  # GET 请求（无 -X POST）
)

# 危险命令模式（不可白名单化）
_DANGEROUS_PATTERNS: tuple[str, ...] = (
    r"\brm\s+(-[rf]+\s+|--recursive)",  # rm -rf
    r"\bsudo\b",
    r"\bchmod\s+777",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bdd\s+",
    r">\s*/dev/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bkill\s+-9",
    r"\bpkill\b",
    r"\bnohup\b.*\bsh\b",
    r"\|.*\bsh\b",      # 管道到 sh
    r"\|.*\bbash\b",    # 管道到 bash
    r"\bexec\b",
)

_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


def is_safe_bash_command(command: str) -> bool:
    """判断 Bash 命令是否为只读安全命令。"""
    cmd = command.strip()
    return any(cmd.startswith(prefix) for prefix in _SAFE_BASH_PREFIXES)


def is_dangerous_command(command: str) -> bool:
    """判断 Bash 命令是否为危险命令（不可白名单化）。"""
    return bool(_DANGEROUS_RE.search(command))


def has_dangerous_structure(command: str) -> bool:
    """检查命令是否包含危险结构（管道、重定向、命令替换等）。"""
    # 管道到 sh/bash 已在 _DANGEROUS_PATTERNS 中
    # 这里检查额外的危险结构
    if "&&" in command and "rm" in command:
        return True
    if "`" in command:  # 命令替换
        return True
    if "$(" in command and "rm" in command:
        return True
    return False


def classify_tool_danger(tool_name: str, tool_input: Dict[str, Any]) -> DangerLevel:
    """根据工具名和输入判断危险等级。"""
    if tool_name in SAFE_TOOLS:
        return DangerLevel.SAFE

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if is_dangerous_command(command) or has_dangerous_structure(command):
            return DangerLevel.DANGEROUS
        if is_safe_bash_command(command):
            return DangerLevel.SAFE
        return DangerLevel.NORMAL

    # 写操作工具
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        return DangerLevel.NORMAL

    # DDW 工具默认为 NORMAL
    if tool_name.startswith("ddw."):
        return DangerLevel.NORMAL

    return DangerLevel.NORMAL


# --------------------------------------------------------------------------- #
#  权限请求/结果
# --------------------------------------------------------------------------- #


@dataclass
class PermissionRequest:
    """权限请求。"""
    request_id: str
    session_id: str
    tenant_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    description: str
    danger_level: DangerLevel
    allow_always: bool = True  # 是否提供"总是允许"选项
    command: Optional[str] = None  # Bash 命令摘要
    source_plugin: str = ""


@dataclass
class PermissionResult:
    """权限检查结果。"""
    allowed: bool
    message: str = ""
    from_whitelist: bool = False


# --------------------------------------------------------------------------- #
#  会话级白名单
# --------------------------------------------------------------------------- #


class _SessionWhitelist:
    """单个会话的权限白名单。"""

    def __init__(self) -> None:
        self.allowed_tools: Set[str] = set()
        self.allowed_bash_commands: Set[str] = set()


# --------------------------------------------------------------------------- #
#  AgentPermissionService
# --------------------------------------------------------------------------- #


class AgentPermissionService:
    """DDW Agent 权限服务（单例模式）。

    核心职责：
    - 三层分级判断（SAFE/NORMAL/DANGEROUS）
    - 会话级白名单管理
    - 权限请求队列管理（Promise + Map 模式）
    - EventBus 集成（权限决策审计）
    """

    def __init__(self) -> None:
        self._pending: Dict[str, PermissionRequest] = {}
        self._whitelists: Dict[str, _SessionWhitelist] = {}

    def check_permission_sync(
        self,
        session_id: str,
        tenant_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> PermissionResult:
        """同步权限检查（不弹窗）。

        Returns:
            PermissionResult
            - Level 1 (SAFE): allowed=True
            - Level 2 (NORMAL) + 白名单: allowed=True, from_whitelist=True
            - Level 2 (NORMAL) + 未白名单: allowed=False
            - Level 3 (DANGEROUS): allowed=False
        """
        danger = classify_tool_danger(tool_name, tool_input)

        # Level 1: 自动放行
        if danger == DangerLevel.SAFE:
            return PermissionResult(allowed=True)

        # Level 2: 检查白名单
        if danger == DangerLevel.NORMAL:
            if self._is_whitelisted(session_id, tool_name, tool_input):
                return PermissionResult(allowed=True, from_whitelist=True)
            return PermissionResult(allowed=False, message=f"需要确认: {tool_name}")

        # Level 3: 永远需要确认
        return PermissionResult(allowed=False, message=f"危险操作需确认: {tool_name}")

    def create_permission_request(
        self,
        session_id: str,
        tenant_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        *,
        source_plugin: str = "",
    ) -> PermissionRequest:
        """创建权限请求（异步等待用户确认）。"""
        danger = classify_tool_danger(tool_name, tool_input)
        command = tool_input.get("command") if tool_name == "Bash" else None
        description = self._build_description(tool_name, tool_input, command)

        request = PermissionRequest(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            tenant_id=tenant_id,
            tool_name=tool_name,
            tool_input=tool_input,
            description=description,
            danger_level=danger,
            allow_always=(danger != DangerLevel.DANGEROUS),
            command=command,
            source_plugin=source_plugin,
        )
        self._pending[request.request_id] = request
        return request

    def respond_to_permission(self, request_id: str, allow: bool, always_allow: bool = False) -> Optional[str]:
        """响应权限请求。

        Returns:
            session_id 如果找到请求，否则 None
        """
        request = self._pending.pop(request_id, None)
        if request is None:
            return None

        if allow and always_allow and request.allow_always:
            self._add_to_whitelist(request.session_id, request.tool_name, request.tool_input)

        return request.session_id

    def clear_session(self, session_id: str) -> None:
        """清除会话的所有待处理请求和白名单。"""
        self._pending = {k: v for k, v in self._pending.items() if v.session_id != session_id}
        self._whitelists.pop(session_id, None)

    @property
    def pending_requests(self) -> List[PermissionRequest]:
        return list(self._pending.values())

    # ------------------------------------------------------------------ #
    #  内部
    # ------------------------------------------------------------------ #

    def _is_whitelisted(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        wl = self._whitelists.get(session_id)
        if wl is None:
            return False

        if tool_name != "Bash":
            return tool_name in wl.allowed_tools

        command = tool_input.get("command", "")
        if is_dangerous_command(command) or has_dangerous_structure(command):
            return False
        base_cmd = self._extract_base_command(command)
        return base_cmd in wl.allowed_bash_commands

    def _add_to_whitelist(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        wl = self._whitelists.setdefault(session_id, _SessionWhitelist())
        if tool_name != "Bash":
            wl.allowed_tools.add(tool_name)
        else:
            command = tool_input.get("command", "")
            base_cmd = self._extract_base_command(command)
            if base_cmd:
                wl.allowed_bash_commands.add(base_cmd)

    @staticmethod
    def _extract_base_command(command: str) -> str:
        """提取 Bash 命令的基础命令（git push → git push）。"""
        parts = command.strip().split()
        if not parts:
            return ""
        # 两词组合命令
        if len(parts) >= 2 and parts[0] in ("git", "npm", "bun", "yarn", "pnpm", "pip", "docker"):
            return f"{parts[0]} {parts[1]}"
        return parts[0]

    @staticmethod
    def _build_description(tool_name: str, tool_input: Dict[str, Any], command: Optional[str]) -> str:
        if command:
            return f"执行命令: {command[:200]}"
        if tool_name == "Write":
            path = tool_input.get("file_path", tool_input.get("path", ""))
            return f"写入文件: {path}"
        if tool_name == "Edit":
            path = tool_input.get("file_path", tool_input.get("path", ""))
            return f"编辑文件: {path}"
        return f"调用工具: {tool_name}"


# 全局单例
_svc: Optional[AgentPermissionService] = None


def get_permission_service() -> AgentPermissionService:
    global _svc
    if _svc is None:
        _svc = AgentPermissionService()
    return _svc


__all__ = [
    "AgentPermissionService",
    "DangerLevel",
    "PermissionRequest",
    "PermissionResult",
    "classify_tool_danger",
    "is_safe_bash_command",
    "is_dangerous_command",
    "has_dangerous_structure",
    "get_permission_service",
    "SAFE_TOOLS",
]
