#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_bench.py —— RapidOCR 配置基准测试（同一批页图，比较不同参数组合的耗时）

用法:
    <rapid_venv>/python.exe ocr_bench.py <页图1> [页图2 ...]

输出每种配置的 每页平均秒数，用于在本机选最优 OCR 参数。
"""
import sys
import time

from rapidocr_onnxruntime import RapidOCR

CONFIGS = [
    ("A 默认(含cls,batch6,线程-1)", {}),
    ("B 关cls,batch16,线程8", dict(use_cls=False, rec_batch_num=16,
                                   intra_op_num_threads=8, inter_op_num_threads=1)),
    ("C 关cls,batch6,线程8", dict(use_cls=False, rec_batch_num=6,
                                  intra_op_num_threads=8, inter_op_num_threads=1)),
    ("D 关cls,batch6,线程16", dict(use_cls=False, rec_batch_num=6,
                                   intra_op_num_threads=16, inter_op_num_threads=1)),
    ("E 关cls,batch6,线程4", dict(use_cls=False, rec_batch_num=6,
                                  intra_op_num_threads=4, inter_op_num_threads=1)),
]


def main():
    imgs = sys.argv[1:]
    if not imgs:
        print(__doc__)
        sys.exit(1)
    print("测试页数: %d" % len(imgs), flush=True)
    for name, kw in CONFIGS:
        try:
            engine = RapidOCR(**kw)
            engine(imgs[0])  # 预热，不计入
            t0 = time.time()
            for im in imgs:
                engine(im)
            dt = time.time() - t0
            print("%-28s %6.1fs / %d页 = %5.1f s/页" % (name, dt, len(imgs), dt / len(imgs)), flush=True)
        except Exception as exc:  # noqa: BLE001
            print("%-28s 失败: %s" % (name, exc), flush=True)


if __name__ == "__main__":
    main()
