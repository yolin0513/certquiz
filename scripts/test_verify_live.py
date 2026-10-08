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
import re
import shutil
import subprocess
import sys
import tempfile
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
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "verify_live.py"), base], capture_output=True)
        screen = r.stdout.decode("utf-8", "replace").strip().splitlines()
        m = re.search(r"寫在 (\S+\.log)", screen[0]) if len(screen) == 1 else None
        log = Path(m.group(1)) if m else None
        body = log.read_text(encoding="utf-8") if log and log.exists() else ""
        last = [l for l in body.splitlines() if l.strip()][-1:] or [""]
        ok = (len(screen) == 1 and m is not None and not re.search(r"VERIFY-LIVE (OK|FAILED|ABORT)", r.stdout.decode("utf-8", "replace"))
              and r.returncode == 1 and "VERIFY-LIVE FAILED" in last[0] and re.search(r"· HTTP 200 \d+B \d+ms", body)
              and re.search(r"· HTTP 404 \d+B \d+ms", body))
        print(f"{'✓' if ok else '✗'} C 輸出規約：畫面 {len(screen)} 行、不含結論；結論只在記錄檔最後一行（{last[0][13:60]}）；記錄檔有每次 HTTP 的狀態碼與大小；結束碼 {r.returncode}")
        fails += 0 if ok else 1
        if log and log.exists():
            log.unlink()
    finally:
        if proc:
            proc.kill()
            proc.wait()
        shutil.rmtree(site, ignore_errors=False)
    print("TEST-VERIFY-LIVE OK：全部符合" if not fails else f"TEST-VERIFY-LIVE FAILED：{fails} 項不符")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
