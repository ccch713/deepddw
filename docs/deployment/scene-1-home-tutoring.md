# DDW 培训系统 · 家庭辅导场景部署手册

> 场景：家长在家辅导孩子学习（物理/化学/数学等）
> 目标用户：家长（非技术背景）
> 硬件要求：Mac mini M4 16G / Windows PC / 任意 x86_64 设备
> 部署方式：本地部署，数据不出家门

---

## 一、场景描述

孩子即将升入初三，需要学习更难的物理和新开的化学课程。家长希望通过 AI 辅助：
1. 上传课本 PDF → AI 自动生成多媒体教案（语音+动画讲解）
2. 孩子与 AI 对话学习（苏格拉底式问答）
3. AI 自动出题 + 批改 + 生成学习报告
4. 家长查看孩子学习进度

## 二、需要启用的插件

| 插件 | 用途 | 启用方式 |
|------|------|---------|
| ddw_training | 核心：AI 培训+课件+出题+批改 | ✅ 必须启用 |
| ddw-smart-cs | 辅助：学习对话界面 | ✅ 必须启用 |
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

### 3.2 配置本地 LLM

```bash
# 安装 Ollama（如果未安装）
curl -fsSL https://ollama.ai/install.sh | sh

# 下载适合的模型（16G 设备推荐 7B）
ollama pull qwen2.5:7b

# 在 DDW 中配置 LLM
ddw config set llm.provider ollama
ddw config set llm.model qwen2.5:7b
ddw config set llm.endpoint http://localhost:11434
```

### 3.3 启用培训插件

```bash
# 启用 ddw_training
ddw plugin enable ddw_training

# 启用 ddw-smart-cs（对话界面）
ddw plugin enable ddw-smart-cs

# 重启服务
ddw restart
```

### 3.4 创建学习者档案

在 DDW 对话框中输入：

```
帮我创建一个学习者档案：
姓名：小明
年级：初三
科目：物理、化学、数学
学习目标：中考冲刺
```

DDW 会自动：
1. 在数据库中创建学习者记录
2. 初始化各科目的学习计划
3. 生成第一个学习任务

### 3.5 上传课本/教材

将课本 PDF 文件放到指定目录：

```bash
mkdir -p ~/ddw-data/textbooks/
# 将 PDF 文件复制到该目录
cp ~/Downloads/物理课本.pdf ~/ddw-data/textbooks/
cp ~/Downloads/化学课本.pdf ~/ddw-data/textbooks/
```

在 DDW 对话框中输入：

```
请学习 ~/ddw-data/textbooks/ 目录下的课本文件，
提取知识点，生成教学大纲和练习题。
```

## 四、日常使用

### 4.1 孩子学习

孩子打开浏览器访问 `http://localhost:8500/ui/`，在对话框中：

```
我想学习"光的折射"这个章节，请给我讲解。
```

AI 会：
1. 用苏格拉底式问答引导思考
2. 生成示意图和动画
3. 穿插小测验检查理解
4. 记录学习进度

### 4.2 AI 出题

```
请根据"光的折射"这一章出 10 道选择题和 3 道计算题。
```

### 4.3 家长查看进度

家长在对话框中输入：

```
查看小明的学习进度报告。
```

DDW 会生成：
- 各科目学习时长
- 知识点掌握率
- 薄弱环节分析
- 下一步学习建议

## 五、配置参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| llm.model | qwen2.5:7b | 16G 设备推荐 |
| llm.temperature | 0.7 | 教学场景适中 |
| training.difficulty | adaptive | 自适应难度 |
| training.style | socratic | 苏格拉底式问答 |
| training.max_turns | 20 | 单次对话最大轮次 |

## 六、注意事项

1. **数据安全**：所有学习数据保存在本地，不上云
2. **模型选择**：16G 设备推荐 7B 模型，8GB 内存设备推荐 3B
3. **PDF 识别**：扫描版 PDF 识别效果有限，推荐使用文字版 PDF
4. **网络要求**：首次安装需要联网下载模型，之后可离线使用
5. **存储空间**：每个模型约 4-8GB，建议预留 20GB 磁盘空间
