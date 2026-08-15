#!/usr/bin/env python3
"""批量 OCR 题库入库（2026-08-14）。

从问渠_教材包 目录批量识别 PDF/图片中的题目，提取后入库。

用法:
    python3 plugins/ddw_wenqu_tutor/scripts/batch_ocr.py \
        --input /Users/chenye/workspace/问渠_教材包/在线_化学 \
        --subject chemistry --limit 50

依赖: pip install pymupdf pillow httpx（MiniMax-VL-01 多模态）
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("DDW_WENQU_VISION_MODEL", "MiniMax-VL-01")
VISION_BASE_URL = os.getenv("DDW_WENQU_VISION_BASE_URL", "https://api.minimaxi.com/v1")
IMAGE_MAX_SIZE = 4 * 1024 * 1024  # 4MB per image


def _vision_api_key() -> str:
    key = os.getenv("DDW_MINIMAX_API_KEY", "")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.ddw_env")) as f:
            for line in f:
                if "MINIMAX_API_KEY" in line:
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


def _build_prompt(subject: str) -> str:
    subject_name = "物理" if subject == "physics" else "化学"
    return f"""请识别这张{subject_name}题目图片中的所有题目。

要求：
1. 只提取题目正文和选项，不要提取答案/解析
2. 每道题输出 JSON 格式：
   {{"text": "完整题目正文", "options": ["A. 选项1", "B. 选项2", ...], "difficulty": "easy/medium/hard"}}
3. 如果没有选项（如计算题/问答题），options 为空数组

输出 JSON 数组，不要其他文字。"""


def extract_pages_from_pdf(pdf_path: str, max_pages: int = 5) -> list[bytes]:
    """从 PDF 提取前几页的截图（图片格式）。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF 未安装，跳过 PDF: %s", pdf_path)
        return []

    images = []
    try:
        doc = fitz.open(pdf_path)
        for i in range(min(max_pages, len(doc))):
            page = doc[i]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            if len(img_bytes) <= IMAGE_MAX_SIZE:
                images.append(img_bytes)
        doc.close()
    except Exception as e:
        logger.warning("PDF 处理失败 %s: %s", pdf_path, e)
    return images


async def recognize_image(
    image_bytes: bytes,
    subject: str,
    api_key: str,
) -> list[dict]:
    """用视觉模型识别单张图片中的题目。"""
    mime = "image/png"  # PyMuPDF 截图是 PNG 格式
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"

    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _build_prompt(subject)},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VISION_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data["choices"][0]["message"]["content"]

    # 解析 JSON 数组
    json_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    # 单个 JSON 对象也接受
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            obj = json.loads(json_match.group())
            if "text" in obj:
                return [obj]
        except json.JSONDecodeError:
            pass
    return []


async def batch_process(
    input_dir: str,
    subject: str,
    limit: int = 50,
    output_json: Optional[str] = None,
):
    """批量处理目录下所有 PDF/图片。"""
    api_key = _vision_api_key()
    if not api_key:
        print("❌ 未找到 MiniMax API key")
        return

    input_path = Path(input_dir)
    all_questions = []

    # 收集文件
    files = []
    for ext in ["*.pdf", "*.jpg", "*.jpeg", "*.png"]:
        files.extend(input_path.glob(ext))
    # 也扫描子目录
    for sub in input_path.iterdir():
        if sub.is_dir():
            for ext in ["*.pdf", "*.jpg", "*.jpeg", "*.png"]:
                files.extend(sub.glob(ext))
            # 二级子目录
            for sub2 in sub.iterdir():
                if sub2.is_dir():
                    for ext in ["*.pdf", "*.jpg", "*.jpeg", "*.png"]:
                        files.extend(sub2.glob(ext))

    files = sorted(set(files))[:limit]
    print(f"📄 共 {len(files)} 个文件待处理")

    for i, fpath in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {fpath.name[:50]}", end="...")
        try:
            if fpath.suffix.lower() == ".pdf":
                images = extract_pages_from_pdf(str(fpath), max_pages=3)
            else:
                with open(fpath, "rb") as f:
                    img = f.read()
                images = [img] if len(img) <= IMAGE_MAX_SIZE else []

            questions = []
            for img in images[:2]:
                qs = await recognize_image(img, subject, api_key)
                questions.extend(qs)
                time.sleep(0.5)

            for q in questions:
                q["_source_file"] = fpath.name
                q["_chapter"] = fpath.stem[:30]
            all_questions.extend(questions)
            print(f" {len(questions)} 题")
        except Exception as e:
            print(f" ❌ {e}")
        time.sleep(1)

    # 去重
    seen = set()
    unique = []
    for q in all_questions:
        text = (q.get("text") or "").strip()[:100]
        if text and text not in seen:
            seen.add(text)
            unique.append(q)

    # 输出
    out_path = output_json or f"/Users/chenye/workspace/问渠_教材包/ocr_output_{subject}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=1)

    print(f"\n✅ 完成！共识别 {len(unique)} 道去重题目")
    print(f"   输出：{out_path}")
    print(f"   来源：{len(files)} 个文件")
    print(f"\n   用途：下一步跑 seed 脚本入库（公共题库，M1 众筹奖励）")

    return unique


def main():
    ap = argparse.ArgumentParser(description="批量 OCR 题库入库")
    ap.add_argument("--input", required=True, help="输入目录")
    ap.add_argument("--subject", default="chemistry", help="physics 或 chemistry")
    ap.add_argument("--limit", type=int, default=50, help="最大处理文件数")
    ap.add_argument("--output", help="输出 JSON 路径（默认 ocr_output_{subject}.json）")
    args = ap.parse_args()
    import asyncio
    asyncio.run(batch_process(args.input, args.subject, args.limit, args.output))


if __name__ == "__main__":
    main()
