#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內控主題分組的開發組／驗收組切分（docs/K_讀書模式方案.md 第 2 步）
-------------------------------------------------------------------------------
輸入：本機匯入包、data/local/study/points.json（先跑 study_points.py）。
輸出：data/local/study/split.json（只在本機，只有題號），並在 data/local/study/log.tsv 加一行（時間、檔名、sha256）。

規則（事先定）：
  - 以「考點」為單位切：同一個考點（逐字重複＋跨期相似）的題整組放同一邊，避免開發組讀過的題的雙胞胎落在驗收組。
  - 法規、實務分開，各自約一半；固定種子，可重現。
  - 只切可練的題（沒有 dupOf 的）；逐字重複的隱藏題跟著它的代表題走。
  - split.json 已存在就拒絕覆寫（切分只做一次；要重切只能作廢並在文件記下原因，見 docs/K 的自我約束）。
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
STUDY = ROOT / "data" / "local" / "study"
SEED = 20261008


def log(name, path):
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{name}\t{path.name}\t{h}\n"
    with (STUDY / "log.tsv").open("a", encoding="utf-8") as f:
        f.write(line)
    return h


def main():
    out = STUDY / "split.json"
    if out.exists():
        print(f"STUDY-SPLIT ABORT：{out.name} 已存在，不覆寫（切分只做一次）")
        return 2
    allq = json.loads(PACK.read_text(encoding="utf-8"))["questions"]
    active = {q["id"]: q for q in allq if not q.get("dupOf")}
    points = json.loads((STUDY / "points.json").read_text(encoding="utf-8"))["points"]
    # 單位：每個考點裡的可練題為一個單位；不屬於任何考點的可練題各自一個單位
    units, seen = [], set()
    for p in points:
        ids = [i for i in p["ids"] if i in active]
        if ids:
            units.append(ids)
            seen.update(ids)
    units += [[i] for i in active if i not in seen]
    # 跨科的考點（同樣內容在不同期分別出現在法規與實務）仍是一個單位、整組放同一邊；
    # 平衡兩科時算進多數題所屬的科目（同數時算法規）。2026-10-08 第一次執行時發現 6 個，切分前補的規則。
    def subj(u):
        law = sum(active[i]["subject"] == "law" for i in u)
        return "law" if law * 2 >= len(u) else "gen"
    mixed = [u for u in units if len({active[i]["subject"] for i in u}) > 1]
    print(f"• 跨科的考點：{len(mixed)} 個（整組放同一邊）")
    rnd = random.Random(SEED)
    split = {"seed": SEED, "dev": [], "holdout": []}
    for s in ("law", "gen"):
        us = [u for u in units if subj(u) == s]
        rnd.shuffle(us)
        total = sum(len(u) for u in us)
        n = 0
        for u in us:
            side = "dev" if n < total / 2 else "holdout"
            split[side] += u
            if side == "dev":
                n += len(u)
    # 自查
    both = set(split["dev"]) & set(split["holdout"])
    covered = set(split["dev"]) | set(split["holdout"])
    where = {i: "dev" for i in split["dev"]} | {i: "holdout" for i in split["holdout"]}
    torn = [p for p in points if len({where[i] for i in p["ids"] if i in where}) > 1]
    print(f"• 可練題 {len(active)} 題 → 開發組 {len(split['dev'])}、驗收組 {len(split['holdout'])}；兩邊重疊 {len(both)}、漏掉 {len(set(active) - covered)}")
    for s in ("law", "gen"):
        d = sum(active[i]["subject"] == s for i in split["dev"]); h = sum(active[i]["subject"] == s for i in split["holdout"])
        print(f"  {s}：開發 {d}、驗收 {h}")
    print(f"• 被切開的考點：{len(torn)}（應為 0）")
    if both or covered != set(active) or torn:
        print("STUDY-SPLIT ABORT：自查不過，不寫檔")
        return 2
    STUDY.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    h = log("split", out)
    print(f"STUDY-SPLIT OK：{out.relative_to(ROOT)}（sha256 {h[:16]}…，已記入 log.tsv）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
