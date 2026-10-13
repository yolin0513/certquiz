#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「我們寫的」寫手單（docs/M；寫手是獨立代理，一批最多 50 題）
-------------------------------------------------------------------------------
  python -u scripts/textbook_writer_sheet.py <輸出名> <批次代號> <題號…>   → <輸出名>.md（寫作規格＋題目）＋ <輸出名>.tsv（空白，寫手填）

寫作規格與 docs/STATUS「教材」那一段的丙紀律一致；「看不出」的題畫面上不出現說明（章首有一句說明）。
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
SPEC = """# 教材「我們寫的（未查證）」寫手單

給讀者（一個從零開始準備這張證照的人）每題寫一段**短**說明，解釋**為什麼官方正解是對的**。這一層沒有外部依據，畫面會標「我們寫的（未查證）」。

## 紀律（一定要照做）
1. **只解釋為什麼官方正解是對的，不延伸補充。** 不要引進題目和選項裡都沒有的數字、期限、金額、條件或規定——延伸的部分最容易錯，也不是讀者需要的。
   **具體地說：理由只能用題目和選項裡已經寫出來的東西**（例如拿選項彼此比較、看題目用的字、常識上的因果）。**如果要講出理由，非得引進題目和選項裡沒有的規則、條件、期限或處理方式，就填「看不出」，不要寫。** 核對時這一條從嚴：多出一個題目裡沒有的條件就不合格。
2. **不寫法規名稱、不寫「依據」「依…規定」「主管機關規定」**——那會讓它看起來像有依據。
3. **拿不準就寫拿不準。** 如果你說不出比「規定就是這樣」更多的理由（例如純粹要記的數字、天數、倍數、比例），類別填「看不出」，內容寫三到八個字說明是什麼要背的（例如「要記的天數」）。**不要為了填滿硬編理由。**
4. **短**：一到兩句、通常 60 字以內。問「何者錯誤」的題，直接指出錯的那個選項錯在哪。
5. 不要說官方答案錯，也不要暗示別的選項才對。

## 好的例子
- 替客戶多勾一張他沒要的卡，就是沒經同意替他申請，誰做都不行。
- 不留傳輸紀錄，出事時就查不到誰傳了什麼，所以 (2) 錯。
- (4) 說可以由董事會授權的人核定，所以 (3)「一定要董事會」說得太死。
## 不好的例子
- 「依○○辦法第 5 條規定……」（寫了法規名稱）
- 「所以答案是 (2)，因為 (2) 是對的。」（空話：只是把答案換句話說）
- 「另外，實務上銀行通常還會……」（延伸）

## 填法
用 Write 把對應的 .tsv 整檔重寫（UTF-8、Tab 分隔）：保留第一行表頭，每行「題號<TAB>類別（說明／看不出）<TAB>內容<TAB>批次代號」，批次代號照表頭下方預填的。每題都要填。
"""


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    name, batch, ids = argv[0], argv[1], argv[2:]
    Q = {q["id"]: q for q in json.loads((ROOT / "data" / "local" / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))["questions"]}
    md, rows = [SPEC, "## 題目", ""], ["題號\t類別（說明／看不出）\t內容\t批次"]
    for i in ids:
        q = Q[i]
        md += [f"### {i}", q["stem"]] + [f"- ({k}) {o}{'　**（官方正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)] + [""]
        rows.append(f"{i}\t\t\t{batch}")
    (D / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
    (D / f"{name}.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"WRITER-SHEET OK：{len(ids)} 題（批次 {batch}）→ {D / (name + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
