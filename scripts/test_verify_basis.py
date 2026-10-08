#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_basis.py 的測試（離線）：把 fetch 換成假頁面，證明每一種「引用不實」都會變紅、而且點名那一題。
全部在暫存目錄裡做，不連網、不碰真的 data/。
結束碼：0 全部符合；1 有不符。
"""
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_basis as V  # noqa: E402

_REAL_PARSE = V.parse_blocks

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

URL = "https://learn.microsoft.com/en-us/azure/fake-page"
QUOTE = "An availability zone is a logical grouping of one or more physically separate datacenters within a region."
PAGE = ("<html><head><script>var hidden = 'Only inside a script tag, never visible on the page.';</script></head><body>"
        "<h1>Overview</h1><p>Intro text that pads the page so the ruler probe has room to work with, "
        "repeated words repeated words repeated words repeated words repeated words.</p>"
        "<p>An availability zone is a <b>logical grouping</b> of one or more physically\n   separate datacenters "
        "within a region.</p><p>Tail paragraph with more padding text for the probe, padding text, padding text, "
        "padding text, padding text.</p></body></html>")


def block(qid, quote=QUOTE, url=URL):
    return "\n".join([f"=== {qid}", "type: single", "chapter: az900.all", "objective: B.1", "stem: 題幹",
                      "1: 甲", "2: 乙", "3: 丙", "4: 丁", "answer: 1", "source: original-ai",
                      f"basis: {url}", f"basis_quote: {quote}", "explain: 解析。", ""])


def run(desc, text, expect_rc, expect_in=(), fetch=None, parser=None):
    tmp = Path(tempfile.mkdtemp(prefix="certquiz-vb-"))
    saved = V.fetch, V.parse_blocks
    try:
        (tmp / "q.txt").write_text(text, encoding="utf-8")
        V.fetch = fetch or (lambda url: PAGE)
        V.parse_blocks = parser or saved[1]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = V.main([str(tmp)])
        out = buf.getvalue()
        ok = rc == expect_rc and all(s in out for s in expect_in)
        print(f"{'✓' if ok else '✗'} {desc}：結束碼 {rc}")
        if not ok:
            print("    " + out.replace("\n", "\n    "))
        return ok
    finally:
        V.fetch, V.parse_blocks = saved
        shutil.rmtree(tmp)


def drop_last(path):
    """模擬將來解析器改壞、默默少讀一題。"""
    return _REAL_PARSE(path)[:-1]


def boom(url):
    raise OSError("network down")


def main():
    cases = [
        ("原樣：引用逐字在頁面上（跨標籤、跨換行）→ 綠", block("az900-b1-001"), 0, ["核對了 1／1 題"]),
        ("引用改一個字 → 紅、點名", block("az900-b1-001", QUOTE.replace("logical", "logicel")), 1, ["az900-b1-001"]),
        ("兩題一真一假 → 紅、只點名假的", block("az900-b1-001") + "\n" + block("az900-b1-002", QUOTE + " Extra."), 1, ["az900-b1-002"]),
        ("引用只出現在 <script> 裡（畫面上看不到）→ 紅", block("az900-b1-001", "Only inside a script tag, never visible on the page."), 1, ["az900-b1-001"]),
        ("缺 basis_quote → 紅、點名", block("az900-b1-001").replace(f"basis_quote: {QUOTE}\n", ""), 1, ["az900-b1-001"]),
        ("抓不到頁面 → 不能算綠（結束碼 2）", block("az900-b1-001"), 2, ["抓不到"], boom),
        ("沒有任何 AZ-900 題 → 不能算綠（結束碼 2）", "（空檔）\n", 2, ["沒有找到"]),
        ("解析器默默少讀一題（兩題都是真引用）→ 紅（題數對不上）", block("az900-b1-001") + "\n" + block("az900-b1-002"), 1, ["核對了 1／2 題", "題數對不上"], None, drop_last),
    ]
    fails = sum(0 if run(*c) else 1 for c in cases)
    if fails:
        print(f"TEST-VERIFY-BASIS FAILED：{fails} 項不符")
        return 1
    print(f"TEST-VERIFY-BASIS OK：{len(cases)} 項全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
