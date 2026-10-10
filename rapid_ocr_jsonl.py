"""Batch RapidOCR over rendered page PNGs -> line-level JSONL (same schema as the
Windows OCR output, so the EPUB builder can consume either).

Usage: python rapid_ocr_jsonl.py <png_dir> <out.jsonl> [pages_per_log]
Resumable: pages already present in <out.jsonl> are skipped.
"""
import json
import os
import re
import sys
import time
import numpy as np
import cv2
from rapidocr_onnxruntime import RapidOCR

png_dir = sys.argv[1]
out_jsonl = sys.argv[2]
log_every = int(sys.argv[3]) if len(sys.argv) > 3 else 20

done = set()
if os.path.exists(out_jsonl):
    with open(out_jsonl, encoding="utf-8") as f:
        for line in f:
            try:
                done.add(json.loads(line)["page"])
            except Exception:  # noqa: BLE001
                pass

ocr = RapidOCR(use_cls=False, rec_batch_num=16, intra_op_num_threads=8, inter_op_num_threads=1)
pngs = sorted(n for n in os.listdir(png_dir) if n.lower().endswith(".png"))
print(f"[rapid] {len(pngs)} pages, already done {len(done)}", flush=True)

out = open(out_jsonl, "a", encoding="utf-8")
t0 = time.time()
proc = 0
for name in pngs:
    m = re.match(r"p(\d+)", name)
    page = int(m.group(1)) if m else 0
    if page in done:
        continue
    img = cv2.imdecode(np.fromfile(os.path.join(png_dir, name), np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        continue
    h, w = img.shape[:2]
    try:
        res = ocr(img)
    except Exception as e:  # noqa: BLE001
        print(f"[rapid] page {page} ERROR {e}", flush=True)
        res = None
    if isinstance(res, tuple) and len(res) == 2:
        res = res[0]
    lines = []
    for item in (res or []):
        try:
            box, txt, score = item[0], str(item[1]), float(item[2])
            ys = [float(p[1]) for p in box]
            xs = [float(p[0]) for p in box]
            lines.append({"t": txt, "x0": round(min(xs), 1), "y0": round(min(ys), 1),
                          "x1": round(max(xs), 1), "y1": round(max(ys), 1)})
        except Exception:  # noqa: BLE001
            continue
    lines.sort(key=lambda l: (l["y0"], l["x0"]))
    out.write(json.dumps({"page": page, "w": w, "h": h, "engine": "rapid", "lines": lines}, ensure_ascii=False) + "\n")
    out.flush()
    proc += 1
    if proc % log_every == 0:
        el = time.time() - t0
        per = el / proc
        left = (len(pngs) - len(done) - proc) * per
        print(f"[rapid] {proc}/{len(pngs)-len(done)}  {per:.2f}s/page  elapsed={el/60:.1f}min  eta={left/60:.1f}min", flush=True)
out.close()
print(f"[rapid] DONE processed={proc} -> {out_jsonl}", flush=True)
