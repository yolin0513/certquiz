#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原創題的真值核對：每一題的依據原文必須還在它引用的官方頁面上、在它標的章節裡、而且那一頁的授權查得到
-------------------------------------------------------------------------------
設計見 docs/I_原創題的真值.md。開發時的檢查工具（會連到 learn.microsoft.com 與 GitHub 讀公開文件），
不是 App 的一部分——App 本身不連任何外部網址（STATUS 規則 9 的界線）。

原文只留本機（Dispatch 2026-10-08）：公開的題目檔只存 basis（網址）、basis_anchor（章節錨點，# 代表頁首）、
basis_section（章節標題）、basis_hash（原文正規化後的 sha256）、basis_len（原文字數）。
原文本身在草稿檔（data/local/draft/）或本機原文庫（data/local/basis/*.txt），兩者都不進 repo。

每一題檢查：
  1. 有原文時：原文逐字在頁面上；sha256 與字數跟題目檔記的一致。
  2. 沒有原文時（例如別人 clone 下來）：在錨點那一節的文字上，用「字數＋雜湊」逐格比對——找得到才算依據還在。
  3. 錨點：原文要落在 basis_anchor 那一節；在頁面別處找到 → 「錨點過時」；整頁都找不到 → 「依據失效」。
  4. 授權：頁面中繼資料指向的原始 repo 必須在 GitHub 有公開版，而且那個 repo 的法律聲明授權文件內容為 CC BY 4.0；
     查不到就算不通過（「查不到不等於可以」，Dispatch 2026-10-08）。

驗尺（常設規則 14、16）：第一個頁面上截一段當正對照（必須命中），改一個字當反對照（必須不命中）；
雜湊逐格比對也用同一段驗一次。輸出「核對了幾題／應該核對幾題」（常設規則 15）。

用法：
  python scripts/verify_basis.py <題目檔或目錄> [...]   核對指定的題目
  python scripts/verify_basis.py --recheck              定期檢查：核對 data/src/az900 與 data/local/draft/az900 全部題目
  python scripts/verify_basis.py --fill <草稿檔> [...]   依草稿裡的原文算出錨點、章節、雜湊、字數，寫回草稿檔
結束碼：0 全部通過；1 有題目不通過（逐題點名）；2 驗尺失敗、抓不到頁面或沒有題目。
"""
import hashlib
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

ROOT = Path(__file__).resolve().parent.parent
QUOTE_STORE = ROOT / "data" / "local" / "basis"
RECHECK_DIRS = [ROOT / "data" / "src" / "az900", ROOT / "data" / "local" / "draft" / "az900"]


def norm(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (certquiz verify_basis)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def qhash(quote: str) -> str:
    return hashlib.sha256(norm(quote).encode("utf-8")).hexdigest()


class Page:
    """一個官方頁面：可見文字＋每個帶 id 的標題在可見文字裡的起點。"""

    def __init__(self, raw: str):
        self.raw = raw
        self.text = page_text(raw)
        self.sections = [("#", "", 0)]  # (錨點, 標題, 起點)
        for m in re.finditer(r"(?is)<h([1-6])\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</h\1>", raw):
            # 頁面標題（h1）與網站範本的標題（ms--in-this-article 之類）不是內容章節：落在那裡就是頁首導言（#）
            if m.group(1) == "1" or m.group(2).startswith("ms--") or m.group(2) == "module-unit-title":
                continue
            start = len(page_text(raw[:m.start()]))
            self.sections.append(("#" + m.group(2), norm(html.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))), start))

    def section_at(self, pos):
        best = self.sections[0]
        for s in self.sections:
            if s[2] <= pos + 1:
                best = s
        return best

    def span(self, anchor):
        """錨點那一節在可見文字裡的範圍；沒有這個錨點回 None。"""
        for i, s in enumerate(self.sections):
            if s[0] == anchor:
                end = min((t[2] for t in self.sections if t[2] > s[2]), default=len(self.text))
                return max(0, s[2] - 2), end
        return None

    def find_hash(self, h, n, lo=0, hi=None):
        """在 [lo, hi) 範圍內逐格找「長度 n、雜湊 h」的那段文字；回傳起點或 -1。"""
        t = self.text
        hi = len(t) if hi is None else min(hi + n, len(t))
        for i in range(lo, max(lo, hi - n + 1)):
            if hashlib.sha256(t[i:i + n].encode("utf-8")).hexdigest() == h:
                return i
        return -1


_LICENSE_CACHE = {}


def license_of(raw: str):
    """回傳 (ok, 說明)。頁面中繼資料 → 原始 repo（-pr 是私有的，對應公開版去掉 -pr）→ 公開版要有這個檔、法律聲明要授權 CC BY 4.0。"""
    m = re.search(r'name="original_content_git_url"\s+content="([^"]+)"', raw)
    if not m:
        return False, "頁面沒有標示原始 repo"
    rm = re.match(r"https://github\.com/MicrosoftDocs/([^/]+)/blob/[^/]+/(.+)$", m.group(1))
    if not rm:
        return False, f"原始 repo 不是 MicrosoftDocs：{m.group(1)}"
    repo = re.sub(r"-pr$", "", rm.group(1))
    if repo not in _LICENSE_CACHE:
        grant = ""
        for fn in ("ThirdPartyNotices.md", "LICENSE"):
            try:
                t = fetch(f"https://raw.githubusercontent.com/MicrosoftDocs/{repo}/main/{fn}")
            except (urllib.error.URLError, OSError):
                continue
            if "Creative Commons Attribution 4.0" in t or "Attribution 4.0 International" in t:
                grant = f"{fn} 授權 CC BY 4.0"
                break
        _LICENSE_CACHE[repo] = grant
    if not _LICENSE_CACHE[repo]:
        return False, f"MicrosoftDocs/{repo} 沒有公開版或查不到 CC BY 4.0 授權"
    try:
        fetch(f"https://raw.githubusercontent.com/MicrosoftDocs/{repo}/main/{rm.group(2)}")
    except (urllib.error.URLError, OSError):
        return False, f"公開版 MicrosoftDocs/{repo} 沒有這一頁的原始檔"
    return True, f"MicrosoftDocs/{repo}（{_LICENSE_CACHE[repo]}）"


def load_quotes():
    """本機原文庫：data/local/basis/*.txt，格式同題目檔（=== id ／ basis_quote: …）。"""
    quotes = {}
    if QUOTE_STORE.exists():
        for f in sorted(QUOTE_STORE.glob("*.txt")):
            for _, q in parse_blocks(f):
                if q.get("basis_quote"):
                    quotes[q["id"]] = q["basis_quote"]
    return quotes


def collect(paths):
    """回傳 (題目, 應有題數)。應有題數直接數原始檔裡的「=== az900-」行，不經過 parse_blocks（常設規則 15）。"""
    qs, expected = [], 0
    for p in paths:
        p = Path(p)
        files = sorted(p.rglob("*.txt")) if p.is_dir() else ([p] if p.exists() else [])
        for f in files:
            expected += sum(1 for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith("=== az900-"))
            for line, q in parse_blocks(f):
                if q.get("id", "").startswith("az900-"):
                    qs.append((f"{f.name}:{line}", q))
    return qs, expected


def check_one(q, page, quote):
    """回傳 None（通過）或不通過的理由。"""
    h, n, anchor = q.get("basis_hash", ""), q.get("basis_len", ""), q.get("basis_anchor", "")
    if not (re.fullmatch(r"[0-9a-f]{64}", h) and n.isdigit() and anchor.startswith("#")):
        return "缺 basis_hash／basis_len／basis_anchor（草稿先跑 --fill）"
    n = int(n)
    if quote is not None:
        if qhash(quote) != h or len(norm(quote)) != n:
            return "原文與記錄的雜湊或字數不一致（原文被改過，或欄位沒重算）"
        pos = page.text.find(norm(quote))
        if pos < 0:
            return "依據失效：原文已不在頁面上"
    else:
        sp = page.span(anchor)
        pos = page.find_hash(h, n, *sp) if sp else -1
        if pos < 0:
            pos = page.find_hash(h, n)
            if pos < 0:
                return "依據失效：頁面上找不到這段原文（雜湊比對）"
    sec = page.section_at(pos)
    if sec[0] != anchor:
        return f"錨點過時：原文還在，但在 {sec[0]}（{sec[1] or '頁首'}），不在 {anchor}"
    return None


def fill(paths):
    """草稿：依原文算出錨點、章節、雜湊、字數，寫回檔案。"""
    pages, changed = {}, 0
    for p in paths:
        p = Path(p)
        out, cur, extra = [], None, {}
        lines = p.read_text(encoding="utf-8").splitlines()
        blocks = {qid: q for _, q in parse_blocks(p) for qid in [q["id"]]}
        for ln in lines:
            if ln.startswith(("basis_anchor: ", "basis_section: ", "basis_hash: ", "basis_len: ")):
                continue
            out.append(ln)
            if ln.startswith("=== "):
                cur = blocks.get(ln[4:].strip())
            if ln.startswith("basis_quote: ") and cur:
                url = cur["basis"]
                if url not in pages:
                    pages[url] = Page(fetch(url))
                pg, quote = pages[url], cur["basis_quote"]
                pos = pg.text.find(norm(quote))
                if pos < 0:
                    print(f"FILL：{cur['id']} 的原文不在頁面上，沒有填")
                    continue
                anc, title, _ = pg.section_at(pos)
                out += [f"basis_anchor: {anc}"] + ([f"basis_section: {title}"] if anc != "#" else []) + \
                       [f"basis_hash: {qhash(quote)}", f"basis_len: {len(norm(quote))}"]
                changed += 1
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"FILL：填了 {changed} 題、{len(pages)} 個頁面")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--fill":
        return fill(argv[1:])
    paths = RECHECK_DIRS if argv[0] == "--recheck" else argv
    qs, expected = collect(paths)
    if not qs:
        print("VERIFY-BASIS ABORT：沒有找到任何 AZ-900 題目")
        return 2
    store = load_quotes()
    pages = {}
    for _w, q in qs:
        url = q.get("basis", "")
        if url and url not in pages:
            try:
                pages[url] = Page(fetch(url))
            except (urllib.error.URLError, OSError) as e:
                print(f"VERIFY-BASIS ABORT：抓不到 {url}（{e}）——抓不到不等於依據失效，不能下結論")
                return 2
    # 驗尺：第一頁中間截一段
    first = next(iter(pages.values()))
    probe = norm(first.text[len(first.text) // 2:len(first.text) // 2 + 80])
    mid = first.text.find(probe)
    flipped = probe[:40] + ("X" if probe[40] != "X" else "Y") + probe[41:]
    rulers = [
        ("逐字比對 正對照：頁面上真的有的一段文字必須命中", norm(probe) in first.text),
        ("逐字比對 反對照：同一段改一個字必須不命中", norm(flipped) not in first.text),
        ("雜湊比對 正對照：同一段只給雜湊與字數必須找得到", first.find_hash(qhash(probe), len(probe)) == mid),
        ("雜湊比對 反對照：改一個字的雜湊必須找不到", first.find_hash(qhash(flipped), len(flipped)) < 0),
    ]
    for d, ok in rulers:
        print(f"{'✓' if ok else '✗'} 驗尺 {d}")
    if not all(ok for _, ok in rulers):
        print("VERIFY-BASIS ABORT：驗尺失敗")
        return 2
    bad, licenses, n_quote = [], {}, 0
    for where, q in qs:
        url = q.get("basis", "")
        quote = q.get("basis_quote") or store.get(q.get("id"))
        n_quote += quote is not None
        if url not in pages:
            bad.append(f"{q.get('id')}（{where}）：沒有 basis")
            continue
        why = check_one(q, pages[url], quote)
        if url not in licenses:
            licenses[url] = license_of(pages[url].raw)
        if not licenses[url][0]:
            why = (why + "；" if why else "") + f"授權查不到：{licenses[url][1]}"
        if why:
            bad.append(f"{q.get('id')}（{where}）：{why}")
    print(f"• 核對了 {len(qs)}／{expected} 題、{len(pages)} 個官方頁面；其中 {n_quote} 題有本機原文（逐字比對），"
          f"{len(qs) - n_quote} 題只有雜湊（逐格比對）")
    print(f"• 授權查得到的頁面 {sum(1 for v in licenses.values() if v[0])}／{len(licenses)}")
    if len(qs) != expected:
        bad.append(f"題數對不上：原始檔有 {expected} 個「=== az900-」，只讀到 {len(qs)} 題")
    if bad:
        print(f"VERIFY-BASIS FAILED：{len(bad)} 題不通過")
        for b in bad:
            print(f"  {b}")
        return 1
    print(f"VERIFY-BASIS OK：{len(qs)} 題的依據都還在官方頁面上、在標記的章節裡，頁面授權都查得到")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
