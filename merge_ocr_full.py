#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_ocr_full.py —— 合并多份 OCR 输出（不同来源格式）为统一全书全文，并校验页数完整性。

用法:
    python merge_ocr_full.py <输出txt> <输入1> [输入2 ...]

支持的输入格式（自动识别）:
    - 本工具链格式： 【第 N 页】\\n正文
    - HTML 注释格式： <!-- page N -->\\n正文
统一输出为： 【第 N 页】\\n正文，按页码升序。
"""
import os
import re
import sys


def parse_bracket(path):
    pages = {}
    txt = open(path, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"【第\s*(\d+)\s*页】\n(.*?)(?=\n?【第\s*\d+\s*页】|\Z)", txt, re.S):
        pages[int(m.group(1))] = m.group(2).strip("\n")
    return pages


def parse_comment(path):
    pages = {}
    txt = open(path, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"<!--\s*page\s*(\d+)\s*-->\n(.*?)(?=\n<!--\s*page\s*\d+\s*-->|\Z)", txt, re.S):
        pages[int(m.group(1))] = m.group(2).strip("\n")
    return pages


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    out = os.path.abspath(sys.argv[1])
    pages = {}
    report = []
    for p in sys.argv[2:]:
        if not os.path.exists(p):
            report.append("MISSING FILE %s" % p)
            continue
        if "page " in open(p, encoding="utf-8", errors="replace").read(2000):
            got = parse_comment(p)
            kind = "comment"
        else:
            got = parse_bracket(p)
            kind = "bracket"
        report.append("%s [%s] pages=%d (%d-%d)" % (os.path.basename(p), kind, len(got),
                                                    min(got) if got else 0, max(got) if got else 0))
        pages.update(got)

    nums = sorted(pages)
    with open(out, "w", encoding="utf-8") as fh:
        for n in nums:
            fh.write("\n【第 %d 页】\n%s" % (n, pages[n]))

    total = max(nums) if nums else 0
    missing = [n for n in range(1, total + 1) if n not in pages]
    chars = sum(len(v) for v in pages.values())
    print("\n".join(report))
    print("MERGED pages=%d/%d chars=%d" % (len(nums), total, chars))
    print("MISSING(%d): %s" % (len(missing), missing[:40]))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
