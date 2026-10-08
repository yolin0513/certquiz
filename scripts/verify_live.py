#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署後驗證：讀「線上」的內容，不是本機的檔
------------------------------------------
    V1 線上 index.html 帶著 robots noindex
    V2 repo HEAD 裡每一個追蹤中的檔，線上抓下來跟本機 HEAD 逐位元組相同（線上版本＝本機 HEAD）
    V3 只能留在本機的路徑線上都是 404（data/local/…、refs/…、匯入包、私人清單）
    V4 線上抓到的所有內容裡沒有任何內控官方題：①比對本機匯入包的題幹（R7 同一套）②沒有 tabf-official／user-import 來源欄位
    V5 線上 data/manifest.json 的內控公開題數是 0、沒有內控的題庫檔
驗尺：V3 與 V4 都先用已知樣本證明抓得到（V3：本機 HEAD 確實有的檔要回 200；V4：拿一題真的題幹餵進同一個比對函式必須命中）。
用法：python scripts/verify_live.py https://yolin0513.github.io/certquiz/
結束碼：0 全部符合；1 有不符；2 驗尺失敗或前提不成立。
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import selfcheck as S  # noqa: E402

fails = 0


def check(desc, ok, detail=""):
    global fails
    print(f"{'✓' if ok else '✗'} {desc}{'' if ok else '：' + str(detail)}")
    if not ok:
        fails += 1
    return ok


def fetch(url):
    """回傳 (HTTP 狀態, 內容 bytes)。加時間參數避開 CDN 快取。"""
    # 檔名有中文（docs/A_範圍評估.md 等）：網址要先編碼（2026-10-08 第一次線上驗證時當在這裡）
    url = urllib.parse.quote(url, safe=":/?&=%#")
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}v={int(time.time())}", headers={"User-Agent": "certquiz-verify", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, check=True).stdout


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/") + "/"
    head = git("rev-parse", "HEAD").decode().strip()
    files = [f for f in git("ls-tree", "-r", "--name-only", "-z", "HEAD").decode("utf-8").split("\0") if f]
    stems, n_packs = S.load_stems(ROOT)
    if not stems:
        print("VERIFY-LIVE ABORT：本機沒有匯入包，V4 沒有東西可比（不能拿「沒比到」當成「沒有」）")
        return 2
    print(f"• 線上：{base}｜本機 HEAD {head[:8]}｜追蹤中的檔 {len(files)} 個｜R7 題幹 {len(stems)} 題")

    # ---- 驗尺
    known = "index.html"
    st, _ = fetch(base + known)
    ruler_v3 = check(f"驗尺 V3：本機 HEAD 有的檔線上回 200（{known} → {st}）", st == 200)
    probe = next(iter(stems))
    ruler_v4 = check("驗尺 V4：拿一題真的題幹餵進比對函式必須命中 R7",
                     any(r == "R7" for r, _ in S.check_one("probe.html", ("<p>" + probe + "</p>").encode("utf-8"), (), stems)))
    if not (ruler_v3 and ruler_v4):
        print("VERIFY-LIVE ABORT：驗尺失敗，後面的結論不成立")
        return 2

    # ---- V1 noindex（讀線上的 HTML）
    st, html = fetch(base)
    text = html.decode("utf-8", "replace")
    check("V1 線上首頁帶著 robots noindex",
          st == 200 and re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I) is not None, f"HTTP {st}")
    check("V1 線上首頁帶著 CSP（connect-src 'self'）", "connect-src 'self'" in text)

    # ---- V2 每一個追蹤中的檔逐位元組相同；同時收集內容給 V4
    mismatch, online = [], {}
    for f in files:
        st, body = fetch(base + f)
        local = git("show", f"HEAD:{f}")
        online[f] = body
        if st != 200 or body != local:
            mismatch.append(f"{f}（HTTP {st}，線上 {len(body)} B／本機 {len(local)} B）")
    check(f"V2 線上 {len(files)} 個檔與本機 HEAD {head[:8]} 逐位元組相同", not mismatch, "；".join(mismatch[:5]))

    # ---- V3 本機專用路徑線上都是 404
    local_only = ["data/local/import/bic-匯入包.json", "data/local/src/bic/tabf-p49-law.txt", "data/local/抽檢/claude_核對.md",
                  "refs/tabf/past/第49期_一般金融_法規.pdf", "refs/user/收件清單.tsv", ".selfcheck-private.txt", "data/q/bic.json"]
    leaks = [f"{p}（HTTP {s}）" for p in local_only for s, _ in [fetch(base + p)] if s != 404]
    check(f"V3 本機專用的 {len(local_only)} 個路徑線上都是 404", not leaks, "；".join(leaks))

    # ---- V4 線上內容裡沒有內控官方題
    hits = []
    for f, body in list(online.items()) + [("(首頁)", html)]:
        for r, why in S.check_one(f, body, (), stems):
            if r in ("R3", "R7"):
                hits.append(f"{f}：{r} {why}")
    check(f"V4 線上 {len(online) + 1} 份內容都沒有內控題幹、沒有本機來源欄位", not hits, "；".join(hits[:5]))

    # ---- V5 線上題庫清單
    st, body = fetch(base + "data/manifest.json")
    try:
        m = json.loads(body)
        bic = next(c for c in m["certs"] if c["id"] == "bic")
        check(f"V5 線上 manifest：內控公開題數 {bic['bundledCount']}、題庫檔 {bic['bundledFile']}", bic["bundledCount"] == 0 and bic["bundledFile"] is None)
    except (ValueError, KeyError, StopIteration) as e:
        check("V5 線上 manifest 讀得到", False, f"HTTP {st}：{e}")

    print("VERIFY-LIVE OK：全部符合" if not fails else f"VERIFY-LIVE FAILED：{fails} 項不符")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
