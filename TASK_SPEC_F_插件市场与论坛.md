# TASK_SPEC · F · 插件市场改版 + 内部插件论坛

> 来源：用户测试反馈 14/15 条（2026-08-10）
> 状态：**今晚 0 点 MiMo 夜间开发**（cron 派发）· 明早验收交付
> 作者：Hermes（架构）· 执行：MiMo Code CLI · 质量：AHE Loop（写一个验一个）

## 一、需求与验收

### 第 14 条（已完成，无需开发）
- ✅ 仪表盘"已发现插件"→"插件市场总数"（已部署）

### 第 15 条（本 spec）
插件管理页改版为"插件市场"风格 + 每个插件一个**内部子论坛**：

1. **插件名称**：显示中文名（大字），英文名放中文名下面（字号小、不加粗、颜色淡=说明栏同色）
2. **行业分类**："制造业"、"医疗"、"通用"等分类徽标
3. **每个插件显示**：已安装 xx 次、★ 星级、版本更新日期、反馈（进论坛入口）
4. **内部论坛**：所有有账号的用户都能从插件市场点插件名进入该插件的子论坛；子论坛首页含：插件说明页、版本更新日期、反馈、星、发帖求助、热议贴
5. 风格：类似 GitHub 但**不要太 GitHub**（温和的企业内部风格，沿用 admin 主题）

**验收标准**：
- A. 插件管理页：77 个插件全部显示中文名+英文名+分类+安装次数+星级+版本更新日期+反馈入口
- B. 分类至少 5 类（制造业/医疗/通用/…），每插件有分类（默认"通用"）
- C. 点插件名/反馈 → 进入该插件子论坛页，含：说明、版本更新日期、星（1-5 打分）、发帖求助、热议贴、回复列表
- D. 发帖/回复/打分需要登录（复用 JWT），所有账号可见
- E. pytest 新增 ≥10 条；全量回归通过；部署 ECS 浏览器实测

## 二、目录结构与改动清单

```
core/database/models.py      # + PluginMeta / ForumThread / ForumReply / PluginStar 4 个模型
core/api/forum.py            # 新建：论坛 API router（prefix /api/v1/forum）
core/api/admin.py            # /admin/plugins 扩展（title/category/installs/stars/updated_at/thread_count）
core/main.py                 # include forum_router
scripts/init_plugin_meta.py  # 新建：扫描 plugins/*/manifest.yaml 初始化 plugin_meta（幂等）
frontend/plugin-market.html  # 新建：插件市场页（或改造 admin.html plugins 频道）
frontend/plugin-forum.html   # 新建：插件子论坛页（?plugin=ddw-xxx）
frontend/admin.html          # 插件管理频道链接到 plugin-market.html（或内嵌改版）
tests/test_forum.py          # 新建：论坛 API 测试 ≥10 条
```

**禁止改动**：现有登录/认证流程、租户隔离中间件、插件加载逻辑、partner 插件（只读）。

## 三、数据模型（Pydantic + SQLAlchemy）

### PluginMeta（插件元数据表）
```python
class PluginMeta(Base):
    __tablename__ = "plugin_meta"
    plugin_name: str = mapped_column(String(100), primary_key=True)  # 目录名/英文名
    title: str = mapped_column(String(200), default="")              # 中文名
    category: str = mapped_column(String(50), default="通用")        # 行业分类
    installs: int = mapped_column(Integer, default=0)                # 安装次数
    stars: float = mapped_column(Float, default=0.0)                 # 平均星（0-5）
    star_count: int = mapped_column(Integer, default=0)              # 评分人数
    updated_at: str = mapped_column(String(20), default="")          # 版本更新日期 YYYY-MM-DD
```

### ForumThread（帖子）
```python
class ForumThread(Base):
    __tablename__ = "forum_threads"
    id, plugin_name(索引), title, content(Text), author_id, author_name,
    views(int 默认0), replies_count(int 默认0),
    is_pinned(bool 默认False), is_hot(bool 默认False),   # 热议贴标记
    created_at, updated_at
```

### ForumReply（回复）
```python
class ForumReply(Base):
    __tablename__ = "forum_replies"
    id, thread_id(索引), author_id, author_name, content(Text), created_at
```

### PluginStar（插件评分，唯一约束 plugin_name+user_id）
```python
class PluginStar(Base):
    __tablename__ = "plugin_stars"
    id, plugin_name(索引), user_id, stars(int 1-5), created_at
    __table_args__ = (UniqueConstraint("plugin_name", "user_id", name="uq_plugin_star_user"),)
```

## 四、API 端点表

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/v1/admin/plugins | 扩展：每项 + title/category/installs/stars/star_count/updated_at/thread_count | admin |
| GET | /api/v1/forum/plugins | 插件论坛列表（含标题/分类/星/热议数/最新贴） | 登录 |
| GET | /api/v1/forum/plugins/{name} | 插件论坛首页：说明/版本/星/热议贴(前5)/最新贴(前10) | 登录 |
| POST | /api/v1/forum/plugins/{name}/star | {stars:1-5} 打分（upsert）→ 更新 plugin_meta 平均星 | 登录 |
| GET | /api/v1/forum/plugins/{name}/threads?sort=new\|hot&page=1 | 帖子列表 | 登录 |
| POST | /api/v1/forum/plugins/{name}/threads | {title, content} 发帖 → 回复数+1 计数 | 登录 |
| GET | /api/v1/forum/threads/{id} | 帖子详情+回复列表（views+1） | 登录 |
| POST | /api/v1/forum/threads/{id}/replies | {content} 回复 → thread.replies_count+1 | 登录 |
| POST | /api/v1/forum/threads/{id}/pin | 管理员置顶/取消（is_pinned） | admin |
| GET | /api/v1/forum/search?q= | 帖子搜索（title/content LIKE） | 登录 |

**返回规范（铁律）**：列表一律**裸数组**（禁 items 信封）；分页返回 {items:[...], total:N, page:N} 仅当明确需要分页时用，前端按实际解析。

**分类初始化**（init_plugin_meta.py 幂等，已知映射，未列出的默认"通用"）：
```
制造业: ddw_bid_writer, ddw_capa_workflow, ddw_chem_safety, ddw_sop_engine(如存在)...
医疗: ddw_clinic_cs, ddw_dental_*, ddw_clinic_*(含 clinic/dental/口腔 关键词)
通用: 其余全部
```
（开发时按插件目录名关键词归类：bid/制造/工厂/设备→制造业；clinic/dental/口腔/医疗→医疗；其余→通用；后续可在页面/DB 手工调整）

## 五、前端页面设计

### plugin-market.html（插件市场）
- 复用 admin.html 的 theme.css + 侧边栏结构（无 emoji、字号 16px）
- 顶部：搜索框 + 分类筛选按钮（全部/制造业/医疗/通用…）
- 插件卡片网格（不是表格，不要太 GitHub）：
  ```
  [中文名]                    ★4.2 (12)   [制造业]
  ddw-bid-writer             已安装 3 次 · 更新 2026-08-01 · 反馈 5
  ```
  - 中文名（16px 粗体）→ 点击进子论坛；英文名（12px 淡色）在其下
  - 星：★ 数字（橙色）；分类：小徽标
  - "已安装 x 次 · 更新日期 · 反馈(n)" 一行淡色小字
- 点卡片任意处 → plugin-forum.html?plugin=ddw-xxx

### plugin-forum.html（插件子论坛）
- 头部：返回市场 + 插件中文名+英文名 + 分类徽标 + ★ 打分（1-5 星可点）+ 平均星
- Tab/区块：**插件说明**（description）/ **版本更新**（updated_at）/ **反馈**（帖子列表）
- 帖子列表：标题 + 作者 + 时间 + 回复数 + 浏览量；**热议贴**置顶区（is_hot 或回复≥5 标🔥）
- 「发帖求助」按钮 → 弹窗表单（标题+内容）→ POST 后刷新
- 帖子详情：展开显示内容 + 回复列表 + 回复框

## 六、测试用例（≥10 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | 未登录访问 forum 列表 | 401 |
| 2 | 登录后 GET /forum/plugins | 200 + 裸数组 + 每项含 title/category |
| 3 | GET /forum/plugins/{name} 不存在的插件 | 200 + 默认空数据（或 404，二选一，文档注明） |
| 4 | 打分 1-5 | 200 + plugin_meta.stars 更新正确 |
| 5 | 重复打分（upsert） | 200 + star_count 不重复增加 |
| 6 | 打分越界（0 或 6） | 422 |
| 7 | 发帖 | 200 + thread 创建 + 列表可见 |
| 8 | 发帖内容为空 | 422 |
| 9 | 回复帖子 | 200 + replies_count+1 |
| 10 | 帖子详情 views+1 | 两次 GET 后 views 递增 |
| 11 | 置顶（admin） | 200 + is_pinned=True；非 admin 403 |
| 12 | /admin/plugins 返回 title/category/installs/stars | 字段齐全 + 全量 77+ |

## 七、开发顺序

1. models.py 4 模型 → init_db 建表
2. scripts/init_plugin_meta.py（幂等扫描 manifest：title=display_name||name、category 按关键词、installs=0、updated_at=manifest mtime）→ 运行初始化
3. core/api/forum.py 全部端点 + core/main.py include
4. admin.py /plugins 扩展（join plugin_meta + forum_threads 计数）
5. 测试 12 条 → ruff + pytest 全量回归
6. 前端 plugin-market.html + plugin-forum.html（复用 theme.css 侧边栏）
7. AHE Loop：每模块 ruff + pytest → 全量 → 部署 ECS → curl 验证 → 浏览器实测

## 八、禁止事项

- 禁新依赖（纯 FastAPI+SQLAlchemy+内置）
- 禁改登录/租户隔离/插件加载逻辑
- 禁改 partner 插件
- 论坛数据**不按租户隔离**（内部论坛全局共享，所有账号可见）
- 列表端点禁 items 信封（除明确分页场景）
