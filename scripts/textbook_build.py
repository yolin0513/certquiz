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
FILLED = ["T08", "T07", "T01", "T02", "T03", "T04", "T05", "T06", "T09", "T10", "T11", "T12", "T13", "T16", "T99", "T14", "T15"]   # 全量進行中（docs/M 第七節）：每通過一組就加進來
# C3（全量、機械）：「我們寫的」不得出現法規名稱、「依據」、「依…規定」、「主管機關規定」
LAWNAME = re.compile(r"「[^」]*(辦法|準則|規則|要點|注意事項|公約|條例|法)」|依據|依[^，。；]{0,12}規定|主管機關規定")


def load_ours():
    """所有 ours-*.tsv（說明跟著題目走，不跟著章走）。每個檔都要通過複核、之後沒被改過（docs/M）。"""
    import textbook_ours_check as OC
    out = {}
    for of in sorted(D.glob("ours-T*.tsv")):
        if not re.fullmatch(r"ours-T\d+\.tsv", of.name):
            continue
        if not OC.passed(of.stem.split("-")[1]):
            return None, f"{of.name} 還沒通過「我們寫的」複核（scripts/textbook_ours_check.py），或通過後被改過"
        for line in of.read_text(encoding="utf-8").splitlines()[1:]:
            if line.strip():
                qid, kind, text = [x.strip() for x in (line.split("\t") + ["", ""])[:3]]
                if kind not in ("說明", "看不出") or not text:
                    return None, f"{of.name} 的 {qid} 類別或內容不對"
                if kind == "說明" and LAWNAME.search(text):
                    return None, f"{of.name} 的 {qid}（我們寫的）出現法規名稱或依據字樣——會看起來像有依據：{LAWNAME.search(text).group(0)}"
                out[qid] = {"text": text, "unknown": kind == "看不出"}
    return out, ""


def main():
    pack = json.loads((L / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))
    names = {c: n for c, n, *_ in __import__("study_topics").TOPICS} | {"T99": "其他"}
    chf = D / "chapters-bic.json"
    tp = json.loads(chf.read_text(encoding="utf-8"))
    act = {q["id"]: q for q in pack["questions"] if not q.get("dupOf") and q.get("status") != "retired"}
    if set(act) != set(tp):
        print(f"TEXTBOOK ABORT：逐題歸章跟題庫對不上（少 {len(set(act) - set(tp))}、多 {len(set(tp) - set(act))}）")
        return 1
    el = LC.eligible()
    basis, disagree = {}, set()
    for bf in sorted(D.glob("basis-T*.json")):
        if not re.fullmatch(r"basis-T\d+\.json", bf.name):   # 只要合併結果，不要 -key.json
            continue
        b = json.loads(bf.read_text(encoding="utf-8"))
        c = b["topic"]
        disagree |= {d[1] for d in b["disagree"]}
        if not b["basis"]:   # 這一章沒有任何題對得上依據：沒有摘要要核（例：T06 候選 0 題）
            continue
        chk = SC.checked(c)
        if chk is None:
            print(f"TEXTBOOK ABORT：{c} 的法規重點摘要還沒經過獨立核對，或核對後被改過")
            return 2
        summ, off = chk
        if off or set(summ) != set(b["basis"]):
            print(f"TEXTBOOK ABORT：{c} 的法規重點摘要有偏離或缺漏：{off or sorted(set(b['basis']) ^ set(summ))}")
            return 1
        for i, x in b["basis"].items():
            basis[i] = dict(x, summary=summ[i])
        disagree |= {d[1] for d in b["disagree"]}
    ours, why = load_ours()
    if ours is None:
        print(f"TEXTBOOK ABORT：{why}")
        return 2
    chapters = []
    order = sorted(set(tp.values()), key=lambda c: (c == "T99", -sum(1 for i in act if tp[i] == c)))
    for c in order:
        ids = sorted(i for i in act if tp[i] == c)
        ch = {"id": c, "name": names.get(c, "其他"), "count": len(ids)}
        if c in FILLED:
            idset = set(ids)
            items, used = [], set()
            pts = sorted([p for p in pack["points"] if any(i in idset for i in p["ids"])], key=lambda p: (-len(p["periods"]), p["id"]))
            for p in pts:
                mine = [i for i in p["ids"] if i in idset]
                rep = sorted(mine, key=lambda i: -int(act[i]["period"]))[0]
                # 同一組裡被歸到別章的題，留在它自己那一章；這裡只收本章的（重複題照舊附在代表題下）
                items.append({"id": rep, "point": {"times": len(p["periods"]), "kind": p.get("kind", "rule")},
                              "variants": [i for i in p["ids"] if i != rep and (i in idset or i not in act)]})
                used.update(mine)
            items += [{"id": i} for i in ids if i not in used]

            def annotate(it):
                i = it["id"]
                if i in basis:
                    x = basis[i]
                    it["explain"] = {k: x[k] for k in ("law", "article", "version", "text", "snapshot", "url", "link", "summary")}
                elif i in ours and ours[i]["unknown"]:
                    it["plain"] = True     # 純背：畫面上不出現說明，章首有一句說明
                elif i in ours:
                    it["ours"] = ours[i]
                elif not (act[i].get("law") or {}).get("laws"):
                    it["blank"] = "題目沒有點名法規"
                elif i not in el:
                    it["blank"] = "點名的法規查不到考試當時的版本"
                elif i in disagree:
                    it["blank"] = "兩個判斷者對條文的看法不一致"
                else:
                    it["blank"] = "條文沒有寫到正解的關鍵內容"
                return it
            for it in items:
                annotate(it)
                it["variants"] = [annotate({"id": v}) for v in it.get("variants", []) if v in act] + [{"id": v, "dup": True} for v in it.get("variants", []) if v not in act]
                if not it["variants"]:
                    del it["variants"]
            ch["items"] = items
            allq = items + [v for it in items for v in it.get("variants", []) if not v.get("dup")]
            ch["explained"] = sum(1 for x in allq if "explain" in x)
            ch["ours"] = sum(1 for x in allq if "ours" in x)
            ch["plain"] = sum(1 for x in allq if x.get("plain"))
            left = [x["id"] for x in allq if "blank" in x]
            if left:
                print(f"TEXTBOOK ABORT：{c} 還有 {len(left)} 題沒有法規重點也沒有「我們寫的」（目標是不留白）：{left[:5]}")
                return 1
            seen = [x["id"] for x in allq]
            if sorted(seen) != ids:
                print(f"TEXTBOOK ABORT：{c} 的題目沒有剛好各出現一次（少 {sorted(idset - set(seen))[:5]}、多 {sorted(set(seen) - idset)[:5]}）")
                return 1
        chapters.append(ch)
    tb = {"version": 1, "generated": datetime.now().strftime("%Y-%m-%d"), "status": "draft", "tier": "乙＋丙",
          "chapterRule": "逐題歸章（scripts/textbook_chapters.py，8 個代理）", "chapters": chapters}
    D.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tb, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in chapters:
        if "items" in ch:
            print(f"  {ch['name']}：{ch['count']} 題（{len(ch['items'])} 張卡）；法規重點 {ch['explained']}、我們寫的 {ch['ours']}、純背（不寫說明）{ch['plain']}")
    print(f"TEXTBOOK OK：{len(chapters)} 章（完整 {len(FILLED)} 章）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
