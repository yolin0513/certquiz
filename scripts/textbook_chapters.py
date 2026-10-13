#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材全量：內控逐題歸章（docs/M；取代草稿用的關鍵字規則）
-------------------------------------------------------------------------------
  python -u scripts/textbook_chapters.py sheet     801 題打亂（固定種子）分 8 批 → chapters-bNN.md（章節定義＋題目）＋空白判斷檔
  python -u scripts/textbook_chapters.py lock      8 批都填完 → 合併成 chapters-bic.json、鎖雜湊
  python -u scripts/textbook_chapters.py diff      跟草稿用的關鍵字規則比，各章進出幾題（信用卡章已給使用者看過，要知道它變了多少）

章＝導覽用途，不是驗證過的學習單位（互助性 11%，docs/K）；每題只歸一章，歸不進去的歸「其他」。
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_topics as ST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"
OUT = D / "chapters-bic.json"
SEED, N_BATCH = 20261014, 8
SUBJ = {"law": "法規", "gen": "實務"}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def chapters():
    return [(c, n, s) for c, n, s, _ in ST.TOPICS] + [(ST.OTHER[0], ST.OTHER[1], "上面每一章都放不進去的題")]


def questions():
    pack = json.loads((ROOT / "data" / "local" / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))
    return sorted([q for q in pack["questions"] if not q.get("dupOf") and q.get("status") != "retired"], key=lambda q: q["id"])


def sheet():
    D.mkdir(parents=True, exist_ok=True)
    if (D / "chapters-b01.md").exists():
        print("SHEET ABORT：已經分過批了")
        return 2
    qs = questions()
    random.Random(SEED).shuffle(qs)
    size = -(-len(qs) // N_BATCH)
    defs = ["# 內控教材：逐題歸章", "", "每一題只歸**一章**：看這題主要在考哪一個主題。真的放不進任何一章的，歸 T99（其他）。",
            "章是為了讓讀的人好找，不必追求完美；拿不準時選最接近的那一章。", "", "## 章節定義", ""]
    defs += [f"- **{c}　{n}**：{s}" for c, n, s in chapters()] + [""]
    for b in range(N_BATCH):
        part = qs[b * size:(b + 1) * size]
        md = list(defs) + ["## 題目", ""]
        rows = ["題號\t章（填代號，例如 T08）"]
        for q in part:
            md += [f"### {q['id']}（{SUBJ.get(q['subject'], q['subject'])}）", q["stem"]] + [f"- ({k}) {o}" for k, o in enumerate(q["options"], 1)] + [""]
            rows.append(f"{q['id']}\t")
        (D / f"chapters-b{b + 1:02d}.md").write_text("\n".join(md), encoding="utf-8")
        (D / f"chapters-b{b + 1:02d}.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    log("chapters-sheet", Path(__file__))
    print(f"SHEET OK：{len(qs)} 題分 {N_BATCH} 批（每批 ≤ {size} 題）→ {D}")
    return 0


def lock():
    codes = {c for c, _, _ in chapters()}
    merged, bad = {}, []
    for b in range(N_BATCH):
        p = D / f"chapters-b{b + 1:02d}.tsv"
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
    log("chapters-lock", OUT)
    cnt = {}
    for v in merged.values():
        cnt[v] = cnt.get(v, 0) + 1
    names = {c: n for c, n, _ in chapters()}
    print(f"LOCK OK：{len(merged)} 題 → {OUT}")
    for c, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
        print(f"  {c} {names[c]}：{n}")
    return 0


def diff():
    new = json.loads(OUT.read_text(encoding="utf-8"))
    old = json.loads((ROOT / "data" / "local" / "study" / "topics.json").read_text(encoding="utf-8"))["topics"]
    same = sum(1 for i in new if old.get(i) == new[i])
    print(f"跟草稿的關鍵字規則同章：{same}／{len(new)}（{same / len(new):.0%}）")
    for c in ("T08", "T07"):
        o = {i for i in new if old.get(i) == c}
        n = {i for i in new if new[i] == c}
        print(f"  {c}：關鍵字 {len(o)} 題 → 逐題 {len(n)} 題；留下 {len(o & n)}、移出 {len(o - n)}、移入 {len(n - o)}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"sheet": sheet, "lock": lock, "diff": diff}.get(cmd, lambda: (print(__doc__), 2)[1])())
