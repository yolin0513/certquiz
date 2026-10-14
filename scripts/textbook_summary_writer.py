#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「法規重點」摘要寫手單（寫手是獨立代理；摘要寫完再由另一個代理用 textbook_summary_check.py 全量核對）
-------------------------------------------------------------------------------
  python -u scripts/textbook_summary_writer.py T01   → summary-T01-writer.md（題目、官方正解、條文全文）＋ summary-T01.tsv（空白，寫手填）

只列 basis-T01.json 裡「有依據」的題；沒有依據的題不寫法規重點。寫作規格與信用卡、第二章用的那一份相同（使用者 2026-10-13 定的格式）。
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
SPEC = """# 法規重點摘要寫手單

每題寫一句「法規重點」。**寫作規格**（一定要照）：標出條號（含款）→ 用一句話講出那一款的重點 → 直接指出選項（問錯的題指出錯的選項錯在哪；問對的題指出就是哪個選項）。不鋪陳、不引全文。
**以條號開頭（「第N條…」），不要在前面加法規名稱**（法規名稱畫面上另外顯示）。**不能漏掉會改變意思的條件**（例如但書「…不在此限」）。只寫條文裡有的。
範例：第32條第3款：先由有權人員核准轉銷，再彙報董（理）事會備查；選項 (4) 把順序寫反了，所以是錯的那一個。

## 填法
用 Write 把對應的 summary-<章>.tsv 整檔重寫（UTF-8、Tab 分隔）：保留第一行表頭，每行「題號<TAB>法規重點」，每題都要填。
"""


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    topic = argv[0]
    md_p, tsv_p = D / f"summary-{topic}-writer.md", D / f"summary-{topic}.tsv"
    if tsv_p.exists():
        print(f"SUMMARY-WRITER ABORT：{tsv_p.name} 已經存在")
        return 2
    basis = json.loads((D / f"basis-{topic}.json").read_text(encoding="utf-8"))["basis"]
    if not basis:
        print(f"SUMMARY-WRITER OK：{topic} 沒有有依據的題，不用寫")
        return 0
    Q = {q["id"]: q for q in json.loads((ROOT / "data" / "local" / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))["questions"]}
    md, rows = [SPEC], ["題號\t法規重點"]
    for qid in sorted(basis):
        q, b = Q[qid], basis[qid]
        md += [f"## {qid}", q["stem"]] + [f"- ({k}) {o}{'　**（官方正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
        md += ["", f"**依據**：{b['law']}{b['article']}（{b['version']} 版），條文全文：", "", "```", b["text"], "```", ""]
        rows.append(f"{qid}\t")
    md_p.write_text("\n".join(md), encoding="utf-8")
    tsv_p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"SUMMARY-WRITER OK：{len(basis)} 題 → {md_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
