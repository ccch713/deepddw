"""Prompt templates for RIA-TV++ methodology distill engine.

Five extraction types + triple verification + RIA++ six-section construction.
All prompts support Chinese documents.
"""
from __future__ import annotations

# ─── System prompts ───

EXTRACT_SYSTEM = """你是一位资深的企业方法论专家，擅长从文档中提炼可执行的方法论。
你的任务是从用户提供的文档内容中提取候选方法论单元。
每个候选单元必须包含：标题、原文引用（≤150字）、出处章节。
请用 JSON 格式返回结果。"""

VERIFY_SYSTEM = """你是一位严格的方法论评审专家，负责对候选方法论单元进行三重验证。
验证标准：
- V1 跨域：文档中≥2个独立段落有佐证
- V2 预测力：能回答文档没明说的新问题
- V3 独特性：不是任何聪明人都说的常识
请用 JSON 格式返回验证结果。"""

CONSTRUCT_SYSTEM = """你是一位方法论构造专家，负责将验证通过的方法论单元构造为 RIA++ 六段格式。
RIA++ 六段：
- R（原文引用）：≤150字的原文引用
- I（改写）：方法论骨架，用你自己的话重述
- A1（书中案例）：文档中的具体案例
- A2（触发场景）：什么情况下应该使用这个方法论
- E（执行步骤）：1-2-3 步骤
- B（边界）：这个方法论不适用的情况
请用 JSON 格式返回结果。"""


# ─── Five extraction prompts ───

def extract_framework_prompt(document_content: str, chapter: str = "") -> str:
    """提取框架类方法论（结构性、体系化的方法）。"""
    return f"""请从以下文档内容中提取"框架"类方法论候选单元。

框架类方法论的特征：
- 提供结构性的思考或行动框架
- 有明确的步骤、阶段或层次
- 可以指导复杂问题的分析和解决

文档章节：{chapter if chapter else "全文"}

文档内容：
{document_content[:6000]}

请返回 JSON 数组，每个元素包含：
{{
    "title": "方法论名称",
    "original_text": "原文引用（≤150字）",
    "source_chapter": "出处章节",
    "reason": "为什么这是框架类方法论"
}}

如果没有找到框架类方法论，返回空数组 []。"""


def extract_principle_prompt(document_content: str, chapter: str = "") -> str:
    """提取原则类方法论（指导性原则、准则）。"""
    return f"""请从以下文档内容中提取"原则"类方法论候选单元。

原则类方法论的特征：
- 提供指导性的原则或准则
- 简洁有力，易于记忆
- 可以指导决策和行为

文档章节：{chapter if chapter else "全文"}

文档内容：
{document_content[:6000]}

请返回 JSON 数组，每个元素包含：
{{
    "title": "原则名称",
    "original_text": "原文引用（≤150字）",
    "source_chapter": "出处章节",
    "reason": "为什么这是原则类方法论"
}}

如果没有找到原则类方法论，返回空数组 []。"""


def extract_case_prompt(document_content: str, chapter: str = "") -> str:
    """提取案例类方法论（具体案例、实例）。"""
    return f"""请从以下文档内容中提取"案例"类方法论候选单元。

案例类方法论的特征：
- 包含具体的情境、行动和结果
- 可以作为学习和参考的范例
- 有明确的因果关系或经验教训

文档章节：{chapter if chapter else "全文"}

文档内容：
{document_content[:6000]}

请返回 JSON 数组，每个元素包含：
{{
    "title": "案例名称",
    "original_text": "原文引用（≤150字）",
    "source_chapter": "出处章节",
    "reason": "为什么这是案例类方法论"
}}

如果没有找到案例类方法论，返回空数组 []。"""


def extract_counter_example_prompt(document_content: str, chapter: str = "") -> str:
    """提取反例类方法论（错误做法、需要避免的情况）。"""
    return f"""请从以下文档内容中提取"反例"类方法论候选单元。

反例类方法论的特征：
- 展示错误的做法或需要避免的情况
- 可以帮助识别和预防问题
- 通常包含"不要"、"禁止"、"避免"等关键词

文档章节：{chapter if chapter else "全文"}

文档内容：
{document_content[:6000]}

请返回 JSON 数组，每个元素包含：
{{
    "title": "反例名称",
    "original_text": "原文引用（≤150字）",
    "source_chapter": "出处章节",
    "reason": "为什么这是反例类方法论"
}}

如果没有找到反例类方法论，返回空数组 []。"""


def extract_glossary_prompt(document_content: str, chapter: str = "") -> str:
    """提取术语类方法论（专业术语、关键概念）。"""
    return f"""请从以下文档内容中提取"术语"类方法论候选单元。

术语类方法论的特征：
- 包含专业术语或关键概念的定义
- 有助于理解领域知识
- 通常有明确的定义或解释

文档章节：{chapter if chapter else "全文"}

文档内容：
{document_content[:6000]}

请返回 JSON 数组，每个元素包含：
{{
    "title": "术语名称",
    "original_text": "原文引用（≤150字）",
    "source_chapter": "出处章节",
    "reason": "为什么这是术语类方法论"
}}

如果没有找到术语类方法论，返回空数组 []。"""


# ─── Triple verification prompt ───

def verify_unit_prompt(
    unit_title: str,
    unit_type: str,
    original_text: str,
    document_content: str,
    strict_mode: bool = True,
) -> str:
    """对候选方法论单元进行三重验证。"""
    v3_instruction = (
        "V3 独特性：不是任何聪明人都说的常识。必须有独特见解或专业知识。"
        if strict_mode
        else "V3 独特性：宽松模式，只要是文档中的有价值内容即可。"
    )

    return f"""请对以下候选方法论单元进行三重验证。

候选单元：
- 标题：{unit_title}
- 类型：{unit_type}
- 原文引用：{original_text}

文档内容（用于交叉验证）：
{document_content[:4000]}

验证标准：
- V1 跨域：文档中≥2个独立段落有佐证。这个方法论在文档的多个地方被提及或支持吗？
- V2 预测力：能回答文档没明说的新问题。这个方法论能帮助解决文档没有直接回答的问题吗？
- {v3_instruction}

请返回 JSON 对象：
{{
    "v1_passed": true/false,
    "v1_reason": "V1 通过/不通过的原因",
    "v2_passed": true/false,
    "v2_reason": "V2 通过/不通过的原因",
    "v3_passed": true/false,
    "v3_reason": "V3 通过/不通过的原因",
    "overall": "verified" 或 "rejected",
    "reject_reason": "如果不通过，说明主要原因"
}}"""


# ─── RIA++ construction prompt ───

def construct_ria_prompt(
    unit_title: str,
    unit_type: str,
    original_text: str,
    document_content: str,
) -> str:
    """将验证通过的方法论单元构造为 RIA++ 六段格式。"""
    return f"""请将以下方法论单元构造为 RIA++ 六段格式。

方法论单元：
- 标题：{unit_title}
- 类型：{unit_type}
- 原文引用：{original_text}

文档内容（用于提取案例和细节）：
{document_content[:4000]}

请构造 RIA++ 六段：

R（原文引用）：≤150字的原文引用，保持原文准确性。
I（改写）：用你自己的话重述方法论骨架，使其更清晰易懂。
A1（书中案例）：从文档中提取一个具体案例来说明这个方法论。
A2（触发场景）：描述什么情况下应该使用这个方法论（触发词）。
E（执行步骤）：提供 1-2-3 个具体步骤来执行这个方法论。
B（边界）：说明这个方法论不适用的情况或限制条件。

请返回 JSON 对象：
{{
    "r_section": "原文引用",
    "i_section": "改写后的方法论骨架",
    "a1_section": "文档中的具体案例",
    "trigger_words": "触发词，用逗号分隔",
    "e_section": "执行步骤（1. xxx 2. xxx 3. xxx）",
    "b_section": "边界和限制条件"
}}"""


# ── 轻量摘要模式 Prompt ─────────────────────────────────────

LIGHT_SUMMARY_SYSTEM = """你是一个企业知识管理助手。请对以下文档内容做轻量蒸馏。
提取核心摘要、关键知识点、适用场景和关键词标签。"""

LIGHT_SUMMARY_PROMPT = """文档标题：{title}
文档内容（前 5000 字）：{content}

请提取：
1. 核心摘要（200 字以内）
2. 关键知识点（3-7 条，每条不超过 100 字）
3. 适用场景（哪些岗位/部门/业务场景会用到）
4. 关键词标签（3-8 个）
5. 是否涉及强制规定/红线

JSON 输出：
{{
  "title": "蒸馏标题",
  "summary": "200字摘要",
  "key_points": ["要点1", "要点2"],
  "applicable_scenarios": ["质量工程师日常", "CAPA 流程执行"],
  "tags": ["CAPA", "不合格品", "质量管控"],
  "has_redlines": false,
  "unit_type": "framework"
}}"""
