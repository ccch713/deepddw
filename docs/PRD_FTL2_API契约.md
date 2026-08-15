# PRD: 列表 API 单一契约规范（铁律2落地）

> 编号：PRD-FTL2-APICONTRACT
> 版本：v1.0
> 日期：2026-08-11
> 优先级：P1（Demo 后第一批，防信封/裸数组混用 bug）
> 关联铁律：铁律2（列表 API 单一契约）
> 关联规范：DDW-代码命名规范与入库规范-20260811.md

---

## 1. 背景与目标

### 1.1 问题
后端列表端点三种返回格式混用：
- `{items:[...], total:N}` 信封（部分新端点）
- 裸数组 `[...]`（部分旧端点）
- map 对象 `{minimax:{...}}`（LLM providers）

2026-08-10 实测：LLM 频道前端期望裸数组，后端返回信封 → "items 不可达"；用户管理前端期望数组，后端返回信封 → 空列表。

### 1.2 目标
- 定义统一契约：列表端点 = `{items:[], total:N}`；单对象 = 裸对象；健康检查 = 裸对象
- 用 Pydantic `ListResponse[T]` 泛型模型强制
- 提供 pytest 契约校验 helper，新端点自动校验

---

## 2. 目录结构

```
ddw-ai-hub/
├── core/
│   └── api/
│       ├── schemas.py           # 新增：ListResponse 泛型模型
│       └── {各端点}.py          # 修改：列表端点返回 ListResponse
├── tests/
│   ├── conftest.py              # 新增：契约校验 fixture
│   └── test_api_contract.py     # 新增：契约一致性测试
└── docs/
    └── API_CONTRACT.md          # 契约文档（一页纸）
```

## 3. 核心模型

```python
# core/api/schemas.py
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
```

```python
# tests/conftest.py 契约校验 helper
def assert_list_response(resp):
    """列表端点契约校验：必须 {items, total}"""
    assert resp.ok, f"请求失败: {resp.status_code}"
    data = resp.json()
    assert "items" in data, f"列表端点缺少 items 字段: {list(data.keys())}"
    assert "total" in data, f"列表端点缺少 total 字段"
    assert isinstance(data["items"], list), "items 必须是数组"
    assert data["total"] == len(data["items"]), "total 必须等于 items 长度"
```

## 4. 契约规则（写入 docs/API_CONTRACT.md）

```markdown
# DDW API 契约规范

## 规则
1. 所有列表端点（GET /xxx/）→ {"items": [...], "total": N}
2. 所有单对象端点（GET /xxx/{id}）→ 裸对象 {...}
3. 健康检查/状态类 → 裸对象（不做信封）
4. 禁止混用：同一端点不能切换格式
5. 分页（未来）：items 返回当前页，total 返回总数

## 例外
- LLM providers 健康检查：保持 map（状态类，规则3）
- 统计类（trend_7d 等）：裸对象（非列表）

## 违反检测
- pytest: assert_list_response() 覆盖所有列表端点
- 新端点开发时必须声明返回 ListResponse[T]
```

## 5. 需要整改的端点（按 ECS 实际）

| 端点 | 当前格式 | 整改为 | 优先级 |
|------|---------|--------|--------|
| GET /api/v1/users/ | 裸数组 | {items,total} | P0 |
| GET /api/v1/admin/plugins | 裸数组 | {items,total} | P0 |
| GET /api/v1/admin/billing/channels | 裸数组 | {items,total} | P1 |
| GET /api/v1/llm/rules | {items,total} | 保持 | ✅ |
| GET /api/v1/llm/providers | map | 保持（状态类） | ✅ 例外 |
| GET /api/v1/llm/fallback | {chain:[]} | 保持（单对象） | ✅ |
| GET /api/v1/users/whitelist | 裸数组 | {items,total} | P1 |
| GET /api/v1/plugins/... 插件端点 | 不定 | 逐个审计 | P1 |

## 6. 测试用例（6 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | GET /users/ | assert_list_response 通过 |
| 2 | GET /admin/plugins | assert_list_response 通过 |
| 3 | GET /users/whitelist | assert_list_response 通过 |
| 4 | GET /llm/rules | assert_list_response 通过 |
| 5 | GET /llm/providers | 允许 map（例外） |
| 6 | 全量端点扫描 | openapi.json 中所有列表路径无裸数组返回（抽样） |

## 7. 验收标准

| # | 维度 | 标准 |
|---|------|------|
| 1 | pytest | 新增 6 条测试全过，全量回归无破坏 |
| 2 | ruff | 零新增 error |
| 3 | 铁律2 | 核心列表端点全部 {items,total} |
| 4 | 兼容 | 前端已兼容信封格式（admin.html 已改） |
| 5 | 安全 | 无回归 |
| 6 | 冒烟 | 5 场景冒烟脚本（含频道列表）通过 |

## 8. 风险

- 前端有多处直接消费裸数组（loadUsers/loadPlugins 等）→ 需要同步改前端解析
- 第三方对接（如经销商页面）可能依赖旧格式 → 逐个确认

## 9. 依赖

- 前端 admin.html / saas-admin.html 同步整改
