#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_render_pages.py —— 把 PDF（尤其扫描版）逐页渲染为灰度 PNG，供 OCR 使用。

用法:
    python pdf_render_pages.py <pdf路径> <输出目录> [dpi=200] [起始页=1] [结束页=0(到末尾)]

说明:
    - 灰度（csGRAY）输出，体积约为彩色 1/3，OCR 精度不受影响。
    - 文件名 p0001.png 形式，页码从 1 开始，便于 OCR 结果回填页码。
    - 已存在的页会跳过，支持断点续跑。
"""
import os
import sys

import pymupdf


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pdf = os.path.abspath(sys.argv[1])
    outdir = os.path.abspath(sys.argv[2])
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    start = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    end = int(sys.argv[5]) if len(sys.argv) > 5 else 0

    doc = pymupdf.open(pdf)
    n = doc.page_count
    end = end or n
    end = min(end, n)
    os.makedirs(outdir, exist_ok=True)

    done = 0
    for i in range(start - 1, end):
        path = os.path.join(outdir, "p%04d.png" % (i + 1))
        if os.path.exists(path) and os.path.getsize(path) > 1024:
            done += 1
            continue
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        pix.save(path)
        done += 1
        print("[%d/%d] %s %dx%d %dKB" % (i + 1, n, os.path.basename(path),
                                         pix.width, pix.height,
                                         os.path.getsize(path) // 1024), flush=True)
    print("DONE rendered=%d total_pages=%d outdir=%s" % (done, n, outdir))


if __name__ == "__main__":
    main()
