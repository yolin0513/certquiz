#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」本機匯入包（docs/L）
-------------------------------------------------------------------------------
輸入：data/local/sfi/ethics-{113,116}-{gen,eth}.json（import_sfi.py）＋ ethics-diff.json（ethics_diff.py）
輸出：data/local/import/ethics-匯入包.json（只放本機；使用者在 App「設定 → 匯入題目」匯入）

考試範圍（使用者 2027 年才考，Dispatch 2026-10-12）：**116 年版是考試範圍**，113 年版降為次要。
  116 年版全部 1,174 題：在範圍內；新增的標 change: added，改過的標 change: modified。
  113 年版裡跟 116 年版完全相同的題：標 dupOf 指到 116 年版那題（去重，口徑同內控：題幹與四個選項正規化後完全相同），不另外出現。
  113 年版裡改過的舊版、被刪掉的題：標 scope: outside（不在 116 年考試範圍內）、change: modified／deleted；改過的另標 newId 指到 116 年版的新題。
    App 預設不出這些題；要練得另外選，畫面標「不在 116 年考試範圍內」。
母體核對（印出來）：各類相加必須等於兩版題數，而且跟 ethics-diff.json 的分類一致；不等就報錯、不寫檔。
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
OUT = I.ROOT / "data" / "local" / "import" / "ethics-匯入包.json"


def main():
    banks = {k: json.loads((D / f"ethics-{k}.json").read_text(encoding="utf-8")) for k in ("113-gen", "113-eth", "116-gen", "116-eth")}
    diff = json.loads((D / "ethics-diff.json").read_text(encoding="utf-8"))
    qs, fails = [], 0
    print("母體核對（各類相加＝題數；跟兩版差異一致）")
    for part in ("gen", "eth"):
        d = diff[part]
        new = {q["no"]: q for q in banks[f"116-{part}"]["questions"]}
        old = {q["no"]: q for q in banks[f"113-{part}"]["questions"]}
        added = set(d["added"])
        mod_new = {m["no116"]: m for m in d["modified"]}
        same_old = {a: b for a, b in d["same"]}               # 113 題號 → 116 題號
        mod_old = {m["no113"]: m for m in d["modified"]}
        deleted = set(d["deleted"])
        if d["review"]:
            print(f"  ✗ {I.PART_NAME[part]}：還有 {len(d['review'])} 題待人工判定，不能建匯入包")
            fails += 1
            continue
        nid = lambda q: q["id"]
        base = lambda q, version: {"id": q["id"], "cert": "ethics", "subject": part, "type": "single", "stem": q["stem"],
                                   "options": q["options"], "answer": q["answer"], "source": "sfi-official", "version": version, "qno": q["no"]}
        n_in = 0
        for no, q in new.items():
            r = base(q, "116")
            if no in added:
                r["change"] = "added"
            elif no in mod_new:
                r["change"] = "modified"
                m = mod_new[no]
                if m["answer113"] != m["answer116"]:
                    # 正解換了（Dispatch 2026-10-12：整批差異裡唯一會讓他「確信地答錯」的，要單獨標出新舊正解）
                    oq = old[m["no113"]]
                    r["prevAnswer"] = {"version": "113", "qno": oq["no"], "answer": oq["answer"], "text": oq["options"][oq["answer"] - 1]}
            qs.append(r)
            n_in += 1
        n_dup = n_out_mod = n_out_del = 0
        for no, q in old.items():
            r = base(q, "113")
            if no in same_old:
                r["dupOf"] = nid(new[same_old[no]])
                n_dup += 1
            elif no in mod_old:
                r.update(scope="outside", change="modified", newId=nid(new[mod_old[no]["no116"]]))
                if mod_old[no]["answer113"] != mod_old[no]["answer116"]:
                    r["answerChanged"] = True
                n_out_mod += 1
            elif no in deleted:
                r.update(scope="outside", change="deleted")
                n_out_del += 1
            else:
                print(f"  ✗ {I.PART_NAME[part]}：113 年版第 {no} 題沒有歸到任何一類")
                fails += 1
                continue
            qs.append(r)
        ok = (n_in == len(new) and n_dup + n_out_mod + n_out_del == len(old) and n_dup == len(same_old)
              and n_out_mod == len(mod_old) and n_out_del == len(deleted))
        print(f"  {'✓' if ok else '✗'} {I.PART_NAME[part]}：116 年版 {n_in}／{len(new)} 題在範圍內（新增 {len(added)}、改過 {len(mod_new)}）；"
              f"113 年版 {len(old)} 題＝跟 116 相同（去重）{n_dup}＋改過的舊版 {n_out_mod}＋已刪除 {n_out_del}（後兩類不在 116 年考試範圍）")
        fails += 0 if ok else 1
    if fails:
        print("BUILD-ETHICS FAILED：母體核對不符，不寫檔")
        return 1
    in_scope = [q for q in qs if q.get("scope") != "outside" and not q.get("dupOf")]
    outside = [q for q in qs if q.get("scope") == "outside"]
    changed = [q for q in qs if q.get("prevAnswer")]
    names = "、".join(I.PART_NAME[q["subject"]] + "第 " + str(q["qno"]) + " 題" for q in changed)
    print(f"  正解換了的題：{len(changed)} 題（{names}）")
    pack = {"format": "certquiz-import", "version": 1, "cert": "ethics",
            "note": "證基會公告題庫（113 年版與 116 年版）。116 年版是考試範圍（2027-01-01 起適用）；113 年版裡已刪除或改過的題標 scope: outside。只放本機。",
            "sources": {k: {"file": v["file"], "sha256": v["sha256"], "official": v["official"]} for k, v in banks.items()},
            "counts": {"total": len(qs), "inScope": len(in_scope), "outside": len(outside), "dup": sum(1 for q in qs if q.get("dupOf")),
                       "answerChanged": len(changed)},
            "questions": qs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"BUILD-ETHICS OK：{len(qs)} 題（考試範圍內 {len(in_scope)}、範圍外 {len(outside)}、去重 {pack['counts']['dup']}）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
