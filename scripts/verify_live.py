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

**輸出只寫進檔案，畫面上不印結論**（2026-10-08）：完整輸出寫在 data/local/logs/verify-live-<時間>.log，畫面只印那個路徑。
理由：「直接截命令輸出的最後一行」比「先存檔再讀」順手，這個專案因此兩次查不到失敗的是哪一項；
讓結論只存在檔案裡，讀的人就非得打開檔案不可，這條教訓不必再靠記得。
每一次 HTTP 存取都記下時間、狀態碼、回應大小、耗時（連線錯誤也記）——偶發失敗時留下證據，不再只能「重跑、重現不出來」。
"""
import json
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
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

LOGDIR = ROOT / "data" / "local" / "logs"
fails = 0
failed = []   # 不符的檢查名稱：總結行直接列出（2026-10-08 一次「1 項不符」因為只截了最後一行而查不到是哪一項）


def out(msg):
    """每一行加時間戳記；main() 執行時 stdout 已經轉到記錄檔。"""
    print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {msg}", flush=True)


def check(desc, ok, detail=""):
    global fails
    out(f"{'✓' if ok else '✗'} {desc}{'' if ok else '：' + str(detail)}")
    if not ok:
        fails += 1
        failed.append(desc)
    return ok


def fetch(url):
    """回傳 (HTTP 狀態, 內容 bytes)。加時間參數避開 CDN 快取。"""
    # 檔名有中文（docs/A_範圍評估.md 等）：網址要先編碼（2026-10-08 第一次線上驗證時當在這裡）
    url = urllib.parse.quote(url, safe=":/?&=%#")
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}v={int(time.time())}", headers={"User-Agent": "certquiz-verify", "Cache-Control": "no-cache"})
    t0 = time.time()
    st, body, err = None, b"", ""
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            st, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        st = e.code
    except Exception as e:   # 連線錯誤、逾時：記下來、當成失敗回傳，不讓整支程式炸掉而什麼都沒留下
        err = f"{type(e).__name__}: {e}"
    out(f"· HTTP {st if st is not None else '—'} {len(body)}B {int((time.time() - t0) * 1000)}ms {urllib.parse.unquote(url)}{('｜' + err) if err else ''}")
    return st, body


def compare_files(base, files, local_bytes):
    """逐一抓線上的檔跟本機內容比。回傳 (實際比對過的路徑清單, 不一致清單, {路徑: 線上內容})。
    「實際比對過」要回報出來，呼叫端核對數量——不能讓某個路徑（例如中文檔名）被靜默跳過還回報全部通過。
    守這件事的測試：scripts/test_verify_live.py。"""
    compared, mismatch, online = [], [], {}
    for f in files:
        st, body = fetch(base + f)
        local = local_bytes(f)
        online[f] = body
        compared.append(f)
        if st != 200 or body != local:
            mismatch.append(f"{f}（HTTP {st}，線上 {len(body)} B／本機 {len(local)} B）")
    return compared, mismatch, online


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, check=True).stdout


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    LOGDIR.mkdir(parents=True, exist_ok=True)
    path = LOGDIR / f"verify-live-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.log"
    screen = sys.stdout
    screen.write(f"VERIFY-LIVE：完整輸出與結論都寫在 {path}（畫面不印結論；結束碼 0＝全部符合、1＝有不符、2＝中止）\n")
    screen.flush()
    with path.open("w", encoding="utf-8") as f:
        sys.stdout = sys.stderr = f
        try:
            out(f"開始（UTC {datetime.now(timezone.utc).isoformat(timespec='seconds')}）")
            return run()
        except Exception:
            out("VERIFY-LIVE ABORT：程式例外\n" + traceback.format_exc())
            return 2
        finally:
            sys.stdout, sys.stderr = screen, sys.__stderr__


def run():
    base = sys.argv[1].rstrip("/") + "/"
    head = git("rev-parse", "HEAD").decode().strip()
    files = [f for f in git("ls-tree", "-r", "--name-only", "-z", "HEAD").decode("utf-8").split("\0") if f]
    stems, n_packs = S.load_stems(ROOT)
    if not stems:
        out("VERIFY-LIVE ABORT：本機沒有匯入包，V4 沒有東西可比（不能拿「沒比到」當成「沒有」）")
        return 2
    out(f"• 線上：{base}｜本機 HEAD {head[:8]}｜追蹤中的檔 {len(files)} 個｜R7 題幹 {len(stems)} 題")

    # ---- 驗尺
    known = "index.html"
    st, _ = fetch(base + known)
    ruler_v3 = check(f"驗尺 V3：本機 HEAD 有的檔線上回 200（{known} → {st}）", st == 200)
    probe = next(iter(stems))
    ruler_v4 = check("驗尺 V4：拿一題真的題幹餵進比對函式必須命中 R7",
                     any(r == "R7" for r, _ in S.check_one("probe.html", ("<p>" + probe + "</p>").encode("utf-8"), (), stems)))
    if not (ruler_v3 and ruler_v4):
        out("VERIFY-LIVE ABORT：驗尺失敗，後面的結論不成立")
        return 2

    # ---- V1 noindex（讀線上的 HTML）
    st, html = fetch(base)
    text = html.decode("utf-8", "replace")
    check("V1 線上首頁帶著 robots noindex",
          st == 200 and re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I) is not None, f"HTTP {st}")
    check("V1 線上首頁帶著 CSP（connect-src 'self'）", "connect-src 'self'" in text)

    # ---- V2 每一個追蹤中的檔逐位元組相同；同時收集內容給 V4
    compared, mismatch, online = compare_files(base, files, lambda f: git("show", f"HEAD:{f}"))
    skipped = sorted(set(files) - set(compared))
    check(f"V2 線上 {len(compared)}／{len(files)} 個檔與本機 HEAD {head[:8]} 逐位元組相同（比對數＝追蹤檔數，沒有跳過）",
          not mismatch and not skipped, "；".join(mismatch[:5] + [f"沒比對到：{s}" for s in skipped[:5]]))

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

    out("VERIFY-LIVE OK：全部符合" if not fails else f"VERIFY-LIVE FAILED：{fails} 項不符（{'｜'.join(failed)}）")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
