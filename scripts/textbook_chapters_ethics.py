#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
職業道德教材：逐題歸章（docs/M 第十一節；比照內控的 textbook_chapters.py）
-------------------------------------------------------------------------------
  python -u scripts/textbook_chapters_ethics.py sheet   616 題打亂（固定種子）分 7 批 → chapters-ethics-bNN.md（章節定義＋題目）＋空白判斷檔
  python -u scripts/textbook_chapters_ethics.py lock    7 批都填完 → 合併成 chapters-ethics.json、鎖雜湊

母體：116 年版考試範圍的職業道德（subject=eth、version=116）。章＝證基會公告的職業道德 7 項範圍；每題只歸一章，拿不準選最接近的。
章是導覽用途，不是驗證過的學習單位。
"""
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"
OUT = D / "chapters-ethics.json"
PACK = ROOT / "data" / "local" / "import" / "ethics-匯入包.json"
SEED, N_BATCH = 20261014, 7
CHAPTERS = [
    ("E1", "業務推廣與招攬", "推銷、廣告、招攬客戶、銷售行為的分寸（不誇大、不保證獲利、不不當勸誘）"),
    ("E2", "受託執行業務", "接受客戶委託後怎麼執行：依指示、善良管理人注意、為客戶最佳利益、不越權"),
    ("E3", "告知義務與通知", "對客戶的說明、揭露風險與費用、事前事後應通知的事項"),
    ("E4", "誠實信用原則", "誠實、公平、不欺瞞、不操縱、專業與勤勉等一般原則"),
    ("E5", "有關利益衝突", "員工、公司、客戶之間利益衝突的辨認與處理（自己交易、收受餽贈、兼職等）"),
    ("E6", "保密原則", "客戶資料與內線消息的保密、個資、不得洩漏或利用"),
    ("E7", "遵守法律規範與自律", "守法、遵守公會自律規範、內部規章、主管機關要求，以及違反時的處理"),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def questions():
    qs = json.loads(PACK.read_text(encoding="utf-8"))["questions"]
    return sorted([q for q in qs if q["subject"] == "eth" and q.get("version") == "116"], key=lambda q: q["id"])


def sheet():
    if (D / "chapters-ethics-b01.md").exists():
        print("SHEET ABORT：已經分過批了")
        return 2
    qs = questions()
    random.Random(SEED).shuffle(qs)
    size = -(-len(qs) // N_BATCH)
    defs = ["# 職業道德教材：逐題歸章", "", "每一題只歸**一章**：看這題主要在考哪一項。拿不準時選最接近的那一章（沒有「其他」）。",
            "章是為了讓讀的人好找，不必追求完美。", "", "## 章節定義（證基會公告的職業道德範圍）", ""]
    defs += [f"- **{c}　{n}**：{s}" for c, n, s in CHAPTERS] + [""]
    for b in range(N_BATCH):
        part = qs[b * size:(b + 1) * size]
        md = list(defs) + ["## 題目", ""]
        rows = ["題號\t章（填代號，例如 E3）"]
        for q in part:
            md += [f"### {q['id']}", q["stem"]] + [f"- ({k}) {o}" for k, o in enumerate(q["options"], 1)] + [""]
            rows.append(f"{q['id']}\t")
        (D / f"chapters-ethics-b{b + 1:02d}.md").write_text("\n".join(md), encoding="utf-8")
        (D / f"chapters-ethics-b{b + 1:02d}.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    log("chapters-ethics-sheet", Path(__file__))
    print(f"SHEET OK：{len(qs)} 題分 {N_BATCH} 批（每批 ≤ {size} 題）→ {D}")
    return 0


def lock():
    codes = {c for c, _, _ in CHAPTERS}
    merged, bad = {}, []
    for b in range(N_BATCH):
        p = D / f"chapters-ethics-b{b + 1:02d}.tsv"
        for line in p.read_text(encoding="utf-8").splitlines()[1:]:
            if line.strip():
                qid, code = (line.split("\t") + [""])[:2]
                code = code.strip()
                if code not in codes:
                    bad.append(f"{p.name}:{qid}={code!r}")
                merged[qid.strip()] = code
    ids = {q["id"] for q in questions()}
    if bad or set(merged) != ids:
        print(f"LOCK ABORT：格式不對 {bad[:5]}；缺 {sorted(ids - set(merged))[:5]}；多 {sorted(set(merged) - ids)[:5]}")
        return 2
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    log("chapters-ethics-lock", OUT)
    cnt = {}
    for v in merged.values():
        cnt[v] = cnt.get(v, 0) + 1
    names = {c: n for c, n, _ in CHAPTERS}
    print(f"LOCK OK：{len(merged)} 題 → {OUT}")
    for c in sorted(cnt):
        print(f"  {c} {names[c]}：{cnt[c]}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"sheet": sheet, "lock": lock}.get(cmd, lambda: (print(__doc__), 2)[1])())
