#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收件：使用者自己提供的題庫 PDF → refs/user/（.gitignore 擋，不入庫）
----------------------------------------------------------------------
讀每個 PDF 第一頁，認出「第幾期、哪一科、哪一組」，複製成統一檔名，寫一行到收件清單。
只複製、不改原檔；同內容（md5 相同）的檔不重複收，但收件清單照記一筆「重複」。

用法：
    python scripts/intake_user_pdf.py <pdf> [<pdf> ...]

需要本機的 pdftotext（Git for Windows 內附）。
認不出來的檔放 refs/user/unsorted/，原檔名保留，清單註明「未辨識」。
"""
import hashlib
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "refs" / "user"
LOG = DEST / "收件清單.tsv"
HEADER = "收件時間\t原檔名\t存成\tmd5\t位元組\t主辦\t期別\t科目\t組別\t試卷標示題數\t狀態\n"


def first_page_text(pdf: Path) -> str:
    r = subprocess.run(["pdftotext", "-l", "1", "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"pdftotext 失敗：{r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8", "replace")


def identify(text: str):
    """回傳 dict（認不出的欄位是 None）。只認 TABF 的試卷版面；其他來源一律未辨識。"""
    info = {"org": None, "period": None, "subject": None, "group": None, "count": None, "kind": None}
    if "台灣金融研訓院" in text:
        info["org"] = "TABF"
    m = re.search(r"第\s*(\d+)\s*期", text)
    if m:
        info["period"] = int(m.group(1))
    m = re.search(r"科目[：:]\s*([^\n]+)", text)
    subj = m.group(1) if m else ""
    if "法規" in subj:
        info["subject"] = "法規"
        info["group"] = "一般消費共用" if ("一般" in subj and "消費" in subj) else ("消費金融" if "消費" in subj else "一般金融")
    elif "內部稽核" in subj:
        info["subject"] = "實務"
        info["group"] = "消費金融" if "消費" in subj else ("一般金融" if "一般" in subj else None)
    m = re.search(r"共\s*(\d+)\s*題", text)
    if m:
        info["count"] = int(m.group(1))
    if "正確答案" in text or re.search(r"題號.*節次|節次.*題號", text):
        info["kind"] = "答案"
        info["subject"] = "答案"
        info["group"] = "消費金融" if "消費" in text[:200] else "一般金融"
    elif info["subject"]:
        info["kind"] = "試卷"
    return info


def target_name(info) -> str | None:
    if info["org"] != "TABF" or not info["period"] or not info["subject"] or not info["group"]:
        return None
    if info["subject"] == "法規":
        return f"第{info['period']}期_法規({info['group']}).pdf"
    return f"第{info['period']}期_{info['group']}_{info['subject']}.pdf"


def main(paths):
    DEST.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text(HEADER, encoding="utf-8")
    known = {}
    for line in LOG.read_text(encoding="utf-8").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) > 3 and cols[10] in ("收入", "收入（同名不同內容，加註）"):
            known[cols[3]] = cols[2]
    rc = 0
    for raw in paths:
        src = Path(raw)
        data = src.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        if data[:5] != b"%PDF-":
            print(f"✗ 不是 PDF，沒收：{src.name}")
            rc = 1
            continue
        info = identify(first_page_text(src))
        name = target_name(info)
        status = "收入"
        if md5 in known:
            status, dest_rel = "重複（內容與已收的相同，沒再複製）", known[md5]
        else:
            if name is None:
                dest = DEST / "unsorted" / src.name
                status = "未辨識（放 unsorted，需人工判斷）"
            else:
                dest = DEST / "tabf" / name
                if dest.exists() and hashlib.md5(dest.read_bytes()).hexdigest() != md5:
                    dest = dest.with_name(dest.stem + f"_{md5[:6]}.pdf")
                    status = "收入（同名不同內容，加註）"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            dest_rel = dest.relative_to(ROOT).as_posix()
            known[md5] = dest_rel
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), src.name, dest_rel, md5, str(len(data)),
               info["org"] or "?", str(info["period"] or "?"), info["subject"] or "?", info["group"] or "?",
               str(info["count"] or "?"), status]
        with LOG.open("a", encoding="utf-8") as f:
            f.write("\t".join(row) + "\n")
        print(f"{'✓' if status.startswith('收入') else '•'} {src.name} → {dest_rel}｜第{row[6]}期 {row[7]} {row[8]}｜標示 {row[9]} 題｜{status}")
    return rc


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
