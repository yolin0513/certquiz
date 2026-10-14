#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融常識要不要做教材：兩科各抽 20 題，判「甲 要背的事實／乙 有道理可講」（Dispatch 2026-10-14；不動工，只給判斷用的數字）
-------------------------------------------------------------------------------
  python -u scripts/ethics_kind_sheet.py sheet            → data/local/教材/ethics-kind.md（單子）＋ ethics-kind-a.tsv、ethics-kind-b.tsv（空白，兩個判斷者各填一份）
  python -u scripts/ethics_kind_sheet.py result           → 兩科各自的甲乙比例（兩個判斷者各自的、以及兩人一致的）

母體：116 年版考試範圍，金融市場常識（gen）558 題、職業道德（eth）616 題。固定種子 20261014，各抽 20 題，可重現。
"""
import json
import random
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
PACK = ROOT / "data" / "local" / "import" / "ethics-匯入包.json"
SEED = 20261014
SPEC = """# 金融常識：每題屬於哪一類

給每一題判一類（只判類別，不要寫說明）：
- **甲　要背的事實**：答對靠的是記住一個數字、期限、比例、金額、機構名稱、分類歸屬（「下列何者屬於…」）或專有名詞的定義。就算懂道理，不記得那個事實也答不出來。
- **乙　有道理可講**：答對靠的是原則、判斷或情境應對；可以用一般道理說明為什麼正解對、其他選項錯，不必先記住某個具體事實。

拿不準時：如果要寫說明，就得引進題目沒給的具體事實才講得通 → 甲。
"""


def population():
    qs = json.loads(PACK.read_text(encoding="utf-8"))["questions"]
    return {s: sorted((q for q in qs if q.get("version") == "116" and q["subject"] == s), key=lambda q: q["id"]) for s in ("gen", "eth")}


def sheet():
    P = population()
    print(f"母體：常識 {len(P['gen'])}、道德 {len(P['eth'])}")
    md, rows = [SPEC, "## 題目", ""], ["題號\t類別（甲／乙）"]
    for n, s in enumerate(("gen", "eth")):
        for q in random.Random(SEED + n).sample(P[s], 20):
            md += [f"### {q['id']}", q["stem"]] + [f"- ({k}) {o}{'　**（官方正解）**' if str(k) == str(q['answer']) else ''}" for k, o in enumerate(q["options"], 1)] + [""]
            rows.append(f"{q['id']}\t")
    (D / "ethics-kind.md").write_text("\n".join(md), encoding="utf-8")
    for w in ("a", "b"):
        (D / f"ethics-kind-{w}.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"SHEET OK：40 題 → {D / 'ethics-kind.md'}")


def result():
    J = {}
    for w in ("a", "b"):
        J[w] = {l.split("\t")[0]: l.split("\t")[1].strip() for l in (D / f"ethics-kind-{w}.tsv").read_text(encoding="utf-8").splitlines()[1:] if l.strip()}
    for s, name in (("gen", "金融市場常識"), ("eth", "職業道德")):
        ids = [i for i in J["a"] if f"-{s}-" in i]
        out = []
        for w in ("a", "b"):
            k = [J[w][i] for i in ids]
            out.append(f"判斷者{w} 甲 {k.count('甲')}／乙 {k.count('乙')}")
        agree = [i for i in ids if J["a"][i] == J["b"][i]]
        both_jia = sum(J["a"][i] == "甲" for i in agree)
        print(f"{name}（{len(ids)} 題）：{'；'.join(out)}；兩人一致 {len(agree)}/{len(ids)}（一致的裡面甲 {both_jia}、乙 {len(agree) - both_jia}）")


if __name__ == "__main__":
    {"sheet": sheet, "result": result}.get((sys.argv[1:] or [""])[0], lambda: print(__doc__))()
