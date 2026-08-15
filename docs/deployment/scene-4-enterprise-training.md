# DDW 培训系统 · 企业员工培训场景部署手册

> 场景：企业为内部员工提供在线培训和考核
> 目标用户：企业 HR/培训部门负责人
> 硬件要求：服务器 / 云主机 / Mac mini M4 32G
> 部署方式：内网部署（数据不出企业）

---

## 一、场景描述

企业需要对员工进行：
1. 入职培训（企业文化/制度/安全）
2. 技能培训（专业技能/管理能力）
3. 合规培训（法律法规/行业标准）
4. 考核评估（在线考试/实操评估）
5. 培训记录管理（学习时长/考核分数记入人事档案）
6. 多部门/多岗位培训管理

## 二、需要启用的插件

| 插件 | 用途 | 启用方式 |
|------|------|---------|
| ddw_training | 核心：AI 培训+课件+出题+批改+成绩管理 | ✅ 必须启用 |
| ddw-smart-cs | 员工在线答疑 | ✅ 必须启用 |
| ddw-personnel-qual | 员工资质证书管理 | ⚡ 推荐启用 |
| ddw-cost-knowledge | 不需要 | ❌ 不启用 |
| ddw-bid-writer | 不需要 | ❌ 不启用 |

## 三、部署步骤

### 3.1 安装 DDW AI Hub

```bash
# 下载安装包
curl -L https://ddw.9cio.com/install.sh | bash

# 启动服务
ddw start --port 8500
```

### 3.2 配置多租户

```bash
# 每个部门可作为一个租户
ddw tenant create --name "技术部" --plan enterprise
ddw tenant create --name "销售部" --plan enterprise
ddw tenant create --name "行政部" --plan enterprise
```

### 3.3 配置本地 LLM

```bash
# 32G 设备推荐 14B 模型
ollama pull qwen2.5:14b

ddw config set llm.provider ollama
ddw config set llm.model qwen2.5:14b
ddw config set llm.endpoint http://localhost:11434
```

### 3.4 启用插件

```bash
ddw plugin enable ddw_training
ddw plugin enable ddw-smart-cs
ddw plugin enable ddw-personnel_qual
ddw restart
```

### 3.5 创建培训计划

```
帮我创建以下培训计划：

1. 新员工入职培训（必修）
   - 企业文化与价值观（4课时）
   - 规章制度与行为规范（2课时）
   - 安全生产与消防知识（4课时）
   - 信息安全与保密（2课时）
   - 考核方式：在线考试，80分及格

2. 技术人员年度培训（技术部必修）
   - 新技术学习（AI/云计算/大数据）
   - 代码规范与安全开发
   - 项目管理方法论
   - 考核方式：在线考试+实操评估

3. 管理人员培训（管理层必修）
   - 领导力与团队管理
   - 绩效管理与激励
   - 沟通技巧
   - 考核方式：在线考试+案例分析
```

### 3.6 导入员工名单

准备 Excel 文件，在对话框中：

```
请导入员工名单：~/ddw-data/员工名单.xlsx
按部门分配到对应培训计划。
```

### 3.7 上传培训资料

```bash
mkdir -p ~/ddw-data/training/

# 上传培训教材、PPT、视频等
cp ~/Downloads/企业文化手册.pdf ~/ddw-data/training/
cp ~/Downloads/安全生产培训课件.pptx ~/ddw-data/training/
```

### 3.8 配置资质管理（可选）

```
导入技术部员工的资质证书：
- 注册工程师证书
- 安全生产许可证
- 特种作业操作证

设置证书到期提前 60 天预警。
```

## 四、日常使用

### 4.1 员工在线学习

员工通过 `http://企业内网:8500/ui/` 登录，在对话框中：

```
我是技术部员工，请开始"新员工入职培训"课程。
```

### 4.2 HR 查看培训进度

```
查看本月所有部门的培训完成率。
```

DDW 生成：
- 各部门完成率
- 各课程参与人数
- 未完成人员名单
- 考核成绩分布

### 4.3 资质证书管理

```
查看即将到期的证书列表。
```

```
技术部有多少人持有注册工程师证书？
```

### 4.4 培训记录导出

```
导出技术部 2026 年上半年的培训记录，
包含学习时长和考核分数。
```

## 五、配置参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| llm.model | qwen2.5:14b | 32G 设备推荐 |
| auth.multi_user | true | 多用户模式 |
| auth.sso | true | 单点登录（对接企业 OA） |
| training.difficulty | fixed | 固定难度（统一考核） |
| training.pass_score | 80 | 及格分数线 |
| training.max_students | 200 | 最大员工数 |
| personnel_qual.expiry_warn_days | 60 | 证书到期预警天数 |

## 六、注意事项

1. **数据安全**：企业培训数据属于商业机密，必须内网部署
2. **合规要求**：培训记录需保存 3 年以上（安全生产法要求）
3. **考核防作弊**：支持随机出题、限时答题、切屏检测
4. **系统集成**：可对接企业 OA/HR 系统（飞书/钉钉/企微）
5. **扩展方案**：员工超过 100 人建议使用服务器部署
