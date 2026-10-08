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

**5xx 重試（Dispatch 2026-10-08 准做，範圍限死）**：
  - 只對 HTTP 5xx 重試；4xx、內容不符、逾時、連線錯誤一律不重試（逾時不重試是 Dispatch 2026-10-09 確認的：逾時可能是線上真的慢或掛了，那正是應該被看見的事）。
  - 最多 1 次（間隔 RETRY_WAIT 秒），重試仍失敗就照常判不符。
  - 記錄檔記下「首次 5xx、重試結果」，總結行註明本次重試了幾個檔。
  - 重試次數是訊號，不是雜訊：本次重試超過 MAX_RETRY_FILES 個檔、或連續 CONSEC_RUNS 次執行都有重試，就判紅，並寫明「線上不穩，不是內容不符」。
    跨次的紀錄存在 data/local/logs/verify-live-retries.tsv。

**正式／非正式執行分開放（2026-10-09，Dispatch：東西要帶得出建立者）**：
  只有「工作區的追蹤檔跟 HEAD 一致、而且跑的是 repo 裡這一份腳本」才算正式執行，記錄寫 data/local/logs/，跨次重試紀錄也只有它寫。
  其他（突變——改壞了追蹤中的檔；或跑的是腳本的副本）一律寫 data/local/logs/unofficial/，檔名帶 UNOFFICIAL、跨次紀錄另一份。
  這是程式自己判斷的，不靠執行的人記得加標記。記錄檔開頭寫明 HEAD、正式與否、哪些追蹤檔跟 HEAD 不一樣。
  CERTQUIZ_LOGDIR 環境變數可以指定記錄目錄（測試用：測試跑出來的記錄不該出現在任何一個正式目錄）。
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
# 每次執行一列：時間、HEAD、重試的檔數。測試要用環境變數改到暫存檔——測試的「0 次重試」寫進真的紀錄，會把連續重試的訊號打斷
import os  # noqa: E402
HISTORY = Path(os.environ.get("VERIFY_LIVE_HISTORY") or LOGDIR / "verify-live-retries.tsv")


def run_kind():
    """(正式與否, 說明)。正式＝追蹤檔與 HEAD 一致、而且跑的是 repo 裡這一份腳本。"""
    here = Path(__file__).resolve()
    if here != (ROOT / "scripts" / "verify_live.py").resolve():
        return False, f"跑的是腳本的副本（{here}），不是 repo 裡那一份"
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    dirty = [l[3:] for l in dirty if l.strip()]
    if dirty:
        return False, f"工作區有 {len(dirty)} 個追蹤檔跟 HEAD 不一樣：{'、'.join(dirty[:10])}"
    return True, "工作區與 HEAD 一致、跑的是 repo 裡的腳本"
RETRY_WAIT = 2.0
MAX_RETRY_FILES = 3    # 單次執行重試超過這麼多個檔＝線上不穩
CONSEC_RUNS = 3        # 連續這麼多次執行都有重試＝線上不穩
RETRIES = []           # 本次的重試：{url, first, second}
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
    """回傳 (HTTP 狀態, 內容 bytes)。加時間參數避開 CDN 快取。只有 5xx 會重試一次（見檔頭）。"""
    # 檔名有中文（docs/A_範圍評估.md 等）：網址要先編碼（2026-10-08 第一次線上驗證時當在這裡）
    url = urllib.parse.quote(url, safe=":/?&=%#")
    st, body = _fetch_once(url, "")
    if st is not None and 500 <= st <= 599:
        out(f"  ↻ 首次 HTTP {st}，{RETRY_WAIT:g} 秒後重試一次（只對 5xx）")
        time.sleep(RETRY_WAIT)
        st2, body = _fetch_once(url, "（重試）")
        RETRIES.append({"url": urllib.parse.unquote(url), "first": st, "second": st2})
        out(f"  ↻ 重試結果：HTTP {st2}{'（成功）' if st2 is not None and 200 <= st2 < 300 else '（仍失敗，照常判不符）'}")
        st = st2
    return st, body


def stable(n_retry_files):
    """單次執行的門檻：重試的檔數不超過 MAX_RETRY_FILES。"""
    return n_retry_files <= MAX_RETRY_FILES


def consecutive(history_counts):
    """跨次的門檻：最近 CONSEC_RUNS 次（含本次）都有重試＝不穩。history_counts 由舊到新。"""
    last = history_counts[-CONSEC_RUNS:]
    return not (len(last) == CONSEC_RUNS and all(n > 0 for n in last))


def _fetch_once(url, tag):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}v={int(time.time() * 1000)}", headers={"User-Agent": "certquiz-verify", "Cache-Control": "no-cache"})
    t0 = time.time()
    st, body, err = None, b"", ""
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            st, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        st = e.code
    except Exception as e:   # 連線錯誤、逾時：記下來、當成失敗回傳，不讓整支程式炸掉而什麼都沒留下
        err = f"{type(e).__name__}: {e}"
    out(f"· HTTP {st if st is not None else '—'} {len(body)}B {int((time.time() - t0) * 1000)}ms {urllib.parse.unquote(url)}{tag}{('｜' + err) if err else ''}")
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
    global HISTORY
    official, why = run_kind()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    if os.environ.get("CERTQUIZ_LOGDIR"):
        logdir = Path(os.environ["CERTQUIZ_LOGDIR"])
    else:
        logdir = LOGDIR if official else LOGDIR / "unofficial"
    if not official and not os.environ.get("VERIFY_LIVE_HISTORY"):
        HISTORY = LOGDIR / "unofficial" / "verify-live-retries-UNOFFICIAL.tsv"   # 非正式執行不得寫進正式的跨次紀錄
    logdir.mkdir(parents=True, exist_ok=True)
    path = logdir / f"verify-live-{stamp}{'' if official else '-UNOFFICIAL'}.log"
    screen = sys.stdout
    screen.write(f"VERIFY-LIVE：完整輸出與結論都寫在 {path}（畫面不印結論；結束碼 0＝全部符合、1＝有不符、2＝中止）\n")
    screen.flush()
    with path.open("w", encoding="utf-8") as f:
        sys.stdout = sys.stderr = f
        try:
            out(f"開始（UTC {datetime.now(timezone.utc).isoformat(timespec='seconds')}）｜{'正式執行' if official else '非正式執行'}：{why}｜HEAD {git('rev-parse', 'HEAD').decode().strip()[:8]}｜跨次重試紀錄：{HISTORY}")
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

    # ---- V0 線上穩定性：重試次數是訊號
    n = len({r["url"] for r in RETRIES})
    check(f"V0 線上穩定性：本次 5xx 重試 {n} 個檔（超過 {MAX_RETRY_FILES} 個就算線上不穩）", stable(n),
          "線上不穩，不是內容不符：" + "、".join(f"{r['url']}（{r['first']}→{r['second']}）" for r in RETRIES[:8]))
    hist = []
    if HISTORY.exists():
        hist = [int(l.split("\t")[2]) for l in HISTORY.read_text(encoding="utf-8").splitlines() if l.count("\t") >= 2 and l.split("\t")[2].isdigit()]
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{head[:8]}\t{n}\n")
    hist.append(n)
    check(f"V0 線上穩定性：最近 {CONSEC_RUNS} 次執行不是每次都有重試（最近幾次的重試檔數：{hist[-CONSEC_RUNS:]}）", consecutive(hist),
          f"線上不穩，不是內容不符：連續 {CONSEC_RUNS} 次執行都有 5xx 重試")
    note = f"（本次 5xx 重試 {n} 個檔：成功 {sum(1 for r in RETRIES if r['second'] is not None and 200 <= r['second'] < 300)}、仍失敗 {sum(1 for r in RETRIES if not (r['second'] is not None and 200 <= r['second'] < 300))}）" if RETRIES else ""
    out(("VERIFY-LIVE OK：全部符合" if not fails else f"VERIFY-LIVE FAILED：{fails} 項不符（{'｜'.join(failed)}）") + note)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
