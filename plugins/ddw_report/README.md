# DDW Report Plugin v0.1.0

学习/培训场景通用报表插件。所有客户场景（A/B/C/D）都需要。

## 能力

- 学习报告（每日/每周/每月/每年）
- 培训报告（完成情况、考核结果、能力图谱）
- PDF 导出（reportlab + 中文字体）
- 多维度统计（按学科/章节/能力）

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/plugins/ddw-report/user/{user_id}` | 用户学习汇总 |
| GET | `/api/v1/plugins/ddw-report/user/{user_id}/pdf` | 导出 PDF 报告 |
| GET | `/api/v1/plugins/ddw-report/class/overview` | 班级概览 |
| GET | `/api/v1/plugins/ddw-report/trends/{user_id}` | 成绩趋势 |

## 事件订阅

- `training.session.completed` → 失效用户报告缓存
- `training.assessment.completed` → 失效用户报告缓存

## 依赖

- `ddw-training`（读 TrainingSession / TrainingAssessment）
- `core.database`（SQLAlchemy ORM）

## 测试

```bash
pytest plugins/ddw_report/tests/ -v
# 8/8 passed
```
