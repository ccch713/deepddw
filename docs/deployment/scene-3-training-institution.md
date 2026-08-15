# DDW 培训系统 · 教培机构场景部署手册

> 场景：培训机构为学员提供 AI 辅助教学
> 目标用户：培训机构负责人/教务管理人员
> 硬件要求：Mac mini M4 32G / 服务器 / 云主机
> 部署方式：本地服务器部署 or SaaS 托管（ddw.9cio.com）

---

## 一、场景描述

教培机构（课外辅导/职业技能/语言培训等）需要：
1. 批量管理学员档案（姓名/班级/课程/成绩）
2. AI 自动备课（上传教材→生成教案+课件+习题）
3. 学员在线学习 + AI 答疑
4. 自动出题 + 批改 + 成绩统计
5. 教学质量分析（学员满意度/通过率/薄弱环节）
6. 多班级/多课程管理

## 二、需要启用的插件

| 插件 | 用途 | 启用方式 |
|------|------|---------|
| ddw_training | 核心：AI 培训+课件+出题+批改+成绩管理 | ✅ 必须启用 |
| ddw-smart-cs | 学员在线答疑 | ✅ 必须启用 |
| ddw-personnel-qual | 教师资质管理（可选） | ⚡ 可选 |
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

### 3.2 配置多租户（多机构）

```bash
# 如果是 SaaS 模式，每个机构一个租户
ddw tenant create --name "阳光教育" --plan professional
ddw tenant create --name "未来学院" --plan professional

# 如果是单机构模式，跳过此步
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
ddw restart
```

### 3.5 创建班级和课程

```
帮我创建以下班级和课程：

班级：初三物理冲刺班（15人）
班级：初三化学基础班（20人）
班级：初二数学提高班（12人）

课程：
1. 物理：力学、电学、光学（共30课时）
2. 化学：元素化合物、化学方程式、酸碱盐（共25课时）
3. 数学：二次函数、圆、概率（共20课时）
```

### 3.6 批量导入学员

准备 Excel 文件（含姓名/班级/联系方式），在对话框中：

```
请导入学员名单：~/ddw-data/学生名单.xlsx
```

### 3.7 上传教学资料

```bash
mkdir -p ~/ddw-data/textbooks/
mkdir -p ~/ddw-data/exams/

# 上传教材和试卷
cp ~/Downloads/物理教材全套.pdf ~/ddw-data/textbooks/
cp ~/Downloads/化学习题集.pdf ~/ddw-data/textbooks/
cp ~/Downloads/模拟试卷/*.pdf ~/ddw-data/exams/
```

## 四、日常使用

### 4.1 AI 备课

```
请根据"物理-力学"章节，生成：
1. 教案（含教学目标、重难点、教学过程）
2. PPT 课件大纲
3. 随堂练习题（10道选择+5道计算）
4. 课后作业（8道题）
```

### 4.2 学员在线学习

学员通过 `http://localhost:8500/ui/` 登录，在对话框中：

```
我是初三物理冲刺班的学员，请讲解"牛顿第三定律"。
```

### 4.3 成绩管理

```
查看初三物理冲刺班最近一次测验的成绩统计。
```

DDW 生成：
- 平均分/最高分/最低分
- 分数段分布
- 各知识点得分率
- 需要重点关注的学员

### 4.4 教学质量分析

```
分析本月所有班级的教学质量：
- 学员满意度
- 知识点掌握率
- 教学效果对比
```

## 五、配置参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| llm.model | qwen2.5:14b | 32G 设备推荐 |
| auth.multi_user | true | 多用户模式 |
| training.difficulty | adaptive | 自适应难度 |
| training.style | structured | 结构化教学 |
| training.max_students | 100 | 最大学员数 |
| training.grade_weight | 0.6 | 成绩权重 |

## 六、注意事项

1. **并发性能**：32G 设备建议同时在线学员不超过 30 人
2. **数据备份**：教培机构数据至关重要，建议每日备份
3. **学员隐私**：学员信息加密存储，符合《个人信息保护法》
4. **教学效果**：AI 辅助教学需要与传统教学结合，不能完全替代
5. **扩展方案**：学员超过 50 人建议使用云主机部署
