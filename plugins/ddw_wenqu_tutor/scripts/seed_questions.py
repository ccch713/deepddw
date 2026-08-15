#!/usr/bin/env python3
"""种子题库入库（2026-08-14）。

把 batch_ocr.py 产出的 JSON 题目列表导入 wenqu_questions 表。

用法:
    python3 plugins/ddw_wenqu_tutor/scripts/seed_questions.py \
        --input /Users/chenye/workspace/问渠_教材包/ocr_chemistry.json \
        --subject chemistry
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 需要在项目根目录运行
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def seed(input_file: str, subject: str):
    """读 JSON 题目列表，打印为 SQL INSERT 或直接操作 DB。"""
    data = json.load(open(input_file, encoding="utf-8"))
    print(f"读入 {len(data)} 道题（subject={subject}）")

    # 去重（按 text 前80字符）
    seen = set()
    unique = []
    for q in data:
        text = (q.get("text") or "").strip()
        key = text[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(q)

    print(f"去重后 {len(unique)} 道题")

    # 导出为 seed SQL（方便手动/批量入库）
    sql_lines = []
    for q in unique:
        text = (q.get("text") or "").replace("'", "''")
        answer = (q.get("answer") or "").replace("'", "''")
        explanation = (q.get("explanation") or "").replace("'", "''")
        difficulty = q.get("difficulty", "medium")
        chapter = q.get("chapter", "")
        # 简单从文本提取章节信息（如果有关键词）
        if not chapter:
            if "元素" in text or "化合价" in text or "化学式" in text:
                chapter = "物质构成的奥秘"
            elif "空气" in text or "氧气" in text:
                chapter = "我们周围的空气"
            elif "水" in text or "净化" in text:
                chapter = "自然界的水"
            elif "化学方程式" in text or "反应" in text:
                chapter = "化学方程式"
            elif "碳" in text or "CO" in text:
                chapter = "碳和碳的氧化物"
            elif "燃烧" in text or "燃料" in text:
                chapter = "燃料及其利用"
            elif "力" in text or "摩擦" in text:
                chapter = "力学"
            elif "电" in text or "欧姆" in text:
                chapter = "电学"

        sql = (
            f"INSERT INTO wenqu_questions "
            f"(id, subject, chapter, year, difficulty, source, question_text, "
            f"answer, explanation, knowledge_points, mode, is_ai_generated, created_at) "
            f"VALUES ("
            f"  'Q_SEED_{hash(text) & 0xFFFFFFFFFFFFFF:016x}', "
            f"  '{subject}', "
            f"  '{chapter}', "
            f"  2024, "
            f"  '{difficulty}', "
            f"  'ocr_seed', "
            f"  '{text}', "
            f"  '{answer}', "
            f"  '{explanation}', "
            f"  '[]', "
            f"  NULL, "
            f"  0, "
            f"  CURRENT_TIMESTAMP"
            f");"
        )
        sql_lines.append(sql)

    # 输出 SQL 文件
    out_sql = str(Path(input_file).with_suffix(".sql"))
    with open(out_sql, "w", encoding="utf-8") as f:
        f.write("-- 种子题库（OCR 识别结果）\n")
        f.write(f"-- subject={subject}, count={len(sql_lines)}\n\n")
        for line in sql_lines:
            f.write(line + "\n")
    print(f"✅ SQL 已生成：{out_sql}")
    print(f"   共 {len(sql_lines)} 条 INSERT 语句")

    # 统计
    chapters = {}
    for q in unique:
        ch = q.get("chapter") or "未分类"
        chapters[ch] = chapters.get(ch, 0) + 1
    print("\n章节分布：")
    for ch, cnt in sorted(chapters.items(), key=lambda x: -x[1]):
        print(f"  {ch}: {cnt} 题")


def main():
    ap = argparse.ArgumentParser(description="种子题库入库")
    ap.add_argument("--input", required=True, help="OCR JSON 文件路径")
    ap.add_argument("--subject", default="chemistry", help="physics 或 chemistry")
    args = ap.parse_args()
    seed(args.input, args.subject)


if __name__ == "__main__":
    main()
