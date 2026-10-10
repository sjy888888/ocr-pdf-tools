"""OCR 行级 JSONL → EPUB 构建器 v5：书签两级目录 + 引文转章末注释 + 引号标点修复 + 听书友好排版。

在 v4 基础上增加：
  * fix_quotes —— Windows OCR 把中文引号识别成 ASCII 直引号，按奇偶配对还原 “ ” ‘ ’
  * tidy —— 清理 OCR 标点垃圾（"，．" → "。"、连续句号、行首标点）

Usage: python jsonl2epub5.py <in.jsonl> <out.epub> <title> <author> <pdf>
"""
import sys
import os
import re
import json
import html
import uuid
import zipfile
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citations import extract as extract_cites  # noqa: E402

jsonl, out_epub, title, author, pdf_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
PAGENUM = re.compile(r"^[ivxlcdm\d\s\-—·.．]{1,8}$", re.I)
SKIP = re.compile(r"^(封面|封底|书名页|版权页|目录|目次|扉页|内容提要|前言|序言)\s*$")
FRAG = "扌亻氵忄讠纟阝卩刂疒土宀犭饣礻衤罒罓"


def fix_line(t):
    t = re.sub(r"(?<=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])[ \t]+", "", t)
    t = re.sub(r"[ \t]+(?=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])", "", t)
    return t.strip()


norm = lambda s: re.sub(r"[\d\s\-—·.．]+", "", s)


def fix_quotes(t):
    out = []
    dq = sq = 0
    for ch in t:
        if ch == '"':
            out.append("“" if dq % 2 == 0 else "”")
            dq += 1
        elif ch == "'":
            out.append("‘" if sq % 2 == 0 else "’")
            sq += 1
        else:
            out.append(ch)
    return "".join(out)


def tidy(t):
    t = re.sub(r"[，]\s*[．·]\s*", "。", t)
    t = re.sub(r"(?<=[。！？”])[．·]+", "", t)
    t = re.sub(r"[．·]{2,}", "。", t)
    t = re.sub(r"，\s*，", "，", t)
    t = re.sub(r"。\s*。", "。", t)
    t = re.sub(r"^[，。、．·]+", "", t)
    return t


def clean(t):
    return tidy(fix_quotes(fix_line(t)))


pages = []
with open(jsonl, encoding="utf-8") as f:
    for line in f:
        try:
            pages.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
pages.sort(key=lambda p: p["page"])
for p in pages:
    p["lines"] = [dict(l, t=clean(l["t"])) for l in p["lines"] if clean(l["t"])]
maxpage = max(p["page"] for p in pages)
print(f"[epub] {len(pages)} pages (engine={pages[0].get('engine','?')}), max {maxpage}")

# ---------- 书签：章 + 节 ----------
import pymupdf  # noqa: E402
doc = pymupdf.open(pdf_path)
toc = doc.get_toc()
doc.close()

CN = "[0-9一二三四五六七八九十百千万]"
CHAPT_RE = re.compile(r"^第\s*" + CN + r"+\s*[章篇卷]")
SECT_RE = re.compile(r"^第\s*" + CN + r"+\s*节")

chapters, sections = [], []
for lvl, t, pg in toc:
    t = t.strip()
    if not t or SKIP.match(t):
        continue
    if lvl == 1 and (CHAPT_RE.match(t) or t in ("后记", "结语", "结论", "结束语")):
        chapters.append((t[:60], int(pg)))
    elif lvl in (1, 2) and (SECT_RE.match(t) or re.match(r"^\d+\.\d+", t)):
        sections.append((re.sub(r"^(?:第\s*" + CN + r"+\s*节|\d+\.\d+)\s*", "", t)[:50], int(pg)))
    elif lvl == 1 and t == "思考题":
        sections.append(("思考题", int(pg)))
chapters.sort(key=lambda c: c[1])
sections.sort(key=lambda s: s[1])
print(f"[epub] 书签 {len(chapters)} 章 / {len(sections)} 节")
for c in chapters[:16]:
    print(f"    p{c[1]:<5} {c[0]}")

# ---------- 书眉 ----------
occ = {}
for p in pages:
    h = p["h"] or 1
    for l in p["lines"]:
        t = norm(l["t"])
        if not t or len(t) > 30:
            continue
        yc = (l["y0"] + l["y1"]) / 2 / h
        d = occ.setdefault(t, {"n": 0, "edge": 0, "pages": set()})
        if p["page"] in d["pages"]:
            continue
        d["pages"].add(p["page"])
        d["n"] += 1
        if yc < 0.12 or yc > 0.88:
            d["edge"] += 1
heads = {t for t, d in occ.items() if d["n"] >= 4 and d["edge"] / d["n"] >= 0.6}
print(f"[epub] 书眉候选 {len(heads)}")

# 按章定位的书眉：某页顶部若出现"该页所属章"的章名，判为书眉
# （OCR 对页眉大字的识别每页略有差异，靠"完全重复"抓不全）
page_chapter = {}
if chapters:
    ci = 0
    for pg in range(1, maxpage + 1):
        while ci + 1 < len(chapters) and chapters[ci + 1][1] <= pg:
            ci += 1
        if pg >= chapters[0][1]:
            page_chapter[pg] = norm(re.sub(r"^第\s*" + CN + r"+\s*章\s*", "", chapters[ci][0]))
print(f"[epub] 按章书眉判定启用：{len(page_chapter)} 页")

kept = []
for p in pages:
    h = p["h"] or 1
    probe = page_chapter.get(p["page"], "")
    lines = []
    for l in p["lines"]:
        t = l["t"]
        if norm(t) in heads:
            continue
        if probe and len(probe) >= 4:
            yc0 = l["y0"] / h
            nt = norm(t)
            if yc0 < 0.13 and nt and (probe in nt or (len(nt) >= 4 and nt in probe)):
                continue
        # 页面顶部（<8.5%）的短行且不以句读结尾 → 页眉（含 OCR 变体）
        ytop = l["y0"] / h
        if ytop < 0.085 and len(l["t"]) < 26 and not l["t"].endswith(("。", "！", "？", "：", "；", "，", "、", "”", "’")):
            continue
        yc = (l["y0"] + l["y1"]) / 2
        if PAGENUM.match(t) and (yc < h * 0.09 or yc > h * 0.91 or len(t) <= 4):
            continue
        lines.append(l)
    kept.append({"page": p["page"], "w": p["w"], "h": p["h"], "lines": lines})

# ---------- 重排 ----------
start_page = chapters[0][1] if chapters else 1
all_lines = [l for p in kept if p["page"] >= start_page for l in p["lines"]]
heights = [l["y1"] - l["y0"] for l in all_lines if l["y1"] > l["y0"]]
line_h = statistics.median(heights) if heights else 20
x0s = [round(l["x0"] / 4) * 4 for l in all_lines]
body_left = statistics.mode(x0s) if x0s else 0
body_right = max((l["x1"] for l in all_lines), default=0)
indent_th = line_h * 1.7
short_th = line_h * 2.6
print(f"[epub] line_h={line_h:.1f} left={body_left} right={body_right:.0f} start={start_page}")

probe_by_page = {c[1]: norm(re.sub(r"^第\s*" + CN + r"+\s*章\s*", "", c[0])) for c in chapters}
sec_norms = {norm(s[0]) for s in sections if len(norm(s[0])) >= 3}


def join(a, b):
    a, b = a.rstrip(), b.lstrip()
    if not a:
        return b
    if a.endswith("-") and re.match(r"^[a-z]", b):
        return a[:-1] + b
    if CJK.search(a[-1]) or CJK.search(b[0]):
        return a + b
    return a + " " + b


paras = []
cur = None
prev = None
for p in kept:
    if p["page"] < start_page:
        continue
    skip_upto = -1
    if p["page"] in probe_by_page:
        probe = probe_by_page[p["page"]]
        if probe:
            best_i, best_score = -1, 0.0
            for i, l in enumerate(p["lines"]):
                t = norm(l["t"])
                if not t:
                    continue
                score = 1.0 if (probe in t or t in probe) else len(set(probe) & set(t)) / max(1, len(set(probe)))
                if score > best_score:
                    best_score, best_i = score, i
            if best_score >= 0.6:
                skip_upto = best_i
                # 章首页的标题常出现两遍（书名页眉 + 大字标题），把上部的同类行一并跳过
                for j in range(best_i, min(best_i + 4, len(p["lines"]))):
                    tj = norm(p["lines"][j]["t"])
                    yj = p["lines"][j]["y0"] / max(1, p["h"] or 1)
                    if yj > 0.45:
                        break
                    if tj and (probe in tj or tj in probe):
                        skip_upto = max(skip_upto, j)
    for li, l in enumerate(p["lines"]):
        if li <= skip_upto:
            continue
        t = l["t"]
        nt = norm(t)
        if len(nt) >= 4 and len(t) <= 30 and any(nt in s or s in nt for s in sec_norms):
            if cur:
                paras.append(cur)
                cur = None
            paras.append({"t": t, "k": "h", "page": p["page"]})
            prev = None
            continue
        indented = (l["x0"] - body_left) > indent_th
        prev_short = prev is not None and body_right and (body_right - prev["x1"]) > short_th
        # 硬规则：不在句子中间断段 —— 上一行必须以句末标点收尾，才允许开新段
        prev_end = prev["t"].rstrip()[-1] if (prev and prev["t"].strip()) else ""
        prev_sentence_end = prev_end in "。！？…”’）"
        bullet = bool(re.match(r"^[·．•◆▪\-\*]|^[一二三四五六七八九十]+[、．.]|^[（(]\d+[）)]|^\d+[、．.]", t))
        if cur is None:
            cur = {"t": t, "k": "p", "page": p["page"]}
        elif bullet or (prev_sentence_end and (indented or prev_short)):
            paras.append(cur)
            cur = {"t": t, "k": "p", "page": p["page"]}
        else:
            cur["t"] = join(cur["t"], t)
        prev = l
if cur:
    paras.append(cur)


def is_junk(t):
    if len(t) > 4:
        return False
    if t.endswith(("。", "！", "？", "：", "；", "”", "’", "、", "，", "…")):
        return False
    if any(c in FRAG for c in t):
        return True
    if not CJK.search(t):
        return True
    return False


before = len(paras)
paras = [x for x in paras if x["k"] == "h" or not is_junk(x["t"])]
print(f"[epub] 段落 {len(paras)}（清掉 {before-len(paras)}）字符 {sum(len(x['t']) for x in paras)}")

# ---------- 引文 → 章末注释 ----------
ranges = []
for i, (c, s) in enumerate(chapters):
    e = chapters[i + 1][1] - 1 if i + 1 < len(chapters) else maxpage
    if e < s:
        e = s
    ranges.append((c, s, e))

out_chapters = []
total_notes = 0
for c, s, e in ranges:
    items = [x for x in paras if s <= x["page"] <= e]
    if not items:
        continue
    notes = []
    new_items = []
    for x in items:
        if x["k"] == "p":
            new_items.append({"t": extract_cites(x["t"], notes), "k": "p", "page": x["page"]})
        else:
            new_items.append(x)
    total_notes += len(notes)
    out_chapters.append((c, new_items, notes))
print(f"[epub] 章 {len(out_chapters)}　抽出引文 {total_notes} 条")

# ---------- 写 EPUB ----------
esc = lambda s: html.escape(s, quote=False)
CSS = """html,body{margin:0;padding:0;}
body{font-family:"Songti SC","Source Han Serif SC","Noto Serif CJK SC",serif;
     line-height:1.8;margin:0 6%;font-size:1em;color:#1a1a1a;}
h1{font-size:1.4em;line-height:1.6;margin:1.8em 0 1.2em;text-align:center;
   page-break-before:always;break-before:page;font-weight:bold;}
h2{font-size:1.15em;line-height:1.7;margin:1.6em 0 .8em;font-weight:bold;}
p{text-indent:2em;margin:0 0 .65em 0;text-align:justify;line-height:1.8;}
p.note{text-indent:0;font-size:.88em;color:#444;margin:0 0 .35em 0;}
h3.notes{font-size:1.05em;margin:1.8em 0 .6em;border-top:1px solid #ccc;padding-top:.8em;}
"""
files = {"OEBPS/style.css": CSS}
manifest, spine, nav_items = [], [], []
for i, (ctitle, items, notes) in enumerate(out_chapters, 1):
    name = f"text/ch{i:04d}.xhtml"
    parts = [f"<h1>{esc(ctitle)}</h1>"]
    last_h = None
    for x in items:
        if x["k"] == "h":
            n = norm(x["t"])
            if n == norm(ctitle) or n == last_h:
                continue
            last_h = n
            parts.append(f"<h2>{esc(x['t'])}</h2>")
        else:
            parts.append(f"<p>{esc(x['t'])}</p>")
    if notes:
        parts.append('<h3 class="notes">本章注释</h3>')
        for j, nt in enumerate(notes, 1):
            parts.append(f'<p class="note">[{j}] {esc(nt)}</p>')
    files[f"OEBPS/{name}"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN" lang="zh-CN">\n'
        f'<head><meta charset="utf-8"/><title>{esc(ctitle)}</title>'
        '<link rel="stylesheet" type="text/css" href="../style.css"/></head>\n'
        '<body>\n' + "\n".join(parts) + "\n</body></html>\n"
    )
    manifest.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>')
    spine.append(f'<itemref idref="c{i}"/>')
    nav_items.append(f'<li><a href="{name}">{esc(ctitle)}</a></li>')

files["OEBPS/nav.xhtml"] = (
    '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
    '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">\n'
    f'<head><meta charset="utf-8"/><title>{esc(title)}</title></head>\n<body>\n'
    f'<nav epub:type="toc" id="toc"><h1>{esc(title)}</h1><ol>\n' + "\n".join(nav_items) + "\n</ol></nav>\n</body></html>\n"
)
manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
files["OEBPS/content.opf"] = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    f'<dc:identifier id="bookid">urn:uuid:{uuid.uuid4()}</dc:identifier>\n'
    f'<dc:title>{esc(title)}</dc:title>\n<dc:creator>{esc(author or "佚名")}</dc:creator>\n'
    '<dc:language>zh-CN</dc:language>\n'
    '<meta property="dcterms:modified">2026-10-07T00:00:00Z</meta>\n</metadata>\n<manifest>\n'
    '<item id="css" href="style.css" media-type="text/css"/>\n' + "\n".join(manifest) +
    '\n</manifest>\n<spine>\n' + "\n".join(spine) + '\n</spine>\n</package>\n'
)
files["META-INF/container.xml"] = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
    '</container>\n'
)
os.makedirs(os.path.dirname(out_epub) or ".", exist_ok=True)
with zipfile.ZipFile(out_epub, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
    for name, data in files.items():
        z.writestr(name, data)
print(f"[epub] WROTE {out_epub} {os.path.getsize(out_epub)/1024:.0f} KB chapters={len(out_chapters)}")
