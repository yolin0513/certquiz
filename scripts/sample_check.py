#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TABF 轉檔的人工抽檢：兩份互不重疊、可重現的抽樣
------------------------------------------------
- 第一份（Claude 核對）：從全部題目依「期別×科目」分層抽 N1 題，種子 SEED_CLAUDE。
- 第二份（使用者複核）：**只從第一份沒抽到的題目裡**分層抽 N2 題，種子 SEED_USER。
  用 Claude 核對過的題去給使用者複核，兩邊就不是獨立的來源了，所以兩份不重疊。
- 種子與抽法寫死在這裡，任何人重跑都抽到同一批（可重現）。

輸出（含題目內容，只放本機 data/local/抽檢/，不入庫）：
    claude_核對.md   給 Claude 對照 PDF 用
    使用者_複核.md   給使用者：每題寫明哪一份 PDF、第幾頁、第幾題，以及轉出來的題目與答案，只要比對

用法：python scripts/sample_check.py
"""
import random
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "local" / "src" / "bic"
OUT = ROOT / "data" / "local" / "抽檢"
SEED_CLAUDE = 20261008
SEED_USER = 51808601
N1, N2 = 40, 15
SUBJ_ZH = {"law": "法規", "gen": "實務"}


def load():
    qs = []
    for f in sorted(SRC.glob("tabf-p*-*.txt")):
        for block in f.read_text(encoding="utf-8").split("\n=== ")[1:]:
            lines = block.splitlines()
            q = {"id": lines[0].strip()}
            for ln in lines[1:]:
                if ": " in ln:
                    k, v = ln.split(": ", 1)
                    q[k] = v
            q["subj"] = q["id"].split("-")[1]
            qs.append(q)
    return qs


def stratified(pool, n, seed):
    rng = random.Random(seed)
    strata = {}
    for q in pool:
        strata.setdefault((int(q["period"]), q["subj"]), []).append(q)
    keys = sorted(strata)
    base, extra = divmod(n, len(keys))
    picked = []
    for i, k in enumerate(keys):
        items = sorted(strata[k], key=lambda q: q["id"])
        picked += rng.sample(items, base + (1 if i < extra else 0))
    return sorted(picked, key=lambda q: q["id"])


def pdf_name(q):
    p = q["period"]
    return f"第{p}期_一般金融_{SUBJ_ZH[q['subj']]}.pdf"


def render(qs, title, intro, for_user):
    out = [f"# {title}", "", *intro, ""]
    for i, q in enumerate(qs, 1):
        sec = "第一節（法規）" if q["subj"] == "law" else "第二節（實務）"
        out += [f"## {i}. 第{q['period']}期 {SUBJ_ZH[q['subj']]} 第 {q['qno']} 題",
                f"- 試卷：`{pdf_name(q)}` 第 {q['page']} 頁，找題號 **{q['qno']}.**",
                f"- 答案卷：`第{q['period']}期_一般金融_答案.pdf`，{sec}欄，題號 {q['qno']}",
                f"- 轉出來的題目：{q['stem']}",
                *[f"  - ({k}) {q[k]}" for k in "1234"],
                f"- **轉出來的答案：({q['answer']})**",
                "- 比對結果：☐ 題目一致　☐ 四個選項一致　☐ 答案一致　☐ 有問題：＿＿＿＿" if for_user else "- 核對：",
                ""]
    return "\n".join(out)


def main():
    qs = load()
    if len(qs) < N1 + N2:
        print(f"SAMPLE ABORT：題目只有 {len(qs)} 題")
        return 2
    mine = stratified(qs, N1, SEED_CLAUDE)
    mine_ids = {q["id"] for q in mine}
    rest = [q for q in qs if q["id"] not in mine_ids]
    user = stratified(rest, N2, SEED_USER)
    assert not mine_ids & {q["id"] for q in user}, "兩份抽樣重疊"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "claude_核對.md").write_text(render(
        mine, f"Claude 核對清單（{N1} 題，種子 {SEED_CLAUDE}）",
        ["逐題對照官方 PDF 的頁面影像：題幹、四個選項、答案。"], False), encoding="utf-8", newline="\n")
    (OUT / "使用者_複核.md").write_text(render(
        user, f"TABF 題庫抽檢單（{N2} 題）",
        [f"這 {N2} 題是從 Claude 沒核對過的 {len(rest)} 題裡隨機抽的（種子 {SEED_USER}，重跑會抽到同一批）。",
         "每題寫了：哪一份 PDF、第幾頁、第幾題，以及程式轉出來的題目、選項和答案。",
         "**請打開那份 PDF 的那一頁，比對下面的文字是否一致**，特別是「答案」那一行。",
         "PDF 在電腦的 `CertQuiz/refs/tabf/past/` 資料夾；也可以從 TABF 官網「歷屆試題」重新下載同一份。"], True),
        encoding="utf-8", newline="\n")
    print(f"SAMPLE OK：全部 {len(qs)} 題｜Claude {N1} 題（種子 {SEED_CLAUDE}）｜使用者 {N2} 題（種子 {SEED_USER}，從其餘 {len(rest)} 題抽）｜不重疊")
    for name, s in (("Claude", mine), ("使用者", user)):
        cnt = {}
        for q in s:
            cnt[(q["period"], SUBJ_ZH[q["subj"]])] = cnt.get((q["period"], SUBJ_ZH[q["subj"]]), 0) + 1
        print(f"  {name}：" + "、".join(f"第{p}期{z} {c}" for (p, z), c in sorted(cnt.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
