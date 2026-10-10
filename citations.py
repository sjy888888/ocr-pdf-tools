"""Turn inline bibliographic citations into end-of-chapter notes, so TTS reading is not
interrupted mid-sentence.

Handles the common Chinese scholarly patterns, e.g.
  （《马克思恩格斯文集》第2卷，人民出版社2009年版，第591页）
  （参见《列宁选集》第2卷，人民出版社1995年版，第624页）
  《列宁选集》第2卷，人民出版社1995年版，第624页。
Collects them per chapter and appends a 「本章注释」 section.
"""
import re

CITE_KEYS = ("卷", "页", "年版", "人民出版社", "出版社", "参见", "转引自", "同上", "文集", "全集", "选集", "第")
BRACKET_CITE = re.compile(r"[（(]([^（）()]{6,90}?)[）)]")
BARE_CITE = re.compile(r"(《[^》]{2,40}》[^。；！？\n]{0,60}?第\s*\d+\s*[页卷][^。；！？\n]{0,30})")


def looks_like_cite(s):
    if not s:
        return False
    hits = sum(1 for k in CITE_KEYS if k in s)
    if "参见" in s or "转引自" in s:
        return True
    if "年版" in s and "页" in s:
        return True
    if "《" in s and ("卷" in s or "页" in s):
        return True
    return hits >= 2 and ("页" in s or "卷" in s)


def extract(text, notes):
    """Replace citations in `text` with [n] markers; append originals to `notes`."""
    def repl_bracket(m):
        inner = m.group(1)
        if looks_like_cite(inner):
            notes.append(inner.strip())
            return f"[{len(notes)}]"
        return m.group(0)

    text = BRACKET_CITE.sub(repl_bracket, text)

    def repl_bare(m):
        s = m.group(1).strip()
        notes.append(s)
        return f"[{len(notes)}]"

    # bare citation without brackets, e.g. 《列宁选集》第2卷，人民出版社1995年版，第624页。
    text = BARE_CITE.sub(repl_bare, text)
    # tidy up a duplicated full stop produced by the substitution
    text = re.sub(r"([。！？])[\[［](\d+)[\]］]。", r"\1[\2]", text)
    return text
