# MiniMax Code 交接提示词（口腔门诊 AI 赋能 TASK_SPEC 开发）

> 用法：将下面的提示词完整复制到 16G 设备的 MiniMax Code GUI 对话框中发送。
> 前提：确保 Syncthing 已将32G workspace 同步到16G。

---

## 复制内容开始 ═══════════════════════════════════

你是口腔门诊 AI 赋能系统的开发 Agent。请严格按照 TASK_SPEC 执行开发任务。

## 一、任务概要

为武汉东华口腔青山店（沿港路27号，14 医生）开发一套完整的口腔门诊管理系统。项目基于 DDW AI Hub 插件体系，代码仓库在 `DDW底座平台/ddw-ai-hub/plugins/`。

**开发文档**（必读）：
```
DDW底座平台/ddw-prd/TASK_SPEC_口腔门诊AI赋能_v2.0_20260805.md
```
请先完整阅读此文件（1810 行 / 60KB），它是你唯一的开发依据。

## 二、开发顺序（严格按依赖链执行）

```
第1周前半（T0）→ 第1周后半（T1+T16+T2 并行）→ 第2周（T3+T4+T5+T6）→ 第3周（T7+T8+T9+联调）
```

**每个 Task 完成后必须执行**：
1. `python -m py_compile` 通过所有 .py 文件
2. `pytest tests/ -v` 全部通过
3. 确认无 ruff 错误：`ruff check .`

## 三、DDW 插件协议（速查）

每个插件必须遵循以下结构：

```
plugins/ddw_{name}/
├── __init__.py          # PLUGIN_NAME = "ddw_{name}"; VERSION = "0.1.0"
├── plugin.py            # class Plugin(PluginBase): setup() 中注册 router
├── router.py            # FastAPI APIRouter(prefix="/api/v1/plugins/ddw_{name}")
├── models.py            # Pydantic 数据模型（可选）
├── tests/
│   └── test_{name}.py   # pytest 测试
└── manifest.yaml
```

**plugin.py 模板**：
```python
from core.plugin_base import PluginBase

class Plugin(PluginBase):
    def setup(self):
        from .router import router
        self._router = router
        self.app.include_router(router)
```

**router.py 头部模板**：
```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/plugins/ddw_{name}", tags=["ddw_{name}"])

@router.get("/health")
async def health():
    return {"plugin": "ddw_{name}", "version": "0.1.0", "status": "ok"}
```

**目录名必须用下划线**（ddw_xxx），不能用连字符。`__init__.py` 和 `plugin.py` 缺一不可。

## 四、技术约束

1. **LLM**：使用 MiniMax-M3（从 `config/deployment.yaml` 读取 API key）
2. **数据库**：每个插件用独立 SQLite（路径：`plugins/ddw_{name}/data/{name}.db`）
3. **测试**：每个 Task 的测试用例在 TASK_SPEC 中已列出，必须全部实现
4. **Python 版本**：3.11+，依赖只用 FastAPI + Pydantic + SQLite（stdlib）
5. **不要碰 ECS**：只在本地开发 + 测试，不要推送到远程
6. **不要碰 ddw_clinic_cs**（v0.1 已部署，不要修改）
7. **git commit 格式**：`feat(口腔): T{n} {插件描述}`

## 五、执行要求

1. **逐个 Task 执行**，不要跳 Task。每个 Task 完成后等我说"继续"再做下一个
2. **每个 Task 完成后输出**：
   - 创建的文件清单
   - pytest 执行结果
   - 遇到的问题（如有）
3. **遇到 TASK_SPEC 中未定义的细节**，按以下优先级决策：
   - 参考 TASK_SPEC 中已有的代码模板（如 store.py、transcriber.py）
   - 参考已有插件 `plugins/ddw_clinic_cs/` 的实现风格
   - 自行合理决策，不要停下来问
4. **LLM Prompt**（T1 实体抽取）：TASK_SPEC 中已给出完整 prompt 文本，直接使用
5. **YAML 模板**（T16）：TASK_SPEC 中已给出 extraction.yaml 完整内容，其他 8 个类型按相同格式 + TASK_SPEC 中的字段定义自行编写

## 六、视觉设计规范（必须遵守）

所有前端界面采用以下配色和纹理（来源：口腔诊所AI赋能方案_v1.html）：

```css
:root {
  --brand:        #0B6E99;   /* 主色：医疗蓝 */
  --brand-dark:   #08547A;   /* 深蓝：标题 */
  --brand-light:  #E8F4FA;   /* 浅蓝：徽章/背景 */
  --accent:       #F08A24;   /* 暖橙：CTA按钮 */
  --bg:           #FFFFFF;   /* 纯白 */
  --bg-soft:      #F6FAFD;   /* 微蓝灰：交替区块 */
  --text:         #24313C;   /* 主文字 */
  --text-secondary: #5A6B7A; /* 辅助文字 */
  --border:       #E3EDF4;   /* 卡片边框 */
  --success:      #2E9E6B;   /* 成功绿 */
}
```

渐变纹理：
- Hero：`linear-gradient(135deg, #0B6E99 0%, #0A5C84 55%, #08547A 100%)`
- AI卡片：`linear-gradient(160deg, #0B6E99 0%, #0A5C84 100%)`
- CTA区：`linear-gradient(135deg, #0B6E99 0%, #08547A 100%)`

卡片：白底 + `border: 1px solid var(--border)` + `border-radius: 12-14px` + `box-shadow: 0 3px 14px rgba(11,110,153,0.05)`
CTA按钮：橙色 `#F08A24` + `border-radius: 30px` + `box-shadow: 0 6px 18px rgba(240,138,36,0.35)`
字体栈：`-apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif`

完整设计规范见：`DDW底座平台/ddw-prd/DESIGN_TOKENS_口腔门诊_v1.0_20260805.md`

**铁律**：所有颜色用 CSS 变量 `var(--xxx)`，禁止 Tailwind 颜色类名和硬编码 hex。

## 现在开始

**第一步**：请先阅读 TASK_SPEC：
```
DDW底座平台/ddw-prd/TASK_SPEC_口腔门诊AI赋能_v2.0_20260805.md
```

**第二步**：从 T0（ddw_talk_a1_asr）开始执行。

完成后告诉我 T0 的文件清单和测试结果，我确认后再做 T1。

## 复制内容结束 ═══════════════════════════════════
