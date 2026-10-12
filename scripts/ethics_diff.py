#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」113 年版與 116 年版題庫的差異（docs/L）
-------------------------------------------------------------------------------
輸入：data/local/sfi/ethics-{113,116}-{gen,eth}.json（scripts/import_sfi.py 產生）。輸出：data/local/sfi/ethics-diff.json（只放本機）。

分類（門檻依兩版未配對題目的「最佳相似度」分布定，2026-10-12 先看分布再定、寫在這裡）：
  相同       題幹與四個選項正規化後完全相同
  改過       相似度 ≥ 0.5，而且雙方互為最佳配對 → 逐項比題幹、選項、正解哪裡變了
  待人工判定 相似度 0.3～0.5 → 不自動歸類，列出來
  新增／刪除 116 版裡找不到配對的是新增；113 版裡找不到配對的是刪除
  分布（116 版每題對 113 版的最佳相似度）：常識在 0.3～0.6 之間 0 題、道德在 0.3～0.4 之間 0 題，兩群之間有明顯空檔。
核對：各類題數相加必須等於各版題數，不等就報錯、不寫檔。
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_sfi as I  # noqa: E402

D = I.OUT
HI, LO = 0.5, 0.3
# 待人工判定區的人工判定（判定者：Claude，2026-10-12，兩邊原文並排看過；不是自動歸類）
MANUAL = {("eth", 38, 38): ("改過", "題幹完全相同、正解選項文字相同，三個誘答換了")}


def main():
    out, fails = {}, 0
    for part in ("gen", "eth"):
        a = json.loads((D / f"ethics-113-{part}.json").read_text(encoding="utf-8"))["questions"]
        b = json.loads((D / f"ethics-116-{part}.json").read_text(encoding="utf-8"))["questions"]
        key = lambda q: I.norm(q["stem"] + "|" + "|".join(q["options"]))
        ka = {key(q): q for q in a}
        kb = {key(q): q for q in b}
        same = [(ka[k]["no"], kb[k]["no"]) for k in kb if k in ka]
        ua = [q for q in a if key(q) not in kb]
        ub = [q for q in b if key(q) not in ka]
        G = {id(q): I.grams(q["stem"] + "".join(q["options"])) for q in ua + ub}
        best_a = {id(x): max(((I.jac(G[id(x)], G[id(y)]), id(y)) for y in ub), default=(0, None)) for x in ua}
        best_b = {id(y): max(((I.jac(G[id(y)], G[id(x)]), id(x)) for x in ua), default=(0, None)) for y in ub}
        byid = {id(q): q for q in ua + ub}
        modified, review, paired_a, paired_b = [], [], set(), set()
        for y in ub:
            s, xa = best_b[id(y)]
            if xa is None:
                continue
            mutual = best_a[xa][1] == id(y)
            x = byid[xa]
            if s >= HI and mutual:
                changes = []
                if I.norm(x["stem"]) != I.norm(y["stem"]):
                    changes.append("題幹")
                changes += [f"選項{k + 1}" for k in range(4) if I.norm(x["options"][k]) != I.norm(y["options"][k])]
                if x["answer"] != y["answer"]:
                    changes.append("正解")
                modified.append({"no113": x["no"], "no116": y["no"], "similarity": round(s, 3), "changes": changes,
                                 "answer113": x["answer"], "answer116": y["answer"]})
                paired_a.add(xa)
                paired_b.add(id(y))
            elif s >= LO:
                man = MANUAL.get((part, x["no"], y["no"]))
                if man and man[0] == "改過":
                    changes = (["題幹"] if I.norm(x["stem"]) != I.norm(y["stem"]) else []) +                         [f"選項{k + 1}" for k in range(4) if I.norm(x["options"][k]) != I.norm(y["options"][k])] + (["正解"] if x["answer"] != y["answer"] else [])
                    modified.append({"no113": x["no"], "no116": y["no"], "similarity": round(s, 3), "changes": changes,
                                     "answer113": x["answer"], "answer116": y["answer"], "manual": man[1]})
                else:
                    review.append({"no113": x["no"], "no116": y["no"], "similarity": round(s, 3)})
                paired_a.add(xa)
                paired_b.add(id(y))
        added = [y["no"] for y in ub if id(y) not in paired_b]
        deleted = [x["no"] for x in ua if id(x) not in paired_a]
        n113 = len(same) + len(modified) + len(review) + len(deleted)
        n116 = len(same) + len(modified) + len(review) + len(added)
        ok = n113 == len(a) and n116 == len(b)
        ans_changed = [m for m in modified if "正解" in m["changes"]]
        print(f"{'✓' if ok else '✗'} {I.PART_NAME[part]}：113 版 {len(a)} 題＝相同 {len(same)}＋改過 {len(modified)}＋待人工 {len(review)}＋刪除 {len(deleted)}"
              f"（相加 {n113}）；116 版 {len(b)} 題＝相同 {len(same)}＋改過 {len(modified)}＋待人工 {len(review)}＋新增 {len(added)}（相加 {n116}）"
              f"；改過的題裡正解也換了 {len(ans_changed)} 題")
        fails += 0 if ok else 1
        out[part] = {"same": same, "modified": modified, "review": review, "added": added, "deleted": deleted}
    if fails:
        print("ETHICS-DIFF FAILED：分類相加不等於題數，不寫檔")
        return 1
    (D / "ethics-diff.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ETHICS-DIFF OK：寫出 {D / 'ethics-diff.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
