"""DDW Tool 定义接口（SDK §2.1）

继承 Plugin_SDK_接口规范 v1.0 §2.1。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParamDef:
    """工具参数定义。"""
    name: str
    type: str               # "string" | "integer" | "boolean" | "object" | "array"
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None  # 可选枚举


@dataclass
class ToolDefinition:
    """工具定义（Plugin SDK §2.1）。"""
    name: str                          # 工具名（全局唯一）
    description: str                   # 中文描述（≤250字符）
    parameters: list[ParamDef] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)

    # 安全门
    is_read_only: bool = False         # 只读工具 → 可跳过 ReadBeforeWrite
    requires_read_before_write: bool = True
    max_result_chars: int = 50_000     # Token L1 限制（对齐 token_limits.l1_single_result）
    is_idempotent: bool = False        # 幂等工具可安全重试

    # 版本管理
    version: int = 1
    replaces: str | None = None        # 替代的旧工具名（旧工具自动禁用）

    # 运行时状态（不参与 hash）
    enabled: bool = True

    def __post_init__(self) -> None:
        if len(self.description) > 250:
            raise ValueError(f"工具描述超 250 字符: {len(self.description)}")
        if not self.name.startswith("ddw."):
            # 强制前缀规范
            self.name = f"ddw.{self.name}"

    def to_dict(self) -> dict:
        """导出为 dict（用于 manifest.yaml 序列化）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name, "type": p.type,
                    "description": p.description, "required": p.required,
                    **({"default": p.default} if p.default is not None else {}),
                    **({"enum": p.enum} if p.enum else {}),
                }
                for p in self.parameters
            ],
            "permissions": self.required_permissions,
            "is_read_only": self.is_read_only,
            "requires_read_before_write": self.requires_read_before_write,
            "max_result_chars": self.max_result_chars,
            "is_idempotent": self.is_idempotent,
            "version": self.version,
            **({"replaces": self.replaces} if self.replaces else {}),
        }
