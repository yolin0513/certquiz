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
    F 只有白名單 給使用者/ 底下有沒追蹤的檔 → 回 0（照常推送）
    G 給使用者/ 有沒追蹤的檔，另外別的位置也有一個 → 回 1（白名單只放行具名路徑）
    H 給使用者/ 底下的檔被加入暫存區 → 回 1（白名單只放行「沒追蹤」，不放行暫存的）
--mutate：在暫存 clone 裡把白名單改成萬用（放行所有沒追蹤的檔）再跑一次；G 必須變紅，才印 MUTATION CAUGHT、回 0。
  證明 G 真的在驗「只放行一個資料夾」，不是看起來只放行一個、實際上全放行。
結束碼：0 全部符合（--mutate：突變被抓到）；1 有不符（--mutate：突變沒被抓到）；2 前提不成立。
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


def git_bash():
    """Windows 上 subprocess 叫 "bash" 會先找到 System32 的 WSL bash（沒裝發行版就跑不起來），
    所以明確用 shutil.which 找到的完整路徑（Git Bash）。2026-10-08 踩過：五個情境全都沒跑起來。"""
    p = shutil.which("bash")
    if not p:
        raise RuntimeError("找不到 bash")
    return p


def pushsafe(work):
    r = sh([git_bash(), "scripts/pushsafe.sh", "origin"], work, check=False)
    out = r.stdout.decode("utf-8", "replace")
    last = [ln for ln in out.splitlines() if ln.startswith("PUSHSAFE:")][-1:] or ["(沒有 PUSHSAFE 輸出)"]
    return r.returncode, last[0]


def main():
    mutate = "--mutate" in sys.argv[1:]
    st = sh(["git", "-c", "core.quotePath=false", "status", "--porcelain", "-uall"], ROOT).stdout.decode("utf-8", "replace")
    if [ln for ln in st.splitlines() if not ln.startswith("?? 給使用者/")]:   # 同 pushsafe.sh 的白名單
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
        # clone 沒有本機匯入包（gitignored）：test_verify_live 的情境 C 會 ABORT，整條閘門在它那裡就停了，
        # 後面的情境全都「因為別的原因被擋」（2026-10-15 發現：A、F 預期推得上去卻被擋，而 C、D 的擋法不是它們該驗的那一關）。
        # 複製進暫存 clone（同樣被 .gitignore 排除、隨暫存目錄刪掉）。
        src = ROOT / "data" / "local" / "import"
        if not src.is_dir():
            print("TEST-PUSHSAFE ABORT：本機沒有 data/local/import，推送閘門在暫存 clone 跑不完")
            return 2
        shutil.copytree(src, work / "data" / "local" / "import")
        if mutate:
            ps = work / "scripts" / "pushsafe.sh"
            t = ps.read_text(encoding="utf-8")
            line = r"UNTRACKED_OK='^\?\? 給使用者/'"
            if t.count(line) != 1:
                print("TEST-PUSHSAFE ABORT：找不到白名單那一行，突變做不了")
                return 2
            ps.write_bytes(t.replace(line, r"UNTRACKED_OK='^\?\? '").encode("utf-8"))
            sh(["git", "commit", "-q", "--no-verify", "-am", "mutate: wildcard"], work)
            print("• 突變：白名單改成萬用（放行所有沒追蹤的檔）")
        results, lasts = {}, {}

        def case(desc, expect_rc, reason, setup=None, expect_remote=None):
            """reason：最後一行 PUSHSAFE 輸出必須含的字。只看回傳值不夠——腳本沒跑起來也會回 1。"""
            nonlocal fails
            before = remote_main(bare)
            if setup:
                setup()
            rc, last = pushsafe(work)
            after = remote_main(bare)
            want = expect_remote(before) if expect_remote else before
            if not last.startswith("PUSHSAFE:"):
                print(f"⊘ {desc}：情境未成立（腳本沒有 PUSHSAFE 輸出，回傳 {rc}）")
                fails += 1
                return
            ok = rc == expect_rc and after == want and reason in last
            results[desc[0]] = ok
            lasts[desc[0]] = last
            print(f"{'✓' if ok else '✗'} {desc}：回傳 {rc}（預期 {expect_rc}），假遠端 {'有變' if after != before else '沒變'}｜{last}")
            fails += 0 if ok else 1

        head = lambda: sh(["git", "rev-parse", "HEAD"], work).stdout.decode().strip()
        case("A 乾淨 → 推上去", 0, "推送成功", expect_remote=lambda _b: head())

        def dirty():
            (work / "stray.txt").write_text("x", encoding="utf-8")
        case("B 工作區不乾淨 → 擋", 1, "工作區不乾淨", dirty)
        (work / "stray.txt").unlink()

        def pdf_in_history():
            (work / "docs" / "leak.txt").write_bytes(b"%PDF-1.7 fake\n")
            sh(["git", "add", "docs/leak.txt"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "leak"], work)
            sh(["git", "rm", "-q", "docs/leak.txt"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "rm leak"], work)
        case("C 繞過 hook commit 過 PDF（已刪）→ 歷史掃描擋", 1, "selfcheck.py --history 沒過", pdf_in_history)
        sh(["git", "reset", "-q", "--hard", "HEAD~2"], work)

        def beacon():
            (work / "js" / "x.js").write_text("navigator.sendBeacon('data/x', d);\n", encoding="utf-8")
            sh(["git", "add", "js/x.js"], work)
            sh(["git", "commit", "-q", "--no-verify", "-m", "beacon"], work)
        case("D 繞過 hook commit 了 sendBeacon → 隱私檢查擋", 1, "check_privacy.py 沒過", beacon)
        sh(["git", "reset", "-q", "--hard", "HEAD~1"], work)

        def detach():
            sh(["git", "checkout", "-q", "--detach"], work)
        case("E HEAD 不在 main → 擋", 1, "HEAD 不在 main", detach)
        sh(["git", "checkout", "-q", "main"], work)

        def textbook_only():
            (work / "給使用者").mkdir(exist_ok=True)
            (work / "給使用者" / "x.html").write_text("x", encoding="utf-8")
        case("F 只有 給使用者/ 有沒追蹤的檔 → 照常推送", 0, "推送成功", textbook_only, expect_remote=lambda _b: head())

        def textbook_and_stray():
            textbook_only()
            (work / "stray.txt").write_text("x", encoding="utf-8")
        case("G 給使用者/ 之外還有沒追蹤的檔 → 擋", 1, "工作區不乾淨", textbook_and_stray)
        (work / "stray.txt").unlink()

        def textbook_staged():
            textbook_only()
            sh(["git", "add", "給使用者/x.html"], work)
        case("H 給使用者/ 的檔被暫存 → 擋", 1, "工作區不乾淨", textbook_staged)
        sh(["git", "reset", "-q", "給使用者/x.html"], work)
    finally:
        rmtree(tmp)
        if tmp.exists():
            print(f"✗ 暫存目錄沒刪掉：{tmp.name}")
            fails += 1
    if mutate:
        # G 要「因為白名單放行而推上去」才算抓到；被別的關卡擋下的紅不算
        if results.get("G") is False and "推送成功" in lasts.get("G", ""):
            print("MUTATION CAUGHT：白名單改成萬用時，情境 G 變紅")
            return 0
        print(f"MUTATION NOT CAUGHT：白名單改成萬用，情境 G 沒有因為被放行而推上去（{lasts.get('G', '沒跑')}）")
        return 1
    if fails:
        print(f"TEST-PUSHSAFE FAILED：{fails} 項不符")
        return 1
    print("TEST-PUSHSAFE OK：8 個情境全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
