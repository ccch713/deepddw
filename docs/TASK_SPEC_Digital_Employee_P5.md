# TASK_SPEC: 数字员工体系 P5 — roles.py 扩展 + 全局权限打通

> **前置条件**：P0 已完成  
> **开发工具**：MiMo Code CLI

---

## P5.1 功能概述

确保 DIGITAL_AGENT 角色在整个 DDW 权限体系中正确运作：认证中间件能识别数字员工 token、权限矩阵覆盖数字员工操作、审计日志记录数字员工行为。

## P5.2 认证中间件适配

在 `core/auth.py` 中确保 current_user 依赖能解析数字员工的 JWT token：

```python
# 数字员工的 JWT payload 应包含：
{
    "sub": "agent:7",           # agent:{id} 格式
    "role": "digital_agent",
    "tenant_id": 1,
    "department_id": 3,
}
```

验证：
1. role == "digital_agent" 时，不检查设备绑定
2. role == "digital_agent" 时，不触发首登改密
3. decision_scope 在运行时通过 agent_id 查询

## P5.3 权限矩阵中间件

```python
# core/permission_guard.py（或在 auth.py 中扩展）

DIGITAL_AGENT_PERMISSIONS = {
    "read": True,          # 读取数据
    "create": False,       # 默认不可创建（由 decision_scope 控制）
    "edit": False,         # 默认不可编辑
    "delete": False,       # 默认不可删除
    "approve": False,      # 默认不可审批
    "initiate_flow": True, # 可发起流程
}

async def check_digital_agent_permission(
    agent_id: int, action: str, db: AsyncSession
) -> bool:
    """检查数字员工是否有某项操作权限。"""
    agent = await db.get(DigitalAgent, agent_id)
    if not agent:
        return False
    scope = agent.decision_scope or []
    return action in scope
```

## P5.4 API 端点（如果需要独立文件）

通常 P5 不需要新端点，只需确保现有端点的权限检查覆盖数字员工角色。

## P5.5 测试用例（4 条）
1. 数字员工角色的 JWT token 可被认证中间件解析
2. 数字员工不触发设备绑定检查
3. decision_scope 外的操作被拒绝
4. 数字员工可发起碳硅协作流程

## P5.6 验收标准
- 数字员工 JWT token 认证通过
- decision_scope 权限执行正确
- 审计日志记录数字员工操作
- 全量测试不回归
- ruff clean

## 禁止事项
- 禁止修改 roles.py（P0 已完成）
- 禁止修改 models.py（P0 已完成）
- 禁止 push
- 禁止引入新依赖
