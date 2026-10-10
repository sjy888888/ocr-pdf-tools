#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_pages.py —— 用 RapidOCR（本地 ONNX，无需联网）批量识别 PNG 页，输出带页码标记的全文。

用法:
    <rapid_venv>/python.exe ocr_pages.py <pages目录> <输出txt> [起始页] [结束页]

说明:
    - 页图命名 p0001.png；页码从 1 开始。
    - 行序：按检测框 y 坐标聚类成行，行内按 x 排序（单栏书籍正文适用）。
    - 增量落盘：每页 OCR 完立即重写输出文件，中途中断不丢结果。
    - 断点续跑：输出文件中已有【第 N 页】标记的页会跳过。
    - 分片并行：不同进程用不同 [起始页] [结束页] 与不同输出文件，最后合并即可。
"""
import glob
import os
import re
import sys

from rapidocr_onnxruntime import RapidOCR


def parse_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8", errors="replace") as fh:
            for m in re.finditer(r"【第\s*(\d+)\s*页】", fh.read()):
                done.add(int(m.group(1)))
    return done


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pages_dir = os.path.abspath(sys.argv[1])
    out_path = os.path.abspath(sys.argv[2])
    start = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    end = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    order = (sys.argv[5] if len(sys.argv) > 5 else "asc").lower()

    files = {}
    for f in glob.glob(os.path.join(pages_dir, "*.png")):
        m = re.search(r"p(\d+)\.png$", os.path.basename(f))
        if m:
            files[int(m.group(1))] = f
    if not files:
        print("no page images found in", pages_dir)
        sys.exit(2)

    page_nums = sorted(n for n in files if n >= start and (not end or n <= end))
    if order == "desc":
        page_nums = page_nums[::-1]  # 从书尾往前跑
    done = parse_done(out_path)
    todo = [n for n in page_nums if n not in done]
    print("pages=%d todo=%d already=%d" % (len(page_nums), len(todo), len(done)), flush=True)

    engine = RapidOCR(
        # 书籍为正向扫描件，方向分类（cls）纯属浪费：默认关闭
        use_cls=os.environ.get("OCR_USE_CLS", "0") == "1",
        rec_batch_num=int(os.environ.get("OCR_REC_BATCH", "16")),
        intra_op_num_threads=int(os.environ.get("OCR_THREADS", "-1")),
        inter_op_num_threads=int(os.environ.get("OCR_INTER_THREADS", "1")),
    )
    buf = []
    if done:
        with open(out_path, "r", encoding="utf-8", errors="replace") as fh:
            buf.append(fh.read())

    for i, n in enumerate(todo, 1):
        try:
            res, _ = engine(files[n])
        except Exception as e:  # 单页失败不影响整体
            res = None
            print("ERR page %d: %s" % (n, e), flush=True)
        rows = []
        if res:
            items = []
            for box, text, score in res:
                ys = [p[1] for p in box]
                xs = [p[0] for p in box]
                items.append((sum(ys) / len(ys), min(xs), text))
            items.sort(key=lambda t: t[0])
            for y, x, text in items:
                if rows and abs(y - rows[-1][0]) < 15:
                    rows[-1][1].append((x, text))
                else:
                    rows.append([y, [(x, text)]])
            lines = ["".join(t for _, t in sorted(cells)) for _, cells in rows]
        else:
            lines = []
        buf.append("\n【第 %d 页】\n" % n + "\n".join(lines))
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("".join(buf))
        print("[%d/%d] p%d lines=%d" % (i, len(todo), n, len(lines)), flush=True)

    print("DONE ocr pages=%d -> %s" % (len(todo), out_path))


if __name__ == "__main__":
    main()
