# TASK_SPEC: 泛微 OA 同步（组织架构/人员/权限）

> 优先级：P0
> 预计工时：3-5 天
> 插件名：ddw_wecom（扩展现有 plugins/ddw_wecom/）
> 状态：待确认（需泛微 E9 API 凭证）

---

## 1. 概述

从泛微 E9 OA 系统同步组织架构、人员信息和权限到 DDW AI 组织模块。
嘉必优客户已使用泛微 E9，签合同前必须完成同步能力。

## 2. 同步内容

| 数据 | 泛微 E9 API | DDW 目标表 |
|------|------------|-----------|
| 部门树 | GET /api/department/list | org_departments |
| 员工列表 | GET /api/hrm/resource/list | org_employees |
| 岗位/职位 | GET /api/position/list | org_employees.title |
| 部门-员工关系 | 含在员工列表中 | org_employees.department_id |

## 3. 前置条件（硬阻塞）

| # | 需要 | 状态 |
|---|------|------|
| 1 | 泛微 E9 的 API 地址（base_url） | 待用户提供 |
| 2 | 泛微 E9 的 OAuth2 凭证（client_id + client_secret） | 待用户提供 |
| 3 | 泛微 E9 的 API 文档（接口参数/返回格式） | 待用户提供 |
| 4 | 嘉必优泛微管理员账号（用于测试） | 待用户提供 |

没有以上信息，无法开发。需要用户提供。

## 4. 同步流程

用户点击"从泛微导入"
-> OAuth2 认证（获取 access_token）
-> 拉取部门树（GET /api/department/list）
-> 逐部门创建/更新 org_departments 记录
-> 拉取员工列表（GET /api/hrm/resource/list）
-> 逐员工创建/更新 org_employees 记录（关联 wecom_id）
-> 显示同步结果（新增 N 人 / 更新 M 人 / 跳过 K 人）

## 5. API 端点

GET    /api/v1/org/wecom/config                     # 获取泛微配置
PUT    /api/v1/org/wecom/config                     # 更新泛微配置
POST   /api/v1/org/wecom/sync-departments           # 同步部门
POST   /api/v1/org/wecom/sync-employees             # 同步员工
POST   /api/v1/org/wecom/sync-all                   # 一键同步全部
GET    /api/v1/org/wecom/sync-history               # 同步记录

## 6. 数据映射

| 泛微字段 | DDW 字段 |
|---------|---------|
| departmentId | wecom_id |
| departmentName | name |
| parentId | 构建部门树（DDW 暂不支持部门层级） |
| resourceId | wecom_id |
| resourceName | name |
| mobile | phone |
| positionName | title |
| departmentId | department_id（通过 wecom_id 关联） |

## 7. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 配置泛微连接 | 测试连接成功 |
| 2 | 同步部门 | 新增 N 个部门到 org_departments |
| 3 | 同步员工 | 新增 M 个员工到 org_employees |
| 4 | 重复同步 | 幂等更新（不重复创建） |
| 5 | 同步历史 | 显示每次同步的结果 |

## 8. 依赖

- 泛微 E9 API 凭证（硬阻塞）
- AI 组织插件（TASK_SPEC_AI_ORG）需先就绪
