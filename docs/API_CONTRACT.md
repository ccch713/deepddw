# API 契约 v1.0

> 版本：v1.0
> 生效日期：2026-08-11
> 关联铁律：铁律2（列表端点统一信封）

---

## 一、契约原则

1. **列表统一信封** — 所有返回集合的端点必须返回 `{items: [], total: N}` 格式
2. **单对象裸返回** — 返回单个资源的端点直接返回对象，不套信封
3. **map 仅限健康检查** — 仅 `/llm/providers` 等健康检查类端点允许返回 map 格式

---

## 二、ListResponse 模型

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
```

位置：`core/api/schemas.py`

---

## 三、端点清单

| 端点 | 方法 | 返回类型 | 备注 |
|------|------|----------|------|
| `/api/v1/users/` | GET | `{items, total}` | 用户列表 |
| `/api/v1/users/whitelist` | GET | `{items, total}` | 白名单列表 |
| `/api/v1/admin/plugins` | GET | `{items, total}` | 插件列表 |
| `/api/v1/admin/billing/channels` | GET | `{items, total}` | 渠道商列表 |
| `/api/v1/llm/rules` | GET | `{items, total}` | 路由规则列表 |
| `/api/v1/llm/providers` | GET | map | 健康检查（例外） |
| `/api/v1/llm/fallback` | GET | 单对象 | 回退链 |
| `/api/v1/admin/overview` | GET | 单对象 | 用量概览 |
| `/api/v1/admin/billing` | GET | 单对象 | 套餐信息 |

---

## 四、违规处理

- 新增列表端点若返回裸数组或 map，CI 测试将拦截
- `assert_list_response` helper 用于自动化校验
- 红线：不得修改 `/llm/providers` 的 map 返回格式

---

## 五、变更记录

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0 | 2026-08-11 | 初始版本，统一 5 个列表端点为 {items, total} 信封 |
