#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材的唯一來源：data/local/教材/textbook.json（HTML 與 App 都從這一份產生，不各寫一份——兩份會各自漂移，沒有人會發現）
-------------------------------------------------------------------------------
  python -u scripts/textbook_build.py        → textbook.json；之後：
    python -u scripts/textbook_html.py       → 教材草稿.html（電腦上看；JS 失效時內容仍完整）
    python scripts/build_data.py --local     → 匯入包多一個 textbook 欄位（App 的「教材」）

內容：章（目前用主題分組實驗凍結的規則；正式版逐題歸類）→ 每章先放反覆考過的規定，再放其他題。
說明是「乙＋丙」（使用者 2026-10-13 定案）：
  乙＝兩個判斷者都說條文對得上、條號相同（basis-<章>.json）→ 放條文原文；
  丙＝其餘的題，我們寫的理解（ours-<章>.tsv），畫面標「我們寫的，未經查證」；拿不準就寫「看不出」，不硬寫。
丙的紀律（docs/STATUS「教材」）：只解釋為什麼官方正解是對的、不延伸；不寫法規名稱（會看起來像有依據）；拿不準寫看不出。
建置時機械檢查：丙的段落不得出現「」括起來的法規名稱、不得出現「依據」兩個字；本章每一題都要有乙或丙（不留白）。
題目文字不進 textbook.json（只放題號）；App 從匯入的題目取文字，HTML 從匯入包取。
"""
import json
import re
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
import textbook_summary_check as SC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
L = ROOT / "data" / "local"
D = L / "教材"
OUT = D / "textbook.json"
FILLED = ["T08"]          # 草稿只做完整的一章（信用卡）；其他章只列題數
LAWNAME = re.compile(r"「[^」]*(辦法|準則|規則|要點|注意事項|公約|條例|法)」|依據")


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
            # 法規重點摘要（使用者 2026-10-13：有法規依據的寫重點就好）：只用獨立代理核對「一致」、而且鎖定後沒被改過的
            chk = SC.checked(c)
            if chk is None:
                print(f"TEXTBOOK ABORT：{c} 的法規重點摘要還沒經過獨立核對（scripts/textbook_summary_check.py），或核對後被改過")
                return 2
            summ, off = chk
            if off or set(summ) != set(basis):
                print(f"TEXTBOOK ABORT：{c} 的法規重點摘要有偏離或缺漏：{off or sorted(set(basis) ^ set(summ))}")
                return 1
            of = D / f"ours-{c}.tsv"
            ours = {}
            if of.exists():
                for line in of.read_text(encoding="utf-8").splitlines()[1:]:
                    if line.strip():
                        qid, kind, text = (line.split("\t") + ["", ""])[:3]
                        if kind not in ("說明", "看不出") or not text.strip():
                            print(f"TEXTBOOK ABORT：{of.name} 的 {qid} 類別或內容不對")
                            return 2
                        if LAWNAME.search(text):
                            print(f"TEXTBOOK ABORT：{of.name} 的 {qid}（丙，未經查證）出現法規名稱或「依據」——會看起來像有依據：{LAWNAME.search(text).group(0)}")
                            return 2
                        ours[qid] = {"text": text.strip(), "unknown": kind == "看不出"}
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
                                     "snapshot": x["snapshot"], "url": x["url"], "link": x["link"], "summary": summ[i]}
                elif i in ours and ours[i]["unknown"]:
                    # 說不出比「規定就是這樣」更多的東西：整塊不要出現（使用者：看不懂、沒意義就刪掉）；章首另有一句說明
                    it["plain"] = True
                elif i in ours:
                    it["ours"] = ours[i]
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
            ch["ours"] = sum(1 for x in allq if "ours" in x)
            ch["plain"] = sum(1 for x in allq if x.get("plain"))
            left = [x["id"] for x in allq if "blank" in x]
            if ours and left:
                print(f"TEXTBOOK ABORT：{c} 還有 {len(left)} 題沒有乙也沒有丙（目標是不留白）：{left[:5]}")
                return 1
            extra = sorted(set(ours) - {x["id"] for x in allq if "ours" in x or x.get("plain")})
            if extra:
                print(f"TEXTBOOK ABORT：{of.name} 有 {len(extra)} 題寫了丙，但它們已經有乙（或不在本章）：{extra[:5]}")
                return 1
            # 母體核對：這一章每一題都出現一次（代表題或其他問法）
            seen = [x["id"] for x in allq]
            if sorted(set(seen) & set(ids)) != ids:
                print(f"TEXTBOOK ABORT：{c} 的題目沒有全部出現（少 {sorted(set(ids) - set(seen))[:5]}）")
                return 1
        chapters.append(ch)
    tb = {"version": 1, "generated": datetime.now().strftime("%Y-%m-%d"), "status": "draft", "tier": "乙＋丙",
          "chapterRule": "主題分組實驗凍結的關鍵字規則（草稿；正式版逐題歸類）", "chapters": chapters}
    D.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tb, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in chapters:
        if "items" in ch:
            print(f"  {ch['name']}：{ch['count']} 題（{len(ch['items'])} 張卡）；法規重點 {ch['explained']}、我們寫的 {ch['ours']}、純背（不寫說明）{ch['plain']}；未處理 {ch['count'] - ch['explained'] - ch['ours'] - ch['plain']}")
    print(f"TEXTBOOK OK：{len(chapters)} 章（完整 {len(FILLED)} 章）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
