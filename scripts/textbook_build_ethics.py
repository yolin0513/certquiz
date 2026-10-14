#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
職業道德教材的唯一來源：data/local/教材/textbook-ethics.json（docs/M 第十一節；HTML 與 App 都從這一份產生）
-------------------------------------------------------------------------------
  python -u scripts/textbook_build_ethics.py   → textbook-ethics.json；之後：
    python -u scripts/textbook_html.py ethics   → 職業道德教材草稿.html
    python scripts/build_data.py --local        → 職業道德匯入包多一個 textbook 欄位（App 的「教材」）

跟內控（textbook_build.py）的差別：沒有「法規重點」那一層（題目點名法規的只有 3.4%），每題只有「我們寫的」或「沒有說明」。
章＝證基會公告的職業道德 7 項範圍（chapters-ethics.json，逐題歸章、已鎖定）。
「我們寫的」檔（ours-E*.tsv）要通過複核、之後沒被改過才收（textbook_ours_check.py）；C3 機械檢查同內控。
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
import textbook_chapters_ethics as CE  # noqa: E402
import textbook_ours_check as OC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
OUT = D / "textbook-ethics.json"
FILLED = ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]   # 每通過一組就加進來（docs/M 第十一節）
LAWNAME = re.compile(r"「[^」]*(辦法|準則|規則|要點|注意事項|公約|條例|法)」|依據|依[^，。；]{0,12}規定|主管機關規定")
NOLAW = ("這一科沒有「法規重點」：職業道德的題目只有 3.4% 點名法規，而且多半是原則題，指不出可以對照的條文。"
         "所以每題只有兩種結果——「我們寫的（未查證）」或「沒有說明」。這不是少做了一層，是這一科沒有那一層可做。")


def main():
    tp = json.loads((D / "chapters-ethics.json").read_text(encoding="utf-8"))
    ids_all = {q["id"] for q in CE.questions()}
    if set(tp) != ids_all:
        print("TEXTBOOK-ETHICS ABORT：歸章檔跟母體題號不一致")
        return 2
    chapters = []
    for c, name, _ in CE.CHAPTERS:
        ids = sorted(i for i, v in tp.items() if v == c)
        ch = {"id": c, "name": name, "count": len(ids)}
        if c in FILLED:
            of = D / f"ours-{c}.tsv"
            if not OC.passed(c):
                print(f"TEXTBOOK-ETHICS ABORT：{of.name} 還沒通過「我們寫的」複核，或通過後被改過")
                return 2
            ours = {}
            for line in of.read_text(encoding="utf-8").splitlines()[1:]:
                if line.strip():
                    qid, kind, text = [x.strip() for x in (line.split("\t") + ["", ""])[:3]]
                    if kind not in ("說明", "看不出") or not text:
                        print(f"TEXTBOOK-ETHICS ABORT：{of.name} 的 {qid} 類別或內容不對")
                        return 1
                    if kind == "說明" and LAWNAME.search(text):
                        print(f"TEXTBOOK-ETHICS ABORT：{of.name} 的 {qid} 出現法規名稱或依據字樣：{LAWNAME.search(text).group(0)}")
                        return 1
                    ours[qid] = {"text": text, "unknown": kind == "看不出"}
            if sorted(ours) != ids:
                print(f"TEXTBOOK-ETHICS ABORT：{c} 的「我們寫的」題號跟本章不一致（少 {sorted(set(ids) - set(ours))[:5]}、多 {sorted(set(ours) - set(ids))[:5]}）")
                return 1
            items = [({"id": i, "plain": True} if ours[i]["unknown"] else {"id": i, "ours": ours[i]}) for i in ids]
            ch["items"] = items
            ch["explained"] = 0
            ch["ours"] = sum(1 for x in items if "ours" in x)
            ch["plain"] = sum(1 for x in items if x.get("plain"))
        chapters.append(ch)
    tb = {"version": 1, "generated": datetime.now().strftime("%Y-%m-%d"), "status": "draft", "tier": "丙", "layers": 2, "noLaw": NOLAW,
          "scope": "116 年版考試範圍的職業道德 616 題（金融市場常識不做，docs/M 第十二節）",
          "chapterRule": "逐題歸章（scripts/textbook_chapters_ethics.py，7 個代理）；章名＝證基會公告的職業道德 7 項範圍", "chapters": chapters}
    OUT.write_text(json.dumps(tb, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in chapters:
        if "items" in ch:
            print(f"  {ch['name']}：{ch['count']} 題；我們寫的 {ch['ours']}、沒有說明 {ch['plain']}")
    print(f"TEXTBOOK-ETHICS OK：{len(chapters)} 章（完整 {len(FILLED)} 章）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
