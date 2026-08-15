# Phase 1 补充调研：企业系统 API 对接生态全景

> 日期：2026-07-13
> 目的：摸清国内主流 ERP/MES/CRM/SRM/OA/BI 厂商的 API 开放程度和 Python 对接成熟度
> 结论：这决定了 DDW 插件组合式架构中"适配器插件"的可行性和优先级

---

## 一、核心发现

### 没有一个开源项目能覆盖所有厂商的 API 对接

GitHub 上不存在"一个项目搞定用友+金蝶+鼎捷+SAP+管家婆"的适配器。每个厂商的 API 协议、认证方式、数据格式完全不同。这意味着：

**DDW 的适配器插件必须逐个厂商开发，每个厂商一个独立插件。**

### 各厂商 API 开放程度差异极大

| 厂商 | API 开放度 | Python SDK | 对接难度 | 优先级建议 |
|:-----|:----------:|:----------:|:--------:|:----------:|
| **钉钉/飞书/企微** | ⭐⭐⭐⭐⭐ | 社区完善 | 低 | **P0（V1 必做）** |
| **用友 U8** | ⭐⭐⭐⭐ | 社区有 | 中 | P1 |
| **金蝶云星空** | ⭐⭐⭐⭐ | 社区有 | 中 | P1 |
| **SAP** | ⭐⭐⭐ | PyRFC（已弃维护） | 高 | P2 |
| **泛微 OA** | ⭐⭐⭐ | 无官方 | 中 | P1 |
| **致远 OA** | ⭐⭐⭐ | GitHub 有 | 中 | P2 |
| **纷享销客 CRM** | ⭐⭐⭐⭐ | 社区有 | 低 | P2 |
| **鼎捷 ERP** | ⭐⭐ | 无 | 高 | P2 |
| **管家婆** | ⭐ | 无 | 极高 | P3（暂不考虑） |
| **速达** | ⭐⭐ | 开源 ERP | 高 | P3 |
| **帆软 FineReport** | ⭐⭐ | JDBC | 中 | P2 |

---

## 二、逐厂商详细分析

### A. 身份源（P0 — V1 必做）

#### 钉钉开放平台
- **API 文档**: https://open.dingtalk.com/
- **认证方式**: OAuth2.0 + AppKey/AppSecret
- **Python SDK**: `dingtalk-sdk`（社区维护，pip 可装）
- **核心能力**: 组织架构同步、用户信息、角色、通讯录
- **对接难度**: ⭐ 低（文档完善，社区活跃）

#### 飞书开放平台
- **API 文档**: https://open.feishu.cn/
- **认证方式**: OAuth2.0 + AppID/AppSecret
- **Python SDK**: `lark-oapi`（飞书官方，pip 可装）
- **核心能力**: 组织架构、用户、角色、部门
- **对接难度**: ⭐ 低（官方 SDK 质量高）

#### 企业微信
- **API 文档**: https://developer.work.weixin.qq.com/
- **认证方式**: OAuth2.0 + CorpID/Secret
- **Python SDK**: `wework-sdk`（社区维护）
- **核心能力**: 通讯录、用户、部门、标签
- **对接难度**: ⭐ 低

#### Casdoor（IAM 参考实现）
- **GitHub**: casdoor/casdoor（13,923 ⭐，Apache 2.0）
- **核心价值**: 已实现钉钉/飞书/企微/LDAP/AD 的身份源集成
- **DDW 参考**: 可借鉴其身份源适配器的接口设计模式
- **不直接用的原因**: Casdoor 是 Go 语言，DDW 是 Python 栈

---

### B. ERP 系统（P1 — FDE 阶段按客户做）

#### 用友 U8
- **开放平台**: u8open.yonyou.com
- **3 种对接方式**:
  1. **OpenAPI**（外网 HTTPS，JSON）— 最简单，但不支持关联生单
  2. **EAI**（内网 HTTP，XML）— 中等复杂度
  3. **API**（内网 COM，需装 U8 客户端）— 最强大，支持事务和关联生单
- **Python 对接**: 有社区教程（CSDN 多篇），无官方 Python SDK
- **用户权限**: U8 有完整的用户/角色/权限体系，可通过 OpenAPI 查询
- **对接难度**: ⭐⭐⭐ 中（API 收费，需购买开放平台授权）
- **GitHub 成果**: 无成熟的开源 Python 适配器

#### 金蝶云星空
- **开放平台**: open.kingdee.com（K3Cloud WebAPI）
- **认证方式**: 账号密码登录 + appID/appSecret
- **Python 对接**: 金蝶社区有完整教程（8 篇系列文章），Python requests 即可
- **开源项目**: `Hamster.K3Cloud.WebAPI.ServerExtend`（C#，简化单据操作）
- **用户权限**: 星空有完整的组织架构/用户/角色体系
- **对接难度**: ⭐⭐⭐ 中（WebAPI 文档可读性一般，社区教程弥补）
- **GitHub 成果**: 无成熟的 Python 适配器，但 CSDN 教程可直接参考

#### SAP
- **RFC/BAPI**: SAP/PyRFC（GitHub，已弃维护，437 commits）
- **pyrfc**: pip install pyrfc（需先装 SAP NW RFC SDK）
- **用户权限**: SAP 有完整的权限对象/角色体系（SU01/SUIM）
- **对接难度**: ⭐⭐⭐⭐ 高（需 SAP 账号下载 SDK，中文乱码问题）
- **GitHub 成果**: PyRFC 已归档，社区维护的 fork 存在

#### 鼎捷 ERP（Tiptop/T100/GP）
- **对接方式**: WebService（4GL 编写服务端）
- **Python 对接**: 无成熟方案，主要是 Java/C# 生态
- **对接难度**: ⭐⭐⭐⭐ 高（需要鼎捷实施人员配合）
- **GitHub 成果**: 无

#### 管家婆
- **API 开放度**: 极低，无公开 API 文档
- **对接方式**: 主要是数据库直连（非官方）
- **对接难度**: ⭐⭐⭐⭐⭐ 极高（无 API，只能直连数据库）
- **GitHub 成果**: 无

#### 速达 ERP
- **开源 ERP**: 速达荣耀 Open（sdengineer.cn），源码开放
- **API**: 支持 API 数据接口
- **对接难度**: ⭐⭐⭐ 中
- **GitHub 成果**: 速达荣耀开源版可参考

---

### C. OA 系统（P1 — FDE 阶段按客户做）

#### 泛微 OA（E-Cology/E9）
- **API 文档**: e-cloudstore.com/ec/api/applist/
- **认证方式**: AppID + 私钥签名
- **Python 对接**: CSDN 有多篇实战教程
- **核心能力**: 流程审批、用户信息、组织架构、表单数据
- **对接难度**: ⭐⭐⭐ 中（认证流程较复杂，需 DBA 插入初始化数据）

#### 致远 OA（A8）
- **GitHub 项目**: gbguanbo/seeyon_oa_api（Python 封装）
- **API**: REST 接口
- **对接难度**: ⭐⭐⭐ 中

---

### D. CRM 系统（P2 — 按需做）

#### 纷享销客
- **开放平台**: open.fxiaoke.com
- **Python 对接**: 知乎/CSDN 有多篇完整示例
- **核心能力**: 客户/联系人/商机/订单 CRUD
- **对接难度**: ⭐⭐ 低（API 设计规范）

#### 销售易（Neocrm）
- **开放平台**: open.neocrm.com
- **对接难度**: ⭐⭐ 低

---

### E. BI/报表（P2 — 按需做）

#### 帆软 FineReport/FineBI
- **数据连接**: JDBC 直连数据库
- **API**: 无公开 REST API，但支持定时任务导出
- **对接方式**: 间接通过数据库连接
- **对接难度**: ⭐⭐⭐ 中

---

### F. MES 系统（P2 — 制造业客户按需做）

- **国内 MES**: 大多无公开 API，主要是私有协议或数据库直连
- **鼎捷 MES（sMES/iMES）**: 与鼎捷 ERP 深度绑定
- **开源 MES**: Gitee 上有少量项目，但成熟度低
- **对接难度**: ⭐⭐⭐⭐⭐ 极高（每家 MES 都不同）

---

## 三、DDW 适配器插件优先级矩阵

### V1（客服插件 MVP 必备）

| 优先级 | 适配器插件 | 说明 |
|:------:|:-----------|:-----|
| **P0** | 钉钉身份适配器 | 组织架构/用户同步 |
| **P0** | 飞书身份适配器 | 组织架构/用户同步 |
| **P0** | 企微身份适配器 | 组织架构/用户同步 |

### V1.5（权限底座完善）

| 优先级 | 适配器插件 | 说明 |
|:------:|:-----------|:-----|
| **P1** | LDAP/AD 适配器 | 企业内部统一认证 |
| **P1** | 用友 U8 适配器 | OpenAPI 方式 |
| **P1** | 金蝶云星空适配器 | WebAPI 方式 |
| **P1** | 泛微 OA 适配器 | REST API 方式 |

### V2（FDE 实施阶段按客户做）

| 优先级 | 适配器插件 | 说明 |
|:------:|:-----------|:-----|
| **P2** | SAP 适配器 | RFC/BAPI |
| **P2** | 致远 OA 适配器 | REST API |
| **P2** | 纷享销客 CRM 适配器 | OpenAPI |
| **P2** | 帆软 FineReport 适配器 | JDBC 直连 |
| **P2** | 鼎捷 ERP 适配器 | WebService |
| **P2** | MES 适配器 | 按具体厂商做 |

### V3（暂不考虑）

| 优先级 | 适配器插件 | 说明 |
|:------:|:-----------|:-----|
| **P3** | 管家婆适配器 | 无公开 API，只能直连 DB |
| **P3** | 速达适配器 | 客户基数小 |

---

## 四、对 DDW 架构的影响

### 插件组合式架构确认

```
客户的"AI 智能客服"部署 = 
  ddw-smart-cs（客服核心插件）
  + ddw-adapter-dingtalk（钉钉身份适配器）
  + ddw-adapter-feishu（飞书身份适配器）
  + ddw-adapter-wecom（企微身份适配器）
  + ddw-cs-knowledge（客服知识库插件）
  + ddw-ent-knowledge（企业知识库同步插件）
  + ddw-permission-engine（权限引擎，Casbin）
  + [按客户需要] ddw-adapter-yonyou-u8（用友适配器）
  + [按客户需要] ddw-adapter-kingdee（金蝶适配器）
```

### 适配器插件的标准接口（建议）

```python
# 所有适配器插件实现统一接口
class AdapterBase(PluginBase):
    """DDW 适配器插件基类"""
    
    def sync_users(self) -> List[User]:
        """同步用户列表"""
        pass
    
    def sync_departments(self) -> List[Department]:
        """同步组织架构"""
        pass
    
    def sync_roles(self) -> List[Role]:
        """同步角色/权限组"""
        pass
    
    def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """权限判断"""
        pass
    
    def query_business_data(self, user_id: str, query: str) -> dict:
        """查询业务数据（带权限控制）"""
        pass
```

---

## 五、关键结论

1. **钉钉/飞书/企微对接是最成熟的** — 官方 SDK + 丰富社区教程，V1 必做
2. **用友/金蝶对接是可行的** — 有 API 文档 + 社区教程，但需要付费授权
3. **SAP/鼎捷/管家婆对接是高难度的** — 或无 Python SDK，或无公开 API
4. **MES 对接是最难的** — 每家都不同，只能逐个客户定制
5. **没有现成的"万能适配器"** — DDW 必须自己构建适配器插件体系
6. **Casbin 是权限引擎的最佳选择** — 不要自己造轮子
7. **Casdoor 是身份源对接的最佳参考** — 借鉴其接口设计模式
