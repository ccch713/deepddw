# DDW 问渠学科包（物理化学）

苏格拉底式物理化学学习插件，支持错题本、家长统计等功能。

## 功能特性

- **苏格拉底对话**：AI 教练引导式教学，不直接给答案
- **双角色支持**：物理教练「祁衡」+ 化学教练「林若薇」
- **错题闭环**：答错 → 归档 → 复盘 → 重做
- **钱包计费**：对接 ddw_wallet，按活跃时长计费
- **家长统计**：周报数据源，活跃时长/错题分布/弱项雷达

## 目录结构

```
plugins/ddw_wenqu_tutor/
├── __init__.py          # 插件元信息
├── plugin.py            # PluginBase 实现
├── router.py            # FastAPI 路由（12+ 端点）
├── models.py            # SQLAlchemy 2.0 ORM（9 张表）
├── schemas.py           # Pydantic v2
├── manifest.yaml        # 插件清单
├── config.py            # 环境变量配置
├── prompt/              # Prompt 模块
│   ├── socratic_rules.py
│   ├── format_rules.py
│   ├── physics_coach.py
│   ├── chemistry_coach.py
│   └── token_budget.py
├── services/            # 业务逻辑
│   ├── session.py       # 会话生命周期
│   ├── socratic.py      # 苏格拉底引擎
│   ├── textbook.py      # 教材加载
│   ├── questions.py     # 题库评判
│   ├── wrongbook.py     # 错题本
│   └── parent_stats.py  # 家长统计
├── tests/               # 测试用例
│   ├── conftest.py
│   ├── test_prompt.py
│   ├── test_session.py
│   ├── test_socratic.py
│   ├── test_billing.py
│   ├── test_questions.py
│   └── test_wrongbook.py
├── README.md
└── LICENSE              # Apache-2.0
```

## 配置

环境变量：

```bash
DDW_WENQU_TUTOR_WALLET_BASE=http://127.0.0.1:8500
DDW_WENQU_TUTOR_LLM_GATEWAY=http://127.0.0.1:8500
DDW_WENQU_TUTOR_MODEL=deepseek-v4-flash
DDW_WENQU_TUTOR_TEXTBOOK_ROOT=/opt/wenqu/textbooks
DDW_WENQU_TUTOR_DB_URL=postgresql+asyncpg://...
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /session/start | 开课 |
| POST | /session/{id}/message | 苏格拉底对话 |
| POST | /session/{id}/end | 下课计费 |
| GET | /session/{id} | 会话详情 |
| GET | /textbook/list | 教材列表 |
| POST | /textbook/upload | 上传教材 |
| GET | /questions/list | 真题列表 |
| POST | /questions/submit | 提交答案 |
| GET | /wrongbook/list | 错题本 |
| POST | /wrongbook/{id}/redo | 错题复盘 |
| GET | /parent/stats | 家长统计 |
| GET | /health | 健康检查 |

## 计费规则

- 学习会话：0.2 元/活跃分钟（防挂机：无消息 90s 暂停计时）
- 课件生成：静态 5-10 元/次，视频 20-50 元/次
- 语音交互：0.5 元/分钟

## 开发

```bash
# 运行测试
pytest plugins/ddw_wenqu_tutor/tests/ -q

# 代码检查
ruff check plugins/ddw_wenqu_tutor/ --select=E,W,F
```

## License

Apache-2.0
