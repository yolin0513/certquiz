#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公開 repo 的自查閘門
--------------------
這個 repo 會公開（GitHub Pages）。下面這些東西一旦 commit 就算之後刪掉，也永遠留在歷史裡，
所以要在 commit 之前擋。.gitignore 只擋一般的 `git add`，擋不住 `git add -f`、也擋不住改了副檔名的檔，
這支程式不看 .gitignore，直接看「要進 commit 的東西」本身。

規則（每一條都有 --selftest 的假樣本證明會紅）：
    R1 路徑：refs/、data/local/ 底下的任何檔；副檔名 .pdf .docx .xlsx .pptx（不分大小寫）
    R2 內容：檔頭是 %PDF（改了副檔名的 PDF）、或是 Office 文件（PK 壓縮檔且含 word/ xl/ ppt/）
    R3 題目檔：有一行是 `source: tabf-official` 或 `source: user-import`（題庫原始檔的來源欄位）
    R4 本機路徑：Windows 使用者目錄、Git Bash 與 macOS 與 Linux 的使用者目錄寫法、
       Claude 的 session 目錄、本機 Windows 使用者名稱
    R5 email：除了 GitHub noreply 與 noreply@anthropic.com 以外的 email
    R6 個人資訊：(a) 以人稱開頭的個人處境敘述（他／她／使用者／我／你＋正在準備、要考、報考、單位、任職、
       就讀、升任……）與幾個不需要人稱也能指向個人的固定說法（清單見 PERSONAL_RE）；
       (b) 本機私人清單 .selfcheck-private.txt 的每一行（真實姓名、任職機構、學校等，區分大小寫）。
       私人清單本身不入庫（.gitignore＋R1 雙重擋）；清單不存在時照樣跑 (a)，並在輸出註明。

用法：
    python scripts/selfcheck.py            # 檢查暫存區（pre-commit 用）
    python scripts/selfcheck.py --history  # 檢查所有分支、所有 commit 裡出現過的每一個檔（pre-push 用）
    python scripts/selfcheck.py --selftest # 在暫存 repo 裡用假樣本證明每一條規則都會紅

結束碼：0 通過；1 擋下；2 程式本身出錯（出錯不等於通過）。
輸出：行首 `SELFCHECK OK` 或 `SELFCHECK BLOCKED`，被擋的每一項一行，行首兩格空白＋規則代號。
"""
import os
import re
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

BLOCKED_DIRS = ("refs/", "data/local/")
PRIVATE_LIST = ".selfcheck-private.txt"
# R6 (a)：一定要以人稱開頭，避免「摘要考題」「銀行主管是否也要考」這類一般敘述誤判
PERSONAL_RE = re.compile(
    r"(?:他|她|使用者|我|你)(?:本人)?\s*(?:目前|現在|正)?\s*"
    r"(?:正在準備|在準備|準備考|要考|要去考|去考|報考了?|考過|任職|服務於|就讀|在銀行|的單位|單位的|升任|升主管|是主管)"
    # 下面用 (?:) 把字拆開：比對效果不變，但這支檔自己的原始碼不會含有這些說法（不然會擋到自己）
    r"|在職(?:)考生|單位(?:)的要求|任職(?:)於|就讀(?:)於")
BLOCKED_EXT = (".pdf", ".docx", ".xlsx", ".pptx")
SOURCE_RE = re.compile(r"^\s*source:\s*(tabf-official|user-import)\b", re.M)
OFFICE_PARTS = (b"word/", b"xl/", b"ppt/")
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
EMAIL_OK = (b"@users.noreply.github.com", b"noreply@anthropic.com")
# 範例用的網域（RFC 2606）不算真的 email
EMAIL_EXAMPLE = re.compile(rb"@(example\.(com|org|net)|[A-Za-z0-9-]+\.(test|example|invalid))$")


def local_path_patterns():
    pats = [
        rb"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>|]+",       # Windows：磁碟代號＋Users＋名字（兩種斜線）
        rb"/[a-z]/Users/[^/\s\"'<>|]+",                         # Git Bash：單一字母磁碟＋Users＋名字
        rb"(?<![A-Za-z0-9_.-])/Users/[A-Za-z0-9._-]+/",         # macOS
        rb"(?<![A-Za-z0-9_.-])/home/[A-Za-z0-9._-]+/",          # Linux
        rb"\.claude[\\/]+projects[\\/]",                        # Claude session 目錄
        rb"AppData[\\/]+(Local|Roaming)[\\/]",
    ]
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(user) >= 2:
        pats.append(re.escape(user.encode("utf-8")))
    return [re.compile(p) for p in pats]


LOCAL_PATS = local_path_patterns()


def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def load_private(cwd):
    """讀本機私人清單；回傳 (字串清單, 檔案是否存在)。內容永遠不印出來。"""
    f = Path(cwd) / PRIVATE_LIST
    if not f.exists():
        return [], False
    items = []
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            items.append(s.encode("utf-8"))
    return items, True


def check_one(path: str, data: bytes, private=()):
    """回傳這個檔違反的規則清單：[(規則代號, 說明)]。"""
    hits = []
    low = path.lower()
    if low == PRIVATE_LIST or low.endswith("/" + PRIVATE_LIST):
        hits.append(("R1", "本機私人清單不得入庫"))
    if any(low.startswith(d) or f"/{d}" in f"/{low}" for d in BLOCKED_DIRS):
        hits.append(("R1", "位於只能留在本機的目錄"))
    if low.endswith(BLOCKED_EXT):
        hits.append(("R1", "PDF／Office 副檔名"))
    if data[:5] == b"%PDF-":
        hits.append(("R2", "內容是 PDF"))
    if data[:4] == b"PK\x03\x04" and any(p in data[:4096] for p in OFFICE_PARTS):
        hits.append(("R2", "內容是 Office 文件"))
    text = data.decode("utf-8", "replace")
    m = SOURCE_RE.search(text)
    if m:
        hits.append(("R3", f"題目檔（source: {m.group(1)}）"))
    for pat in LOCAL_PATS:
        m = pat.search(data)
        if m:
            hits.append(("R4", "本機路徑或使用者名稱（內容不顯示）"))
            break
    for m in EMAIL_RE.finditer(data):
        e = m.group(0)
        if not e.endswith(EMAIL_OK) and not EMAIL_EXAMPLE.search(e):
            hits.append(("R5", "email（內容不顯示）"))
            break
    m = PERSONAL_RE.search(text)
    if m:
        line = text.count("\n", 0, m.start()) + 1
        hits.append(("R6", f"第 {line} 行有個人處境敘述（{m.group(0)[:12]}）"))
    for term in private:
        if term in data or term in path.encode("utf-8"):
            line = data[: data.find(term)].count(b"\n") + 1 if term in data else 0
            hits.append(("R6", f"第 {line} 行有私人清單裡的字串（內容不顯示）"))
            break
    # 檔名本身也算內容（例如路徑裡帶使用者名稱）
    for pat in LOCAL_PATS:
        if pat.search(path.encode("utf-8")):
            hits.append(("R4", "檔名含本機路徑或使用者名稱"))
            break
    return hits


def staged_files(cwd):
    out = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT", cwd=cwd)
    return [p for p in out.decode("utf-8").split("\0") if p]


def scan_staged(cwd=ROOT):
    problems = []
    private, _ = load_private(cwd)
    files = staged_files(cwd)
    for p in files:
        data = git("show", f":{p}", cwd=cwd)
        for rule, why in check_one(p, data, private):
            problems.append((rule, p, why))
    return len(files), problems


def scan_history(cwd=ROOT):
    """所有 ref 可達的每一個 commit、每一個檔。同一個 blob 只讀一次，但每個出現過的路徑都檢查。"""
    problems, seen_blob, seen_pair = [], {}, set()
    private, _ = load_private(cwd)
    commits = git("rev-list", "--all", cwd=cwd).decode().split()
    for c in commits:
        tree = git("ls-tree", "-r", "-z", c, cwd=cwd).decode("utf-8")
        for entry in filter(None, tree.split("\0")):
            meta, path = entry.split("\t", 1)
            _mode, typ, sha = meta.split()
            if typ != "blob" or (sha, path) in seen_pair:
                continue
            seen_pair.add((sha, path))
            if sha not in seen_blob:
                seen_blob[sha] = git("cat-file", "blob", sha, cwd=cwd)
            for rule, why in check_one(path, seen_blob[sha], private):
                problems.append((rule, f"{path} @ {c[:8]}", why))
    return len(commits), len(seen_pair), problems


def report(scope, problems):
    _items, exists = load_private(ROOT)
    if not exists:
        scope += f"；注意：沒有 {PRIVATE_LIST}，R6 只檢查內建用語"
    if not problems:
        print(f"SELFCHECK OK（{scope}）")
        return 0
    print(f"SELFCHECK BLOCKED（{scope}）：{len(problems)} 項")
    for rule, where, why in problems:
        print(f"  {rule} {where}：{why}")
    print("  處理：git restore --staged <檔> 取消暫存；這些東西不能進公開 repo。")
    return 1


# ---------------------------------------------------------------- selftest
def _rmtree(p):
    def onerr(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(p, onerror=onerr)


def selftest():
    """在暫存 repo 裡逐條放假樣本：每一個都必須被「恰好那一條」規則擋下；乾淨樣本必須通過。"""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    # 樣本在執行時才組起來：這支檔自己也要通過自查，原始碼裡不能出現真的路徑或 email
    win_path = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "Desktop" + "\\" + "x.txt"
    bash_path = "/c/" + "Users" + "/someone/proj"
    session_dir = "~/." + "claude/" + "projects/abc/x"
    real_mail = "someone.real" + "@" + "gmail.com"
    cases = [
        # (說明, 路徑, 內容, 是否用 git add -f, 預期規則集合)
        ("乾淨的原創題檔", "data/src/az900/q.txt",
         "=== az900-a-o-0001\ntype: single\nsource: original-ai\n".encode(), False, set()),
        ("文件裡用反引號提到來源值（不是題目檔）", "docs/note.md",
         "部署時擋 `source: tabf-official` 的題目。\n".encode(), False, set()),
        ("範例網域的 email", "docs/mail.md", b"contact: someone@example.com\n", False, set()),
        ("refs/ 底下的假 PDF（-f 強制加入）", "refs/tabf/fake.pdf", b"%PDF-1.7 fake\n", True, {"R1", "R2"}),
        ("data/local/ 底下的題目檔（-f）", "data/local/bic.txt",
         "=== bic-law-t49-001\nsource: tabf-official\n".encode(), True, {"R1", "R3"}),
        ("改成 .txt 的 PDF", "docs/renamed.txt", b"%PDF-1.4 fake\n", False, {"R2"}),
        ("其他目錄的 .PDF（-f）", "docs/x.PDF", b"not really a pdf\n", True, {"R1"}),
        ("假的 docx（-f）", "docs/y.docx", b"PK\x03\x04....word/document.xml", True, {"R1", "R2"}),
        ("放在一般目錄的匯入題", "data/src/bic/import.txt",
         "=== u-1\nsource: user-import\n".encode(), False, {"R3"}),
        ("Windows 使用者路徑", "docs/path.md", f"見 {win_path}\n".encode(), False, {"R4"}),
        ("Git Bash 路徑", "scripts/p.sh", f"cd {bash_path}\n".encode(), False, {"R4"}),
        ("Claude session 目錄", "docs/s.md", f"{session_dir}\n".encode(), False, {"R4"}),
        ("真的 email", "docs/e.md", f"mail me: {real_mail}\n".encode(), False, {"R5"}),
    ]
    fake_org = "測試甲" + "機構"   # 私人清單的假樣本（執行時才組字串）
    cases += [
        ("個人處境敘述", "docs/p.md", ("使用者" + "正在準備考試\n").encode(), False, {"R6"}),
        ("固定說法（不需人稱）", "docs/p2.md", ("對" + "在職" + "考生來說\n").encode(), False, {"R6"}),
        ("私人清單裡的字串", "docs/q.md", f"合作對象：{fake_org}\n".encode(), False, {"R6"}),
        ("一般敘述不誤判（摘要考題、銀行主管是否也要考）", "docs/r.md",
         "連「摘要考題」都禁止；銀行主管是否也要考共同科目\n".encode(), False, set()),
        ("私人清單檔本身（-f）", PRIVATE_LIST, f"{fake_org}\n".encode(), True, {"R1", "R6"}),
    ]
    if len(user) >= 2:
        cases.append(("本機 Windows 使用者名稱", "docs/u.md", f"作者 {user}\n".encode(), False, {"R4"}))

    tmp = Path(tempfile.mkdtemp(prefix=f"certquiz-selftest-{os.getpid()}-"))
    fails = []
    try:
        git("init", "-q", "-b", "main", cwd=tmp)
        git("config", "user.email", "t@users.noreply.github.com", cwd=tmp)
        git("config", "user.name", "t", cwd=tmp)
        shutil.copy(ROOT / ".gitignore", tmp / ".gitignore")

        # 前提一：.gitignore 真的擋住一般的 git add（不靠讀 .gitignore 的內容判斷）
        for p in ("refs/a/b.pdf", "data/local/x.txt", "docs/z.pdf", PRIVATE_LIST):
            f = tmp / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"%PDF-1.7\n")
            r = subprocess.run(["git", "add", p], cwd=tmp, capture_output=True)
            staged = staged_files(tmp)
            ok = r.returncode != 0 and p not in staged
            print(f"{'✓' if ok else '✗'} .gitignore 擋一般 git add：{p}（回傳 {r.returncode}，已暫存={p in staged}）")
            if not ok:
                fails.append(f"gitignore {p}")
            f.unlink()

        # 私人清單（假的），放在 .gitignore 情境之後才建，免得被上面的迴圈刪掉
        (tmp / PRIVATE_LIST).write_text(f"# 測試用\n{fake_org}\n", encoding="utf-8")

        # 每一個樣本單獨一個情境
        for desc, path, content, force, expect in cases:
            git("reset", "-q", cwd=tmp, check=False)
            f = tmp / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(content)
            add = ["add", "-f", path] if force else ["add", path]
            git(*add, cwd=tmp)
            if path not in staged_files(tmp):
                print(f"⊘ 情境未成立（沒有進暫存區）：{desc}")
                fails.append(f"setup {desc}")
                continue
            _n, probs = scan_staged(tmp)
            got = {r for r, _p, _w in probs}
            ok = got == expect
            print(f"{'✓' if ok else '✗'} {desc}：預期 {sorted(expect) or '通過'}，實際 {sorted(got) or '通過'}")
            if not ok:
                fails.append(desc)
            git("rm", "-q", "--cached", path, cwd=tmp, check=False)
            if path == PRIVATE_LIST:   # 還原成假清單，後面的情境還要用
                f.write_text(f"# 測試用\n{fake_org}\n", encoding="utf-8")
            else:
                f.unlink()

        # 歷史掃描：繞過 pre-commit 進了 commit、之後刪掉，--history 仍要抓到
        (tmp / "docs").mkdir(exist_ok=True)
        (tmp / "docs/leak.txt").write_bytes(b"%PDF-1.4 leaked\n")
        git("add", "docs/leak.txt", cwd=tmp)
        git("commit", "-q", "--no-verify", "-m", "leak", cwd=tmp)
        git("rm", "-q", "docs/leak.txt", cwd=tmp)
        git("commit", "-q", "--no-verify", "-m", "delete leak", cwd=tmp)
        exists_now = (tmp / "docs/leak.txt").exists()
        _c, _f, probs = scan_history(tmp)
        ok = (not exists_now) and any(r == "R2" and w.startswith("docs/leak.txt") for r, w, _ in probs)
        print(f"{'✓' if ok else '✗'} 刪掉的檔仍在歷史裡，--history 要抓到：工作區還在={exists_now}，抓到={ok}")
        if not ok:
            fails.append("history")
    finally:
        _rmtree(tmp)
        if tmp.exists():
            print(f"✗ 暫存 repo 沒刪掉：{tmp.name}")
            fails.append("cleanup")

    if fails:
        print(f"SELFCHECK SELFTEST FAILED：{len(fails)} 項不符（{'；'.join(fails)}）")
        return 1
    print(f"SELFCHECK SELFTEST OK：{len(cases)} 個樣本＋4 個 .gitignore 情境＋1 個歷史情境全部符合")
    return 0


def main():
    try:
        if "--selftest" in sys.argv:
            return selftest()
        if "--history" in sys.argv:
            n_c, n_f, probs = scan_history()
            return report(f"歷史：{n_c} 個 commit、{n_f} 個檔案版本", probs)
        n, probs = scan_staged()
        return report(f"暫存區：{n} 個檔", probs)
    except Exception as e:  # 出錯不等於通過
        print(f"SELFCHECK ERROR：{type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
