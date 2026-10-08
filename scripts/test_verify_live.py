#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_live.py 的測試：中文檔名（與空白）的路徑一定要真的被抓、被比，不能當掉、也不能被靜默跳過
--------------------------------------------------------------------------------------------
起因（2026-10-08）：第一次線上驗證在中文檔名的網址編碼當掉。當時靠「當掉會回傳失敗」才沒被當成通過——
那是運氣好，不是設計；下一次它可能不是當掉，而是把那個路徑跳過，然後回報「全部通過」。

做法：在本機起一個靜態伺服器（scripts/serve.py），放三個檔（英文、中文檔名、含空白），用 verify_live 的
compare_files 去比：
    A 原樣 → 三個都比對過（含中文檔名）、0 筆不一致
    B 伺服器上的中文檔內容跟「本機」不同 → 必須點名那個中文檔不一致（正對照：證明它真的被抓來比，不是跳過）
任何例外都算這一項不符（當掉不等於通過）。
結束碼：0 全部符合；1 有不符；2 前提不成立。
"""
import http.server
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_live as V  # noqa: E402

ZH = "docs/中文檔名_範圍評估.md"
FILES = {"index.html": b"<p>ok</p>\n", ZH: "中文內容\n".encode("utf-8"), "docs/有 空白.txt": b"space\n"}


def main():
    site = Path(tempfile.mkdtemp(prefix="certquiz-vl-"))
    proc = None
    fails = 0
    try:
        for rel, data in FILES.items():
            (site / rel).parent.mkdir(parents=True, exist_ok=True)
            (site / rel).write_bytes(data)
        proc = subprocess.Popen([sys.executable, "-I", str(ROOT / "scripts" / "serve.py"), str(site), "0"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        line = proc.stdout.readline().decode()
        if not line.startswith("SERVING "):
            print(f"TEST-VERIFY-LIVE ABORT：伺服器沒啟動（{line!r}）")
            return 2
        base = f"http://127.0.0.1:{line.split()[1]}/"
        files = list(FILES)

        def case(desc, local, expect_mismatch):
            nonlocal fails
            try:
                compared, mismatch, _ = V.compare_files(base, files, local)
            except Exception as e:   # 當掉＝不符（不是通過）
                print(f"✗ {desc}：當掉 {type(e).__name__}: {e}")
                fails += 1
                return
            names = [m.split("（")[0] for m in mismatch]
            ok = compared == files and ZH in compared and names == expect_mismatch
            print(f"{'✓' if ok else '✗'} {desc}：比對 {len(compared)}／{len(files)}、不一致 {names or '無'}")
            fails += 0 if ok else 1

        case("A 原樣：中文檔名與含空白的路徑都抓得到、都一致", lambda f: FILES[f], [])
        case("B 正對照：中文檔內容不同 → 必須點名它", lambda f: (b"x" if f == ZH else FILES[f]), [ZH])

        # C 輸出規約：畫面只有一行（記錄檔路徑），不印結論；結論與每一次 HTTP 存取（狀態碼、大小）都在記錄檔裡
        hist_tmp = site / "retries.tsv"   # 不寫進真的跨次紀錄
        hist_real = ROOT / "data" / "local" / "logs" / "verify-live-retries.tsv"
        before = hist_real.read_bytes() if hist_real.exists() else None
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "verify_live.py"), base], capture_output=True,
                           env={**os.environ, "VERIFY_LIVE_HISTORY": str(hist_tmp)})
        after = hist_real.read_bytes() if hist_real.exists() else None
        screen = r.stdout.decode("utf-8", "replace").strip().splitlines()
        m = re.search(r"寫在 (\S+\.log)", screen[0]) if len(screen) == 1 else None
        log = Path(m.group(1)) if m else None
        body = log.read_text(encoding="utf-8") if log and log.exists() else ""
        last = [l for l in body.splitlines() if l.strip()][-1:] or [""]
        ok = (len(screen) == 1 and m is not None and not re.search(r"VERIFY-LIVE (OK|FAILED|ABORT)", r.stdout.decode("utf-8", "replace"))
              and r.returncode == 1 and "VERIFY-LIVE FAILED" in last[0] and re.search(r"· HTTP 200 \d+B \d+ms", body)
              and re.search(r"· HTTP 404 \d+B \d+ms", body))
        ok = ok and before == after and hist_tmp.exists()
        print(f"{'✓' if ok else '✗'} C 輸出規約：畫面 {len(screen)} 行、不含結論；結論只在記錄檔最後一行（{last[0][13:60]}）；記錄檔有每次 HTTP 的狀態碼與大小；結束碼 {r.returncode}")
        fails += 0 if ok else 1
        if log and log.exists():
            log.unlink()

        # D～H 5xx 重試：只對 5xx、最多 1 次、仍失敗就紅；4xx 與內容不符不重試；重試檔數超過門檻＝線上不穩
        hits = {}

        class Flaky(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                hits[path] = hits.get(path, 0) + 1
                code = {"/flaky.txt": 503 if hits[path] == 1 else 200, "/down.txt": 503, "/gone.txt": 404}.get(path, 200)
                body = b"ok" if code == 200 else b""
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Flaky)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        fb = f"http://127.0.0.1:{srv.server_address[1]}/"
        V.RETRY_WAIT = 0
        try:
            def rcase(desc, path, want_st, want_hits, want_retries):
                nonlocal fails
                V.RETRIES.clear()
                st, _ = V.fetch(fb + path)
                ok = st == want_st and hits.get("/" + path, 0) == want_hits and len(V.RETRIES) == want_retries
                print(f"{'✓' if ok else '✗'} {desc}：HTTP {st}、請求 {hits.get('/' + path, 0)} 次、記下重試 {len(V.RETRIES)} 筆")
                fails += 0 if ok else 1
            rcase("D 首次 503、重試 200 → 拿到 200，記一筆重試", "flaky.txt", 200, 2, 1)
            rcase("E 一直 503 → 只重試 1 次（共 2 次請求），結果仍是 503（照常判不符）", "down.txt", 503, 2, 1)
            rcase("F 404 → 不重試（1 次請求）", "gone.txt", 404, 1, 0)
            V.RETRIES.clear()
            _, mm, _ = V.compare_files(fb, ["same.txt"], lambda f: b"different")
            ok = mm and hits.get("/same.txt") == 1 and not V.RETRIES
            print(f"{'✓' if ok else '✗'} G 內容不符 → 不重試（1 次請求）、照常判不符")
            fails += 0 if ok else 1
            ok = V.stable(3) and not V.stable(4) and V.consecutive([1, 0, 2]) and not V.consecutive([0, 1, 1, 1]) and V.consecutive([1, 1])
            print(f"{'✓' if ok else '✗'} H 門檻：本次重試 3 個檔還算穩、4 個就不穩；連續 3 次都有重試就不穩（只有 2 次紀錄時不判）")
            fails += 0 if ok else 1
        finally:
            srv.shutdown()
            V.RETRY_WAIT = 2.0
            V.RETRIES.clear()
    finally:
        if proc:
            proc.kill()
            proc.wait()
        shutil.rmtree(site, ignore_errors=False)
    print("TEST-VERIFY-LIVE OK：全部符合" if not fails else f"TEST-VERIFY-LIVE FAILED：{fails} 項不符")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
