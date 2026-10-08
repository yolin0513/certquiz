#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pushsafe.sh 的驗法：在暫存目錄 clone 一份、接一個假遠端（暫存的 bare repo），逐一造情境。
**不碰真的 repo 與任何真的遠端**：clone 之後先把 origin 換成假遠端，並確認換掉了才開始。
情境：
    A 乾淨 → 回 0，假遠端 main ＝ 鎖定的 commit
    B 工作區有沒 commit 的檔 → 回 1，假遠端不動
    C 用 --no-verify 繞過 commit 自查，commit 一個 PDF 再刪掉 → 回 1（歷史掃描抓到），假遠端不動
    D 用 --no-verify commit 帶 sendBeacon 的 js → 回 1（隱私檢查抓到），假遠端不動
    E HEAD 不在 main → 回 1
結束碼：0 全部符合；1 有不符；2 前提不成立。
"""
import os
import shutil
import stat
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


def sh(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args))} 失敗：{r.stderr.decode('utf-8', 'replace')}")
    return r


def rmtree(p):
    def onerr(func, path, _e):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(p, onerror=onerr)


def remote_main(bare):
    r = sh(["git", "rev-parse", "-q", "--verify", "refs/heads/main"], bare, check=False)
    return r.stdout.decode().strip() or None


def pushsafe(work):
    r = sh(["bash", "scripts/pushsafe.sh", "origin"], work, check=False)
    out = r.stdout.decode("utf-8", "replace")
    last = [ln for ln in out.splitlines() if ln.startswith("PUSHSAFE:")][-1:] or ["(沒有 PUSHSAFE 輸出)"]
    return r.returncode, last[0]


def main():
    if sh(["git", "status", "--porcelain"], ROOT).stdout.strip():
        print("TEST-PUSHSAFE ABORT：真 repo 的工作區不乾淨，先 commit 再測（驗的是已 commit 的版本）")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix=f"certquiz-pushsafe-{os.getpid()}-"))
    fails = 0
    try:
        bare, work = tmp / "remote.git", tmp / "work"
        sh(["git", "init", "-q", "--bare", "-b", "main", str(bare)], tmp)
        sh(["git", "clone", "-q", "--no-local", str(ROOT), str(work)], tmp)
        sh(["git", "remote", "set-url", "origin", str(bare)], work)
        url = sh(["git", "remote", "get-url", "origin"], work).stdout.decode().strip()
        if Path(url).resolve() != bare.resolve():
            print(f"TEST-PUSHSAFE ABORT：origin 沒換成假遠端（{url}）")
            return 2
        for k, v in (("core.hooksPath", ".githooks"), ("user.email", "t@users.noreply.github.com"), ("user.name", "t")):
            sh(["git", "config", k, v], work)
        print(f"• 暫存 clone 的 origin 已換成假遠端（真 repo 的 origin 沒有被碰）")

        def case(desc, expect_rc, setup=None, expect_remote=None):
            nonlocal fails
            before = remote_main(bare)
            if setup:
                setup()
            rc, last = pushsafe(work)
            after = remote_main(bare)
            want = expect_remote(before) if expect_remote else before
            ok = rc == expect_rc and after == want
            print(f"{'✓' if ok else '✗'} {desc}：回傳 {rc}（預期 {expect_rc}），假遠端 {'有變' if after != before else '沒變'}｜{last}")
            fails += 0 if ok else 1

        head = lambda: sh(["git", "rev-parse", "HEAD"], work).stdout.decode().strip()
        case("A 乾淨 → 推上去", 0, expect_remote=lambda _b: head())

        def dirty():
            (work / "stray.txt").write_text("x", encoding="utf-8")
        case("B 工作區不乾淨 → 擋", 1, dirty)
        (work / "stray.txt").unlink()

        def pdf_in_history():
            (work / "docs" / "leak.txt").write_bytes(b"%PDF-1.7 fake\n")
            sh(["git", "add", "docs/leak.txt"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "leak"], work)
            sh(["git", "rm", "-q", "docs/leak.txt"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "rm leak"], work)
        case("C 繞過 hook commit 過 PDF（已刪）→ 歷史掃描擋", 1, pdf_in_history)
        sh(["git", "reset", "-q", "--hard", "HEAD~2"], work)

        def beacon():
            (work / "js" / "x.js").write_text("navigator.sendBeacon('data/x', d);\n", encoding="utf-8")
            sh(["git", "add", "js/x.js"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "beacon"], work)
        case("D 繞過 hook commit 了 sendBeacon → 隱私檢查擋", 1, beacon)
        sh(["git", "reset", "-q", "--hard", "HEAD~1"], work)

        def detach():
            sh(["git", "checkout", "-q", "--detach"], work)
        case("E HEAD 不在 main → 擋", 1, detach)
    finally:
        rmtree(tmp)
        if tmp.exists():
            print(f"✗ 暫存目錄沒刪掉：{tmp.name}")
            fails += 1
    if fails:
        print(f"TEST-PUSHSAFE FAILED：{fails} 項不符")
        return 1
    print("TEST-PUSHSAFE OK：5 個情境全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
