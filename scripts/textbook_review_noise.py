#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「我們寫的」核對的雜訊（Dispatch 2026-10-14：同一段、沒改過的文字，前後被判出不同結果的比例）
-------------------------------------------------------------------------------
  python -u scripts/textbook_review_noise.py [起始時間 ISO]   只算判斷檔在起始時間之後鎖定的（預設：全部）

做法：
- 讀每一份 C1、抽樣、加抽的單子（.md）拿到「題號＋當時的說明文字」，再讀對應的判斷檔（.tsv）拿到判定。
- 以「題號＋說明文字」當同一段：文字一個字都沒改，才算同一段。
- 同一段被同一項（C1／C2／C4／C5）判過兩次以上，就是一組重複判定；判定不全相同＝不一致。
- C1 的判定來源有兩種：C1 全量（不矛盾／矛盾）與抽樣（合格／不合格），兩者都算。
- 「抽樣四項」＝抽樣或加抽裡四項全合格才算過（這是決定整批去留的那個判定）。
只印統計，不印題目或說明文字。
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"


def locked_at():
    t = {}
    for l in LOG.read_text(encoding="utf-8").splitlines():
        c = l.split("\t")
        if len(c) >= 3 and c[1] in ("ours-c1-lock", "ours-sample-lock", "ours-extra-lock"):
            t.setdefault(c[2], c[0])
    return t


def texts(md):
    out, cur = {}, None
    for l in md.read_text(encoding="utf-8").splitlines():
        if l.startswith(("## bic-", "## ethics-")):
            cur = l[3:].strip()
        elif cur and l.startswith("**說明**："):
            out[cur] = l[len("**說明**："):].strip()
            cur = None
    return out


def main(argv):
    since = argv[0] if argv else ""
    when = locked_at()
    judg = defaultdict(lambda: defaultdict(list))   # (題號, 文字) → 項目 → [判定]
    files = 0
    for md in sorted(D.glob("ours-*-*.md")):
        m = re.fullmatch(r"ours-([TE]\d+)-(c1|sample|extra)(-r\d+)?\.md", md.name)
        tsv = md.with_suffix(".tsv")
        if not m or not tsv.exists() or tsv.name not in when or when[tsv.name] < since:
            continue
        files += 1
        T = texts(md)
        for l in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            c = [x.strip() for x in l.split("\t")]
            if not l.strip() or c[0] not in T:
                continue
            key = (c[0], T[c[0]])
            if m.group(2) == "c1":
                judg[key]["C1"].append("過" if c[1] == "不矛盾" else "不過")
            else:
                for k, v in zip(("C1", "C2", "C4", "C5"), c[1:5]):
                    judg[key][k].append("過" if v == "合格" else "不過")
                judg[key]["抽樣四項"].append("過" if all(v == "合格" for v in c[1:5]) else "不過")
    print(f"判斷檔 {files} 份；不同的段（題號＋文字）{len(judg)} 段")
    for k in ("C1", "C2", "C4", "C5", "抽樣四項"):
        groups = [d[k] for d in judg.values() if len(d.get(k, [])) >= 2]
        inc = [g for g in groups if len(set(g)) > 1]
        pairs = sum(len(g) * (len(g) - 1) // 2 for g in groups)
        dis = sum(g.count("過") * g.count("不過") for g in groups)
        print(f"{k}：被判 2 次以上的段 {len(groups)}；前後不一致 {len(inc)} 段（{len(inc) / max(1, len(groups)):.1%}）；"
              f"兩兩比對 {pairs} 對、不一致 {dis} 對（{dis / max(1, pairs):.1%}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
