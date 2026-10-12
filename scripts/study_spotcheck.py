#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
U7：「反覆考過的規定」使用者抽查單（docs/K：從我核對過的與沒核對過的各抽一半，Dispatch 2026-10-08 定的方式）
-------------------------------------------------------------------------------
  python -u scripts/study_spotcheck.py      產生 data/local/抽檢/使用者_考點抽查.md（給使用者）＋ 考點抽查-key.json（對照，使用者不用看）

母體：本機匯入包的 138 個考點群組。
  核對過＝第二級（跨期相似，含 1+2）：我逐組並排核對過、混入假組驗過的 42 組。
  沒核對過＝只有第一級（逐字重複）：設計上不做人工核對的 96 組。
兩半各抽 PER_HALF 組（種子固定，重跑抽到同一批），混在一起打亂。單子上不寫哪一組屬於哪一半、也不寫我歸納的規定名稱——
使用者只看題目與官方正解自己判斷，才是獨立的檢查（我寫的規定名稱會先入為主）。
兩半的錯誤率差很多本身就是訊號（docs/K）。題目原文只在本機，這兩個檔都不進 repo。
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
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
OUTDIR = ROOT / "data" / "local" / "抽檢"
SHEET = OUTDIR / "使用者_考點抽查.md"
KEY = OUTDIR / "考點抽查-key.json"
LOG = ROOT / "data" / "local" / "study" / "log.tsv"
SEED = 20261012
PER_HALF = 10
SUBJ = {"law": "法規", "gen": "實務"}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if KEY.exists():
        print(f"SPOTCHECK ABORT：抽查單已經產生過（{KEY.name}）；重抽會換一批，先問過再刪")
        return 2
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    by = {q["id"]: q for q in pack["questions"]}
    pts = pack["points"]
    reviewed = sorted([p for p in pts if "2" in p["level"]], key=lambda p: p["id"])
    unreviewed = sorted([p for p in pts if p["level"] == "1"], key=lambda p: p["id"])
    if len(reviewed) + len(unreviewed) != len(pts):
        print(f"SPOTCHECK ABORT：母體核對不符：核對過 {len(reviewed)}＋沒核對過 {len(unreviewed)}≠{len(pts)}")
        return 1
    rnd = random.Random(SEED)
    pick = [(p, "核對過") for p in rnd.sample(reviewed, PER_HALF)] + [(p, "沒核對過") for p in rnd.sample(unreviewed, PER_HALF)]
    rnd.shuffle(pick)
    n = len(pick)
    md = [f"# 「反覆考過的規定」抽查單（{n} 組）", "",
          "App 讀書模式裡的「反覆考過的規定」，是把不同期、問同一條規定的題目歸成一組。這份單子請你判斷：**每一組裡的題目，問的是不是同一條規定？**",
          "",
          "- 判斷標準：**讀懂其中一題依據的那條規定，另一題也會答**——就算問法不同（正問、反問、換一個數字或條件）也算同一條。",
          "- 只看下面寫的題目與官方正解就好，不用翻檔案、不用查資料。不確定就勾「看不出來」，那也是有用的答案。",
          "- 這裡故意**不寫**我歸納的規定名稱，也不說哪一組我核對過：你自己判斷，才是獨立的檢查。",
          f"- 一組大約 1 分鐘，全部約 {n}～{2 * n} 分鐘。可以分幾次做。",
          "",
          "**回覆方式**：照編號回一行就好，例如「1 是、2 是、3 不是、4 看不出來…」；「不是」或「看不出來」的，可以加一句為什麼（選填）。",
          ""]
    key = []
    for i, (p, half) in enumerate(pick, 1):
        md += [f"## {i}（{len(p['ids'])} 題，第 {'、'.join(str(x) for x in sorted(p['periods']))} 期）", ""]
        for j, q in enumerate([by[x] for x in sorted(p["ids"], key=lambda x: -int(by[x]["period"]))], 1):
            md += [f"**{chr(64 + j)}. 第 {q['period']} 期 {SUBJ.get(q['subject'], q['subject'])} 第 {q['qno']} 題**", "",
                   q["stem"], ""]
            md += [f"- ({k}) {o}{'　**← 官方正解**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
            md += [""]
        md += ["你的判斷：☐ 是同一條規定　☐ 不是　☐ 看不出來　（為什麼：＿＿＿＿）", "", "---", ""]
        key.append({"no": i, "point": p["id"], "half": half, "level": p["level"], "kind": p.get("kind", "rule"), "ids": p["ids"]})
    OUTDIR.mkdir(parents=True, exist_ok=True)
    SHEET.write_text("\n".join(md), encoding="utf-8")
    KEY.write_text(json.dumps({"seed": SEED, "per_half": PER_HALF, "population": {"核對過": len(reviewed), "沒核對過": len(unreviewed)},
                               "sample": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        for p in (Path(__file__), SHEET, KEY):
            f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\tspotcheck-draw\t{p.name}\t{sha(p)}\n")
    print(f"SPOTCHECK OK：{n} 組（核對過 {PER_HALF}／{len(reviewed)}、沒核對過 {PER_HALF}／{len(unreviewed)}；種子 {SEED}）→ {SHEET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
