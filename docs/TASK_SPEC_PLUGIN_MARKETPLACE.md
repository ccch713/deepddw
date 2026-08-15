# TASK_SPEC: 插件市场（SaaS 版 + 试用 + 上传）

> 优先级：P1  
> 预计工时：3-4 天  
> 插件名：ddw_plugin_market（扩展现有 core/marketplace/）  
> 状态：待确认

---

## 1. 概述

插件市场是 DDW 所有用户浏览、试用、启用插件的统一入口。扩展现有 marketplace 模块，增加：
- **全员可见**：所有角色（owner/admin/member）均可浏览
- **员工试用**：员工可试用未购买的插件，试用期 15 天
- **上传自制插件**：所有用户均可上传，平台收取 15% 费率
- **试用反馈**：管理员可看到试用员工的使用频率和 token 消耗

## 2. 数据模型（扩展现有 marketplace models）

### 2.1 插件试用记录（PluginTrial）

```python
class PluginTrial(Base):
    __tablename__ = "plugin_trials"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    plugin_name: str = Column(String(100), nullable=False)
    user_id: int = Column(Integer, nullable=False)            # 试用员工
    trial_start: datetime = Column(DateTime, default=utcnow)
    trial_end: datetime = Column(DateTime, nullable=False)    # 默认 = trial_start + 15天
    status: str = Column(String(20), default="active")        # active / expired / converted
    usage_count: int = Column(Integer, default=0)             # 调用次数
    token_consumed: int = Column(Integer, default=0)          # token 消耗
    created_at: datetime = Column(DateTime, default=utcnow)
```

### 2.2 用户上传插件（UserPlugin）

```python
class UserPlugin(Base):
    __tablename__ = "user_plugins"
    
    id: int = Column(Integer, primary_key=True)
    uploader_id: int = Column(Integer, nullable=False)
    uploader_tenant_id: int = Column(Integer, nullable=False)
    name: str = Column(String(100), nullable=False)
    display_name: str = Column(String(100), nullable=False)
    description: str = Column(Text, default="")
    version: str = Column(String(20), default="1.0.0")
    category: str = Column(String(50), default="other")
    price_cny: float = Column(Float, default=0.0)             # 定价（0=免费）
    fee_rate: float = Column(Float, default=0.15)             # 平台费率（固定15%）
    status: str = Column(String(20), default="pending_review") # pending_review / published / rejected
    download_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=utcnow)
```

## 3. 试用流程

```
员工点击"试用" 
→ 创建 PluginTrial 记录（trial_end = now + 15天）
→ 安装插件（status=enabled）
→ 15天到期 → 员工界面弹窗"试用期到期，请联系管理员增购"
→ 管理员看到：该插件有 N 个试用员工，显示 姓名/部门/使用频率/Token
```

## 4. 上传自制插件流程

```
用户点击"上传插件"
→ 显示合规提示页面（红字）：
   "⚠️ 插件市场须知
    1. 平台收取 15% 服务器资源费及开票税点
    2. 个人所得税依法代扣代缴（依据《个人所得税法》第八条）
    3. 插件审核通过后方可上架
    4. 上传即视为同意以上条款"
→ 用户勾选"我已阅读并同意"
→ 上传插件包（ZIP / YAML）
→ 后端存入 pending_review 状态
→ superadmin 审核 → published / rejected
```

## 5. API 端点

```yaml
# 浏览（所有用户）
GET    /api/v1/marketplace/plugins                    # 列表（含已安装/可试用状态）
GET    /api/v1/marketplace/plugins/{name}             # 详情

# 安装/启用/停用（扩展现有）
POST   /api/v1/marketplace/{name}/install             # 安装
POST   /api/v1/marketplace/{name}/enable              # 启用
POST   /api/v1/marketplace/{name}/disable             # 停用

# 试用（员工级）
POST   /api/v1/marketplace/{name}/trial               # 开始试用（15天）
GET    /api/v1/marketplace/trials                     # 我的试用列表

# 试用统计（管理员级）
GET    /api/v1/marketplace/trials/overview             # 试用概览（按插件聚合）
GET    /api/v1/marketplace/trials/{plugin_name}        # 某插件的试用员工列表

# 上传自制插件（所有用户）
POST   /api/v1/marketplace/upload                     # 上传插件包
GET    /api/v1/marketplace/my-uploads                  # 我上传的插件列表
```

## 6. 前端页面

### 6.1 插件列表页（saas-admin.html#/plugins）

- 卡片网格展示所有可用插件
- 每个卡片：插件名 + 描述 + 分类标签 + 安装状态
- 状态标识：
  - 已安装已启用 → 绿色"已启用"
  - 已安装已停用 → 灰色"已停用"
  - 可试用 → 蓝色"试用（剩余 N 天）"
  - 已过期试用 → 橙色"试用到期"
- 操作：
  - 已启用：停用
  - 已停用：启用
  - 可试用：开始试用（弹窗确认）
  - 试用到期："请联系管理员增购"

### 6.2 上传插件页

- 合规提示红字（固定在页面顶部）
- 上传区域：拖拽或点击上传 ZIP/YAML
- 填写：名称、描述、分类、定价
- 提交 → pending_review

### 6.3 管理员试用统计

- 表格：插件名 / 试用员工数 / 总调用次数 / 总 token 消耗
- 点击展开：员工姓名 / 部门 / 使用频率（次/天）/ Token（/天）

## 7. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 员工浏览插件市场 | 全员可见所有插件 |
| 2 | 开始试用 | 创建 15 天试用记录 |
| 3 | 试用到期弹窗 | 到期后弹窗提示 |
| 4 | 管理员试用统计 | 看到试用员工/频率/token |
| 5 | 上传页面合规提示 | 红字 15% 费率 + 法律提示 |
| 6 | 上传插件 | 状态=pending_review |

## 8. 依赖

- 现有 core/marketplace/ 模块扩展
- llm_usage_records 需关联 plugin_trial_id
