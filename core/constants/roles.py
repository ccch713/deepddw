"""角色单一权威来源。所有角色判断必须引用本文件，禁止硬编码。

兼容 Python 3.9（StrEnum 在 3.11+ 才可用）。我们用 str 子类实现等价语义：
- Role.X == "x" 为 True
- Role.X in {Role.Y, Role.Z} 正常工作
- str(Role.X) == "x"
"""


class Role(str):
    """角色字符串类型（str 子类，Python 3.9 兼容 StrEnum 语义）。"""

    SUPERADMIN = "superadmin"
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    PARTNER = "partner"
    FINANCE = "finance"
    AUDITOR = "auditor"
    DIGITAL_AGENT = "digital_agent"  # P0 新增：数字员工角色


# 角色白名单集合（frozenset 保证只读语义）
ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER, Role.ADMIN})
PLUGIN_MANAGE_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER})
FINANCE_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER, Role.FINANCE})

# P0 新增：人类角色 vs 数字员工角色分离
HUMAN_ROLES = frozenset({
    Role.SUPERADMIN, Role.OWNER, Role.ADMIN,
    Role.MEMBER, Role.PARTNER, Role.FINANCE, Role.AUDITOR,
})
DIGITAL_ROLES = frozenset({Role.DIGITAL_AGENT})
ALL_ROLES = HUMAN_ROLES | DIGITAL_ROLES

ROLE_VALUES = [
    Role.SUPERADMIN,
    Role.OWNER,
    Role.ADMIN,
    Role.MEMBER,
    Role.PARTNER,
    Role.FINANCE,
    Role.AUDITOR,
    Role.DIGITAL_AGENT,
]


__all__ = [
    "Role",
    "ADMIN_ROLES",
    "PLUGIN_MANAGE_ROLES",
    "FINANCE_ROLES",
    "HUMAN_ROLES",
    "DIGITAL_ROLES",
    "ALL_ROLES",
    "ROLE_VALUES",
]
