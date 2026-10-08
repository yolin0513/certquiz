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

- 第三份（Claude 核對使用者提供那批）：`--user-batch`，從 user-import 題目中**沒被跨來源核對涵蓋**的題目
  分層抽 N3 題，種子 SEED_USERBATCH。跨來源核對＝題幹＋選項逐字相同、官網也有的題，已被官網答案獨立驗過。

用法：python scripts/sample_check.py              # 官網那批：Claude 40＋使用者 15
      python scripts/sample_check.py --user-batch # 使用者提供那批：Claude 20
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
SEED_USERBATCH = 20261009
N1, N2, N3 = 40, 15, 20
SUBJ_ZH = {"law": "法規", "gen": "實務"}


def load(pattern="tabf-p*-*.txt"):
    qs = []
    for f in sorted(SRC.glob(pattern)):
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
    if q.get("source") == "user-import":
        return f"第{p}期_法規(一般消費共用).pdf" if q["subj"] == "law" else f"第{p}期_一般金融_實務.pdf"
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


def norm_key(q):
    s = q["stem"] + "|" + "|".join(q[k] for k in "1234")
    return re.sub(r"[\s，,。．.、？?：:（）()「」『』]", "", s)


def write_sheet(path, text):
    """抽檢單一旦寫出，就可能被填上核對結果；重跑不准蓋掉（2026-10-08 踩過：重跑把 40 題的核對紀錄蓋掉）。
    檔案已存在時：內容的抽樣部分沒變就不動；要重寫必須加 --force。回傳 True＝寫了或不必寫。"""
    if path.exists() and "--force" not in sys.argv:
        print(f"• {path.name} 已存在，沒有覆寫（可能已有核對紀錄；真的要重寫請加 --force）")
        return True
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def main_user_batch():
    official = load("tabf-p*-*.txt")
    user = load("user-p*-*.txt")
    covered = {norm_key(q) for q in official}
    pool = [q for q in user if norm_key(q) not in covered]
    picked = stratified(pool, N3, SEED_USERBATCH)
    OUT.mkdir(parents=True, exist_ok=True)
    write_sheet(OUT / "claude_核對_使用者提供.md", render(
        picked, f"Claude 核對清單：使用者提供那批（{N3} 題，種子 {SEED_USERBATCH}）",
        [f"只從沒被跨來源核對涵蓋的 {len(pool)} 題抽（使用者提供共 {len(user)} 題）。PDF 在 refs/user/tabf/。",
         "逐題對照 PDF 的頁面影像：題幹、四個選項、頁碼；答案對該期一般金融答案卷。"], False))
    cnt = {}
    for q in picked:
        cnt[(q["period"], SUBJ_ZH[q["subj"]])] = cnt.get((q["period"], SUBJ_ZH[q["subj"]]), 0) + 1
    print(f"SAMPLE OK（使用者提供那批）：共 {len(user)} 題，未被跨來源涵蓋 {len(pool)} 題，抽 {N3} 題（種子 {SEED_USERBATCH}）")
    print("  " + "、".join(f"第{p}期{z} {c}" for (p, z), c in sorted(cnt.items())))
    return 0


def main():
    if "--user-batch" in sys.argv:
        return main_user_batch()
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
    write_sheet(OUT / "claude_核對.md", render(
        mine, f"Claude 核對清單（{N1} 題，種子 {SEED_CLAUDE}）",
        ["逐題對照官方 PDF 的頁面影像：題幹、四個選項、答案。"], False))
    write_sheet(OUT / "使用者_複核.md", render(
        user, f"TABF 題庫抽檢單（{N2} 題）",
        [f"這 {N2} 題是從 Claude 沒核對過的 {len(rest)} 題裡隨機抽的（種子 {SEED_USER}，重跑會抽到同一批）。",
         "每題寫了：哪一份 PDF、第幾頁、第幾題，以及程式轉出來的題目、選項和答案。",
         "**請打開那份 PDF 的那一頁，比對下面的文字是否一致**，特別是「答案」那一行。",
         "PDF 在電腦的 `CertQuiz/refs/tabf/past/` 資料夾；也可以從 TABF 官網「歷屆試題」重新下載同一份。"], True))
    print(f"SAMPLE OK：全部 {len(qs)} 題｜Claude {N1} 題（種子 {SEED_CLAUDE}）｜使用者 {N2} 題（種子 {SEED_USER}，從其餘 {len(rest)} 題抽）｜不重疊")
    for name, s in (("Claude", mine), ("使用者", user)):
        cnt = {}
        for q in s:
            cnt[(q["period"], SUBJ_ZH[q["subj"]])] = cnt.get((q["period"], SUBJ_ZH[q["subj"]]), 0) + 1
        print(f"  {name}：" + "、".join(f"第{p}期{z} {c}" for (p, z), c in sorted(cnt.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
