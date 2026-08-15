# TASK_SPEC: 插件论坛（企业内部 GitHub）

> 优先级：P1  
> 预计工时：5-7 天  
> 插件名：ddw_plugin_forum  
> 状态：待确认  
> 参考：GitHub Discussions 模型（发布/点赞/评论/需求/闭环/贡献者）

---

## 1. 概述

插件论坛是 DDW 企业内部的协作平台，类似 GitHub 的 Discussions + Issues 功能。
所有用户可查看和发布，公司级管理员有管理权限，superadmin 可见全部内容并可配置 skill 做关键信息筛选。

## 2. 核心功能

| 功能 | 说明 |
|------|------|
| 发布帖/讨论 | 所有登录用户可发布 |
| 评论 | 所有用户可对自己和他人的帖子评论 |
| 点赞 | 所有用户可点赞 |
| 提需求 | 帖子类型 = "需求"（Issue） |
| 需求闭环 | 需求状态：open → in_progress → resolved → closed |
| 讨论 | 帖子类型 = "讨论"（Discussion） |
| 贡献者 | 帖子可添加贡献者（类似 GitHub Contributors） |
| 删帖 | 仅公司级管理员可删帖 |
| 顶帖 | 仅公司级管理员可顶帖 |
| 禁言 | 仅公司级管理员可禁言某用户（在本租户论坛内） |
| 修改 | 仅可修改自己的帖子/评论 |

## 3. 数据模型

### 3.1 帖子（ForumPost）

```python
class ForumPost(Base):
    __tablename__ = "forum_posts"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    author_id: int = Column(Integer, nullable=False)
    plugin_name: str = Column(String(100), nullable=True)     # 关联插件（可选）
    post_type: str = Column(String(20), default="discussion") # discussion / issue / announcement
    title: str = Column(String(300), nullable=False)
    content: str = Column(Text, nullable=False)
    status: str = Column(String(20), default="open")          # open / in_progress / resolved / closed
    is_pinned: bool = Column(Boolean, default=False)
    is_locked: bool = Column(Boolean, default=False)          # 锁定后不可评论
    like_count: int = Column(Integer, default=0)
    comment_count: int = Column(Integer, default=0)
    contributors: list = Column(JSON, default=[])              # 贡献者 user_id 列表
    tags: list = Column(JSON, default=[])                      # 标签
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
    pinned_at: datetime = Column(DateTime, nullable=True)
```

### 3.2 评论（ForumComment）

```python
class ForumComment(Base):
    __tablename__ = "forum_comments"
    
    id: int = Column(Integer, primary_key=True)
    post_id: int = Column(Integer, ForeignKey("forum_posts.id"), nullable=False)
    author_id: int = Column(Integer, nullable=False)
    content: str = Column(Text, nullable=False)
    like_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 3.3 点赞记录（ForumLike）

```python
class ForumLike(Base):
    __tablename__ = "forum_likes"
    
    id: int = Column(Integer, primary_key=True)
    user_id: int = Column(Integer, nullable=False)
    target_type: str = Column(String(20), nullable=False)     # "post" / "comment"
    target_id: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id"),)
```

### 3.4 禁言记录（ForumMute）

```python
class ForumMute(Base):
    __tablename__ = "forum_mutes"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    user_id: int = Column(Integer, nullable=False)
    muted_by: int = Column(Integer, nullable=False)
    reason: str = Column(Text, default="")
    muted_at: datetime = Column(DateTime, default=utcnow)
    unmuted_at: datetime = Column(DateTime, nullable=True)    # null = 仍在禁言中
```

## 4. API 端点

```yaml
# 帖子
GET    /api/v1/forum/posts                          # 列表（?type=discussion|issue&plugin=xxx&status=xxx）
POST   /api/v1/forum/posts                          # 发布（检查禁言）
GET    /api/v1/forum/posts/{id}                     # 详情（含评论）
PUT    /api/v1/forum/posts/{id}                     # 修改（仅作者）
DELETE /api/v1/forum/posts/{id}                     # 删除（仅 company admin / superadmin）
PUT    /api/v1/forum/posts/{id}/pin                 # 顶帖/取消顶帖（仅 company admin）
PUT    /api/v1/forum/posts/{id}/status              # 需求状态变更（open/in_progress/resolved/closed）

# 评论
POST   /api/v1/forum/posts/{id}/comments            # 发评论（检查禁言）
PUT    /api/v1/forum/comments/{id}                   # 修改（仅作者）
DELETE /api/v1/forum/comments/{id}                   # 删除（仅作者 / company admin）

# 点赞
POST   /api/v1/forum/like                            # 点赞/取消点赞（toggle）
# body: { target_type: "post"/"comment", target_id: xxx }

# 贡献者
POST   /api/v1/forum/posts/{id}/contributors         # 添加贡献者
DELETE /api/v1/forum/posts/{id}/contributors/{uid}   # 移除贡献者

# 禁言
POST   /api/v1/forum/mute                            # 禁言（仅 company admin）
DELETE /api/v1/forum/mute/{user_id}                   # 解禁
GET    /api/v1/forum/mutes                            # 禁言列表

# superadmin 全局视图
GET    /api/v1/forum/admin/all-posts                  # superadmin 看所有租户帖子
GET    /api/v1/forum/admin/keywords                   # 关键信息筛选（配置 skill 做分析）
```

## 5. 前端页面

### 5.1 论坛首页（saas-admin.html#/forum）

- 分类 Tab：全部 / 讨论 / 需求 / 公告
- 排序：最新 / 最热 / 置顶优先
- 每个帖子卡片：标题 + 作者 + 类型标签 + 状态标签 + 点赞数 + 评论数 + 关联插件
- 发帖按钮（所有人可见）
- 搜索框

### 5.2 帖子详情

- 帖子内容（Markdown 渲染）
- 贡献者头像列表
- 评论区（按时间排序）
- 点赞按钮
- 需求状态变更（仅作者/管理员）
- 操作：
  - 作者：编辑 / 删除
  - 管理员：置顶 / 锁定 / 删除 / 禁言作者

### 5.3 superadmin 视图

- 跨租户帖子聚合（按租户分组）
- 关键词筛选（可配置 skill 做 NLP 分析，提取高频需求/bug）

## 6. 权限矩阵

| 操作 | member | dept admin | owner | superadmin |
|------|--------|-----------|-------|-----------|
| 查看帖子 | ✅ | ✅ | ✅ | ✅（跨租户） |
| 发帖 | ✅ | ✅ | ✅ | ✅ |
| 评论 | ✅ | ✅ | ✅ | ✅ |
| 点赞 | ✅ | ✅ | ✅ | ✅ |
| 修改自己帖子 | ✅ | ✅ | ✅ | ✅ |
| 删除别人帖子 | ❌ | ❌ | ✅ | ✅ |
| 置顶 | ❌ | ❌ | ✅ | ✅ |
| 禁言 | ❌ | ❌ | ✅ | ✅ |
| 需求状态变更 | ✅（自己的） | ✅ | ✅ | ✅ |
| 添加贡献者 | ✅ | ✅ | ✅ | ✅ |
| 关键词筛选 | ❌ | ❌ | ❌ | ✅ |

## 7. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 发帖 | 新帖出现在列表中 |
| 2 | 评论 | 帖子详情页显示评论 |
| 3 | 点赞 | 点赞数 +1，再点 -1 |
| 4 | 提需求 | 类型=issue，有状态标签 |
| 5 | 需求闭环 | 状态从 open → resolved，标签变绿 |
| 6 | 贡献者 | 添加后头像出现在帖子详情 |
| 7 | 删帖 | owner 可删，member 不可 |
| 8 | 禁言 | 被禁言用户发帖/评论被拦截 |
| 9 | superadmin | 可看到所有租户帖子 |

## 8. 依赖

- 无外部依赖，独立插件
- 复用 ddw-themes CSS 变量保持配色一致
