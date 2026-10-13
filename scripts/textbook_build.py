#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材的唯一來源：data/local/教材/textbook.json（HTML 與 App 都從這一份產生，不各寫一份——兩份會各自漂移，沒有人會發現）
-------------------------------------------------------------------------------
  python -u scripts/textbook_build.py        → textbook.json；之後：
    python -u scripts/textbook_html.py       → 教材草稿.html（電腦上看；JS 失效時內容仍完整）
    python scripts/build_data.py --local     → 匯入包多一個 textbook 欄位（App 的「教材」）

內容：章（目前用主題分組實驗凍結的規則；正式版逐題歸類）→ 每章先放反覆考過的規定，再放其他題。
說明只照「乙」：兩個判斷者都說條文對得上、條號相同（basis-<章>.json）才有；其他題留白，並寫出留白的原因類別。
題目文字不進 textbook.json（只放題號）；App 從匯入的題目取文字，HTML 從匯入包取。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
import law_coverage as LC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
L = ROOT / "data" / "local"
D = L / "教材"
OUT = D / "textbook.json"
FILLED = ["T08"]          # 草稿只做完整的一章（信用卡）；其他章只列題數


def main():
    pack = json.loads((L / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))
    t = json.loads((L / "study" / "topics.json").read_text(encoding="utf-8"))
    names, tp = t["names"], t["topics"]
    act = {q["id"]: q for q in pack["questions"] if not q.get("dupOf") and q.get("status") != "retired"}
    el = LC.eligible()
    chapters = []
    order = sorted({tp[i] for i in act}, key=lambda c: (c == "T99", -sum(1 for i in act if tp[i] == c)))
    for c in order:
        ids = sorted(i for i in act if tp[i] == c)
        ch = {"id": c, "name": names.get(c, "其他"), "count": len(ids)}
        if c in FILLED:
            bf = D / f"basis-{c}.json"
            if not bf.exists():
                print(f"TEXTBOOK ABORT：{c} 要做完整，但還沒有依據判定結果（scripts/textbook_basis.py merge {c}）")
                return 2
            b = json.loads(bf.read_text(encoding="utf-8"))
            basis = b["basis"]
            items, used = [], set()
            pts = sorted([p for p in pack["points"] if any(i in ids for i in p["ids"])], key=lambda p: (-len(p["periods"]), p["id"]))
            for p in pts:
                mine = [i for i in p["ids"] if i in act]
                rep = sorted(mine, key=lambda i: -int(act[i]["period"]))[0]
                items.append({"id": rep, "point": {"times": len(p["periods"]), "kind": p.get("kind", "rule")},
                              "variants": [i for i in p["ids"] if i != rep]})
                used.update(p["ids"])
            items += [{"id": i} for i in ids if i not in used]
            def annotate(it):
                i = it["id"]
                if i in basis:
                    x = basis[i]
                    it["explain"] = {"law": x["law"], "article": x["article"], "version": x["version"], "text": x["text"],
                                     "snapshot": x["snapshot"], "url": x["url"], "link": x["link"]}
                elif not (act[i].get("law") or {}).get("laws"):
                    it["blank"] = "題目沒有點名法規"
                elif i not in el:
                    it["blank"] = "點名的法規查不到考試當時的版本"
                elif any(d[1] == i for d in b["disagree"]):
                    it["blank"] = "兩個判斷者對條文的看法不一致"
                else:
                    it["blank"] = "條文沒有寫到正解的關鍵內容"
                return it
            for it in items:
                annotate(it)
                # 其他問法也各自有說明或留白（說明跟著題目走，不跟著卡片走）
                it["variants"] = [annotate({"id": v}) for v in it.get("variants", []) if v in act] + [{"id": v, "dup": True} for v in it.get("variants", []) if v not in act]
                if not it["variants"]:
                    del it["variants"]
            ch["items"] = items
            allq = items + [v for it in items for v in it.get("variants", []) if not v.get("dup")]
            ch["explained"] = sum(1 for x in allq if "explain" in x)
            # 母體核對：這一章每一題都出現一次（代表題或其他問法）
            seen = [x["id"] for x in allq]
            if sorted(set(seen) & set(ids)) != ids:
                print(f"TEXTBOOK ABORT：{c} 的題目沒有全部出現（少 {sorted(set(ids) - set(seen))[:5]}）")
                return 1
        chapters.append(ch)
    tb = {"version": 1, "generated": datetime.now().strftime("%Y-%m-%d"), "status": "draft", "tier": "乙",
          "chapterRule": "主題分組實驗凍結的關鍵字規則（草稿；正式版逐題歸類）", "chapters": chapters}
    D.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tb, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in chapters:
        if "items" in ch:
            print(f"  {ch['name']}：{ch['count']} 題（{len(ch['items'])} 張卡）；有說明 {ch['explained']}、留白 {ch['count'] - ch['explained']}")
    print(f"TEXTBOOK OK：{len(chapters)} 章（完整 {len(FILLED)} 章）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
