#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_basis.py 的測試（離線）：把 fetch 與授權查詢換成假的，證明每一種「依據不實」都會變紅、而且點名那一題。
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
PAD = "Padding text so the ruler probe has room to work with, repeated words repeated words repeated words. "
PAGE = ("<html><head><script>var hidden = 'Only inside a script tag, never visible on the page.';</script></head><body>"
        "<h1 id=\"title\">Overview page</h1><p>" + PAD * 3 + "</p>"
        "<h2 id=\"datacenters\">Datacenters and zones</h2>"
        "<p>An availability zone is a <b>logical grouping</b> of one or more physically\n   separate datacenters "
        "within a region.</p><p>" + PAD * 2 + "</p>"
        "<h2 id=\"other\">Other section</h2><p>" + PAD * 3 + "</p></body></html>")
# 改版後的頁面：同一句話被搬到 #other 那一節
MOVED = PAGE.replace("<p>An availability zone is a <b>logical grouping</b> of one or more physically\n   separate datacenters "
                     "within a region.</p>", "").replace("<h2 id=\"other\">Other section</h2><p>",
                     "<h2 id=\"other\">Other section</h2><p>" + QUOTE + " ")
# 改版後的頁面：那句話被改寫
REWORDED = PAGE.replace("logical grouping", "logical set")


def block(qid, quote=QUOTE, anchor="#datacenters", with_quote=True, hash_of=None):
    h = V.qhash(hash_of if hash_of is not None else quote)
    n = len(V.norm(hash_of if hash_of is not None else quote))
    lines = [f"=== {qid}", "type: single", "chapter: az900.all", "objective: B.1", "skill: 2", "stem: 題幹",
             "1: 甲", "2: 乙", "3: 丙", "4: 丁", "answer: 1", "source: original-ai", f"basis: {URL}"]
    if with_quote:
        lines.append(f"basis_quote: {quote}")
    lines += [f"basis_anchor: {anchor}", "basis_section: Datacenters and zones", f"basis_hash: {h}", f"basis_len: {n}",
              "explain: 解析。", ""]
    return "\n".join(lines)


def run(desc, text, expect_rc, expect_in=(), page=PAGE, fetch=None, parser=None, lic=(True, "假的 CC BY 4.0"), store=None):
    tmp = Path(tempfile.mkdtemp(prefix="certquiz-vb-"))
    saved = V.fetch, V.parse_blocks, V.license_of, V.QUOTE_STORE
    try:
        (tmp / "q").mkdir()
        (tmp / "q" / "q.txt").write_text(text, encoding="utf-8")
        (tmp / "store").mkdir()
        if store:
            (tmp / "store" / "az900.txt").write_text(store, encoding="utf-8")
        V.fetch = fetch or (lambda url: page)
        V.parse_blocks = parser or saved[1]
        V.license_of = lambda raw: lic
        V.QUOTE_STORE = tmp / "store"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = V.main([str(tmp / "q")])
        out = buf.getvalue()
        ok = rc == expect_rc and all(s in out for s in expect_in)
        print(f"{'✓' if ok else '✗'} {desc}：結束碼 {rc}")
        if not ok:
            print("    " + out.replace("\n", "\n    "))
        return ok
    finally:
        V.fetch, V.parse_blocks, V.license_of, V.QUOTE_STORE = saved
        shutil.rmtree(tmp)


def drop_last(path):
    """模擬將來解析器改壞、默默少讀一題。"""
    return _REAL_PARSE(path)[:-1]


def boom(url):
    raise OSError("network down")


def main():
    nq = lambda qid, **k: block(qid, with_quote=False, **k)  # noqa: E731 公開題目檔的樣子：沒有原文
    cases = [
        ("原樣（草稿、有原文）：原文逐字在頁上、在標記的章節 → 綠", block("az900-b1-001"), 0, ["核對了 1／1 題", "1 題有本機原文"]),
        ("原樣（公開檔、沒有原文）：只靠雜湊逐格比對找得到 → 綠", nq("az900-b1-001"), 0, ["1 題只有雜湊"]),
        ("公開檔＋本機原文庫：原文從 data/local/basis 讀到，走逐字比對 → 綠", nq("az900-b1-001"), 0, ["1 題有本機原文"],
         PAGE, None, None, (True, "x"), "=== az900-b1-001\nbasis_quote: " + QUOTE + "\n"),
        ("草稿原文改一個字、雜湊沒重算 → 紅、點名", block("az900-b1-001", QUOTE.replace("logical", "logicel"), hash_of=QUOTE), 1,
         ["az900-b1-001", "不一致"]),
        ("草稿原文改一個字、雜湊也重算（原文不在頁上）→ 紅、依據失效", block("az900-b1-001", QUOTE.replace("logical", "logicel")), 1,
         ["az900-b1-001", "依據失效"]),
        ("官方改寫了那句話（公開檔，只有雜湊）→ 紅、依據失效", nq("az900-b1-001"), 1, ["az900-b1-001", "依據失效"], REWORDED),
        ("官方把那句話搬到別的章節 → 紅、錨點過時", nq("az900-b1-001"), 1, ["az900-b1-001", "錨點過時", "#other"], MOVED),
        ("標錯錨點 → 紅、錨點過時", block("az900-b1-001", anchor="#other"), 1, ["az900-b1-001", "錨點過時"]),
        ("兩題一真一假 → 紅、只點名假的", block("az900-b1-001") + "\n" + nq("az900-b1-002", hash_of=QUOTE + " Extra."), 1,
         ["az900-b1-002"]),
        ("原文只出現在 <script> 裡（畫面上看不到）→ 紅", block("az900-b1-001", "Only inside a script tag, never visible on the page."),
         1, ["az900-b1-001", "依據失效"]),
        ("缺雜湊與錨點 → 紅、點名", block("az900-b1-001").replace("basis_hash: ", "x: ").replace("basis_anchor: ", "y: "), 1,
         ["az900-b1-001", "缺 basis_hash"]),
        ("頁面授權查不到 → 紅、點名", block("az900-b1-001"), 1, ["az900-b1-001", "授權查不到"], PAGE, None, None, (False, "沒有公開版")),
        ("抓不到頁面 → 不能算綠（結束碼 2）", block("az900-b1-001"), 2, ["抓不到"], PAGE, boom),
        ("沒有任何 AZ-900 題 → 不能算綠（結束碼 2）", "（空檔）\n", 2, ["沒有找到"]),
        ("解析器默默少讀一題（兩題都對）→ 紅（題數對不上）", block("az900-b1-001") + "\n" + block("az900-b1-002"), 1,
         ["核對了 1／2 題", "題數對不上"], PAGE, None, drop_last),
    ]
    fails = sum(0 if run(*c) else 1 for c in cases)
    if fails:
        print(f"TEST-VERIFY-BASIS FAILED：{fails} 項不符")
        return 1
    print(f"TEST-VERIFY-BASIS OK：{len(cases)} 項全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
