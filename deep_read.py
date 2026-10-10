#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deep_read.py —— 文档深度解析（无损提取原文全文，非 OCR、非概括）

用法:
    python deep_read.py <文件路径> [输出.txt]

支持格式: .pdf .docx .doc .pptx .xlsx .odt .odp .ods
原理:
    - PDF 有文字层 → pymupdf 直接抽全文（逐字无损）
    - Office 格式 → LibreOffice 转 PDF（自带文字层）→ pymupdf 抽全文（无损）
    - 仅当 PDF 是扫描图（无文字层）时才会提示某页无文字，此时才需 OCR

依赖:
    - pymupdf
    - LibreOffice（soffice.exe；路径可用环境变量 SOFFICE 覆盖）
"""
import os
import re
import sys
import shutil
import tempfile
import subprocess

# 强制 stdout/stderr 用 UTF-8，避免 Windows GBK 控制台打印中文时崩溃（配合 PYTHONUTF8=1 双保险）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def soffice():
    return os.environ.get("SOFFICE", r"C:\Program Files\LibreOffice\program\soffice.exe")


def pdf_text(pdf_path):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pages = []
    empty = 0
    for i, page in enumerate(doc):
        t = page.get_text("text").strip()
        if t:
            pages.append(f"\n【第 {i + 1} 页】\n{t}")
        else:
            empty += 1
            pages.append(f"\n【第 {i + 1} 页】(无文字层)")
    return "".join(pages), doc.page_count, empty


def to_pdf(src, outdir):
    r = subprocess.run(
        [soffice(), "--headless", "--convert-to", "pdf", "--outdir", outdir, src],
        capture_output=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError("LibreOffice 转换失败: " + r.stderr.decode("utf-8", "ignore")[:300])
    base = os.path.splitext(os.path.basename(src))[0]
    pdf = os.path.join(outdir, base + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError("未生成 PDF")
    return pdf


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = os.path.abspath(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".txt"
    ext = os.path.splitext(src)[1].lower()

    tmp = tempfile.mkdtemp(prefix="deepread-")
    try:
        if ext == ".pdf":
            text, pages, empty = pdf_text(src)
        elif ext in (".docx", ".doc", ".pptx", ".xlsx", ".odt", ".odp", ".ods"):
            pdf = to_pdf(src, tmp)
            text, pages, empty = pdf_text(pdf)
        else:
            print("unsupported type:", ext)
            sys.exit(2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    chars = len(re.sub(r"\s", "", text))
    print(f"[OK] pages={pages} chars={chars} empty_pages={empty}")
    print(f"fulltext -> {out}")


if __name__ == "__main__":
    main()
