#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原創題的真值核對：每一題的 basis_quote 必須逐字出現在它的 basis 網址那一頁上
-------------------------------------------------------------------------------
設計見 docs/I_原創題的真值.md。這是開發時的檢查工具（會連到 learn.microsoft.com 讀官方文件），
不是 App 的一部分——App 本身不連任何外部網址。

驗尺（常設規則 14、16）：抓到的第一頁上，直接從頁面文字中間截一段當正對照（必須命中），
再把那一段改一個字當反對照（必須不命中）。兩者都成立才採信後面的「命中」。
輸出「核對了幾題／應該核對幾題」（常設規則 15）。

用法：python scripts/verify_basis.py <題目檔或目錄> [...]
結束碼：0 全部命中；1 有題目的引用不在頁面上（逐題點名）；2 驗尺失敗、抓不到頁面或沒有題目。
"""
import html
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import parse_blocks  # noqa: E402


def norm(s: str) -> str:
    s = s.replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (certquiz verify_basis)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def contains(text: str, quote: str) -> bool:
    return norm(quote) in text


def collect(paths):
    """回傳 (題目, 應有題數)。應有題數直接數原始檔裡的「=== az900-」行，不經過 parse_blocks（常設規則 15）。"""
    qs, expected = [], 0
    for p in paths:
        p = Path(p)
        files = sorted(p.rglob("*.txt")) if p.is_dir() else [p]
        for f in files:
            expected += sum(1 for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith("=== az900-"))
            for line, q in parse_blocks(f):
                if q.get("id", "").startswith("az900-"):
                    qs.append((f"{f.name}:{line}", q))
    return qs, expected


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    qs, expected = collect(argv)
    if not qs:
        print("VERIFY-BASIS ABORT：沒有找到任何 AZ-900 題目")
        return 2
    pages = {}
    for _w, q in qs:
        url = q.get("basis", "")
        if url and url not in pages:
            try:
                pages[url] = page_text(fetch(url))
            except (urllib.error.URLError, OSError) as e:
                print(f"VERIFY-BASIS ABORT：抓不到 {url}（{e}）——抓不到不等於引用不在，不能下結論")
                return 2
    # 驗尺：從第一頁的文字中間截一段
    first = next(iter(pages.values()))
    mid = len(first) // 2
    probe = first[mid:mid + 80]
    flipped = probe[:40] + ("X" if probe[40] != "X" else "Y") + probe[41:]
    ok_pos, ok_neg = contains(first, probe), not contains(first, flipped)
    print(f"{'✓' if ok_pos else '✗'} 驗尺 正對照：頁面上真的有的一段文字必須命中")
    print(f"{'✓' if ok_neg else '✗'} 驗尺 反對照：同一段改一個字必須不命中")
    if not (ok_pos and ok_neg):
        print("VERIFY-BASIS ABORT：驗尺失敗")
        return 2
    bad = []
    for where, q in qs:
        url, quote = q.get("basis", ""), q.get("basis_quote", "")
        if not url or not quote or not contains(pages.get(url, ""), quote):
            bad.append(f"{q.get('id')}（{where}）：引用不在 {url or '(沒有 basis)'}")
    print(f"• 核對了 {len(qs)}／{expected} 題、{len(pages)} 個官方頁面")
    if len(qs) != expected:
        bad.append(f"題數對不上：原始檔有 {expected} 個「=== az900-」，只讀到 {len(qs)} 題")
    if bad:
        print(f"VERIFY-BASIS FAILED：{len(bad)} 題的引用不在頁面上")
        for b in bad:
            print(f"  {b}")
        return 1
    print(f"VERIFY-BASIS OK：{len(qs)} 題的引用都逐字出現在它引用的官方頁面上")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
