#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_parallel.py —— 多进程并行 OCR 调度：分片跑 ocr_pages.py，再按页码合并成全书 txt。

用法:
    <rapid_venv>/python.exe ocr_parallel.py <pages目录> <输出txt> [分片数=4]

说明:
    - 每个分片一个子进程（Popen，Windows 下宽字符参数，中文路径安全）。
    - 子进程各自增量落盘 <输出txt>.partN，全部结束后按页码顺序合并。
    - 已有分片文件且含页码标记的页会被 ocr_pages.py 自动跳过（断点续跑）。
"""
import os
import re
import subprocess
import sys


def collect_pages(*paths):
    pages = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        for m in re.finditer(r"【第\s*(\d+)\s*页】\n(.*?)(?=\n?【第\s*\d+\s*页】|\Z)", txt, re.S):
            pages[int(m.group(1))] = m.group(2).strip("\n")
    return pages


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pages_dir = os.path.abspath(sys.argv[1])
    out_txt = os.path.abspath(sys.argv[2])
    nshards = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    from_p = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    to_p = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    order = (sys.argv[6] if len(sys.argv) > 6 else "asc").lower()

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_pages.py")
    nums = []
    for f in os.listdir(pages_dir):
        m = re.search(r"p(\d+)\.png$", f)
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        print("no pages in", pages_dir)
        sys.exit(2)
    total = max(nums)
    to_p = min(to_p or total, total)
    from_p = max(1, from_p)
    span = to_p - from_p + 1
    shard = (span + nshards - 1) // nshards

    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OCR_THREADS", "4"), PYTHONUTF8="1")
    procs = []
    parts = []
    for i in range(nshards):
        if order == "desc":
            e = to_p - i * shard
            s = max(e - shard + 1, from_p)
        else:
            s = from_p + i * shard
            e = min(s + shard - 1, to_p)
        if s > e:
            break
        part = "%s.part%d" % (out_txt, i)
        parts.append(part)
        log = open("%s.log%d" % (out_txt, i), "w", encoding="utf-8")
        procs.append((subprocess.Popen([sys.executable, script, pages_dir, part, str(s), str(e), order],
                                       stdout=log, stderr=subprocess.STDOUT, env=env), log))
        print("shard %d: pages %d-%d order=%s -> %s" % (i, s, e, order, part), flush=True)

    rc = 0
    for p, log in procs:
        rc |= p.wait()
        log.close()

    pages = collect_pages(*parts)
    with open(out_txt, "w", encoding="utf-8") as fh:
        for n in sorted(pages):
            fh.write("\n【第 %d 页】\n%s" % (n, pages[n]))
    chars = sum(len(v) for v in pages.values())
    print("MERGED pages=%d/%d chars=%d rc=%d -> %s" % (len(pages), total, chars, rc, out_txt))


if __name__ == "__main__":
    main()
