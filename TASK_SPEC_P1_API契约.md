# TASK_SPEC：列表 API 单一契约（铁律2落地）

> 优先级：P1（Demo 后第一批）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联 PRD：docs/PRD_FTL2_API契约.md
> 关联铁律：铁律2

---

## 一、背景与目标

后端列表端点三种返回格式混用（{items,total} 信封 / 裸数组 / map），2026-08-10 实测 LLM 频道"items 不可达"、用户管理空列表。

目标：所有列表端点统一 `{items:[], total:N}`；单对象裸返回；提供 ListResponse 泛型模型 + 测试 helper。

## 二、目录结构

```
ddw-ai-hub/
├── core/
│   └── api/
│       ├── schemas.py           # 新增：ListResponse 泛型模型
│       ├── users.py             # 修改：返回 ListResponse
│       ├── admin.py             # 修改：plugins/channels 返回 ListResponse
│       └── llm.py               # 修改：rules 保持信封（已符合）
├── tests/
│   ├── conftest.py              # 新增：assert_list_response helper
│   └── test_api_contract.py     # 新增：6 条测试
└── docs/
    └── API_CONTRACT.md          # 新增：契约文档
```

## 三、核心代码

### 3.1 core/api/schemas.py（新增）

```python
"""API 统一契约模型。所有列表端点必须返回 ListResponse。"""
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
```

### 3.2 tests/conftest.py（新增 helper）

```python
def assert_list_response(resp):
    """列表端点契约校验：必须 {items, total}"""
    assert resp.ok, f"请求失败: {resp.status_code}"
    data = resp.json()
    assert "items" in data, f"列表端点缺少 items 字段: {list(data.keys())}"
    assert "total" in data, "列表端点缺少 total 字段"
    assert isinstance(data["items"], list), "items 必须是数组"
    assert data["total"] == len(data["items"]), "total 必须等于 items 长度"
```

### 3.3 端点整改

| 端点 | 当前 | 改为 |
|------|------|------|
| GET /api/v1/users/ | 裸数组 | {items,total} |
| GET /api/v1/admin/plugins | 裸数组 | {items,total} |
| GET /api/v1/admin/billing/channels | 裸数组 | {items,total} |
| GET /api/v1/users/whitelist | 裸数组 | {items,total} |
| GET /api/v1/llm/rules | 已信封 | 保持 ✅ |

注意：改后端时同步检查前端解析逻辑（admin.html loadUsers/loadPlugins/loadWhitelist/loadChannels 已兼容信封格式则无需改前端；若前端有 `Array.isArray(data)` 分支需同步改）。

## 四、测试用例（6 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | GET /users/ | assert_list_response 通过 |
| 2 | GET /admin/plugins | assert_list_response 通过 |
| 3 | GET /users/whitelist | assert_list_response 通过 |
| 4 | GET /llm/rules | assert_list_response 通过 |
| 5 | GET /llm/providers | 允许 map（例外，健康检查类） |
| 6 | GET /admin/billing/channels | assert_list_response 通过 |

## 五、验收标准

| # | 维度 | 标准 |
|---|------|------|
| A | pytest | 新增 6 条全过，全量回归 123+ 无破坏 |
| B | ruff | 零新增 error |
| C | 铁律2 | 核心列表端点全部 {items,total} |
| D | 前端兼容 | 管理后台频道列表正常显示（无"items 不可达"） |
| E | 冒烟 | 5 场景冒烟通过 |

## 六、红线

1. LLM providers 健康检查保持 map（例外），不改
2. 先改后端再改前端（如需），不要只改前端掩盖
3. commit：`refactor(api): 列表端点统一items信封契约 [LLM: mimo-code]`，不 push
4. 不要动 ECS 上的文件
