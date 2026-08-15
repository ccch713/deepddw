# DDW 培训系统 · 同学辅导场景部署手册

> 场景：一个孩子辅导多个同学（小班教学/家教模式）
> 目标用户：辅导者（大学生/退休教师/家长）
> 硬件要求：Mac mini M4 16G / Windows PC
> 部署方式：本地部署，一台设备服务多个学生

---

## 一、场景描述

一个辅导者同时辅导 2-5 个同学（物理/化学/数学等），需要：
1. 为每个学生建立独立的学习档案
2. AI 根据每个学生的水平生成差异化教案
3. 学生通过不同账号登录，各自独立学习
4. 辅导者查看所有学生的学习进度对比
5. 批量出题 + 自动批改

## 二、需要启用的插件

| 插件 | 用途 | 启用方式 |
|------|------|---------|
| ddw_training | 核心：AI 培训+课件+出题+批改 | ✅ 必须启用 |
| ddw-smart-cs | 辅助：多用户对话界面 | ✅ 必须启用 |
| ddw-personnel-qual | 不需要 | ❌ 不启用 |
| ddw-cost-knowledge | 不需要 | ❌ 不启用 |
| ddw-bid-writer | 不需要 | ❌ 不启用 |

## 三、部署步骤

### 3.1 安装 DDW AI Hub

```bash
# 下载安装包
curl -L https://ddw.9cio.com/install.sh | bash

# 启动服务
ddw start --port 8500

# 打开浏览器
open http://localhost:8500/ui/
```

### 3.2 配置多用户模式

```bash
# 启用多用户
ddw config set auth.multi_user true

# 设置管理员（辅导者）
ddw user create --name "辅导老师" --role admin --password "xxx"

# 为每个学生创建账号
ddw user create --name "学生A" --role student --password "xxx"
ddw user create --name "学生B" --role student --password "xxx"
ddw user create --name "学生C" --role student --password "xxx"
```

### 3.3 启用插件

```bash
ddw plugin enable ddw_training
ddw plugin enable ddw-smart-cs
ddw restart
```

### 3.4 配置本地 LLM

```bash
# 16G 设备推荐 7B 模型
ollama pull qwen2.5:7b

ddw config set llm.provider ollama
ddw config set llm.model qwen2.5:7b
ddw config set llm.endpoint http://localhost:11434
```

### 3.5 为每个学生创建学习档案

在 DDW 管理员对话框中输入：

```
帮我创建 3 个学生的学习档案：

学生A：小红，初二，数学薄弱，需要从基础补起
学生B：小刚，初三，物理中等，目标重点高中
学生C：小丽，初三，化学零基础，需要从头学起

每个学生创建独立的学习计划和进度跟踪。
```

### 3.6 上传教学资料

```bash
mkdir -p ~/ddw-data/textbooks/
# 上传课本、习题集、试卷等
cp ~/Downloads/物理习题集.pdf ~/ddw-data/textbooks/
cp ~/Downloads/化学实验手册.pdf ~/ddw-data/textbooks/
```

## 四、日常使用

### 4.1 学生登录学习

每个学生用各自的账号登录 `http://localhost:8500/ui/`，在对话框中：

```
我是小红，我想复习"一元二次方程"。
```

AI 会根据小红的档案（数学薄弱、从基础补起）调整难度和讲解方式。

### 4.2 辅导者查看进度

管理员对话框中输入：

```
查看所有学生的学习进度对比。
```

DDW 生成：
- 各学生学习时长对比
- 各科目掌握率对比
- 薄弱知识点分布
- 需要重点关注的学生

### 4.3 批量出题

```
为所有学生出一份"二次函数"测验试卷，难度按各自水平调整。
```

### 4.4 自动批改

```
批改学生A提交的数学作业。
```

## 五、配置参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| llm.model | qwen2.5:7b | 16G 设备推荐 |
| auth.multi_user | true | 多用户模式 |
| training.difficulty | adaptive | 自适应难度 |
| training.style | socratic | 苏格拉底式问答 |
| training.max_students | 10 | 最大学生数 |

## 六、注意事项

1. **多用户隔离**：每个学生的学习数据独立，互不可见
2. **并发性能**：16G 设备建议同时在线学生不超过 5 人
3. **模型切换**：如果学生水平差异大，可考虑为不同学生分配不同模型
4. **备份数据**：定期备份 `~/ddw-data/` 目录
