#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」官方題庫 PDF → 本機題目檔（docs/L_金融市場常識與職業道德.md）
-------------------------------------------------------------------------------
來源：證基會題庫下載區（refs/sfi/ethics/，下載清單.tsv 記檔名、大小、sha256、網址、時間）。輸出只放本機 data/local/sfi/。
題庫原文著作權屬五個測驗單位，只放本機、不進公開 repo（界線同內控）。

兩種讀法，必須逐題一致（照內控答案卷 C4／C5 的做法）：
  A  pdftotext -raw：每題以「(答案) 題號」開頭，接題幹與選項。
  B  pdftotext -layout：只取行首（縮排 ≤ 2 格）的「(數字)」當答案序列——113 年職業道德那一份答案欄與題目不對齊，
     B 只靠順序；選項換行時開頭也可能是「(3)」，但那種行縮排很深，用縮排分開。
母體核對（印出來）：題號必須 1～N 連續、N 等於官方公告題數、A 與 B 的答案序列逐題相同；任何一項不符就報錯、不寫檔。

用法：python -u scripts/import_sfi.py            轉檔 4 份題庫＋兩版差異
結束碼：0 全部符合；1 有不符（不寫檔）；2 前提不成立（檔案不在）。
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "refs" / "sfi" / "ethics"
OUT = ROOT / "data" / "local" / "sfi"
# 官方公告的題數（證基會題庫下載區原文，2026-10-12 查）
BANKS = [
    {"id": "113-gen", "version": "113", "part": "gen", "file": "金融市場常識-113.pdf", "official": 504, "valid": "2024-09-01～2026-12-31"},
    {"id": "113-eth", "version": "113", "part": "eth", "file": "職業道德-113.pdf", "official": 616, "valid": "2024-09-01～2026-12-31"},
    {"id": "116-gen", "version": "116", "part": "gen", "file": "116金融市場題庫NEW.pdf", "official": 558, "valid": "2027-01-01 起"},
    {"id": "116-eth", "version": "116", "part": "eth", "file": "116職業道德題庫.pdf", "official": 616, "valid": "2027-01-01 起"},
]
PART_NAME = {"gen": "金融市場常識", "eth": "職業道德"}
FW = str.maketrans("（）１２３４５６７８９０", "()1234567890")
HEAD_RE = re.compile(r"^\((\d)\)\s*(\d+)\s*(.*)$")


def pdftotext(pdf, mode):
    r = subprocess.run(["pdftotext", mode, "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"pdftotext {mode} 讀不了 {pdf.name}：{r.stderr.decode('utf-8', 'replace')}")
    return r.stdout.decode("utf-8", "replace").translate(FW)


def join_lines(lines):
    out = ""
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if out and re.match(r"[A-Za-z0-9]", l[0]) and re.match(r"[A-Za-z0-9]", out[-1]):
            out += " "
        out += l
    return out


def split_options(text):
    """從後往前找最後一組依序出現的 (4)(3)(2)(1)。回傳 (題幹, [4 個選項]) 或 None。"""
    pos = {}
    end = len(text)
    for k in (4, 3, 2, 1):
        i = text.rfind(f"({k})", 0, end)
        if i < 0:
            return None
        pos[k] = i
        end = i
    stem = text[:pos[1]].strip()
    opts = [text[pos[k] + 3:(pos[k + 1] if k < 4 else len(text))].strip() for k in (1, 2, 3, 4)]
    if not stem or any(not o for o in opts):
        return None
    return stem, opts


def read_a(pdf):
    """讀法 A：-raw。回傳 [{no, answer, stem, options}]，以及解析不了的題號。"""
    lines = pdftotext(pdf, "-raw").splitlines()
    recs, cur, bad = [], None, []
    pending = None   # 116 年職業道德從第 369 題起，答案「(4)」單獨一行、題號與題目在下一行
    for l in lines:
        s = l.strip()
        if not s or re.fullmatch(r"\d+", s) or s.startswith("Part ") or re.fullmatch(r"答案\s*題號\s*題目", s):
            continue   # 頁碼、標題列
        if re.fullmatch(r"\((\d)\)", s):
            pending = s
            continue
        if pending:
            nxt = (recs[-1]["no"] + 1) if recs else 1
            if re.match(rf"{nxt}\s", s):
                s = f"{pending} {s}"
            elif cur:
                cur["lines"].append(pending)   # 不是題目開頭：原本就是內文，照原樣接回去
            pending = None
        m = HEAD_RE.match(s)
        if m and (not recs or int(m.group(2)) == recs[-1]["no"] + 1):
            cur = {"no": int(m.group(2)), "answer": int(m.group(1)), "lines": [m.group(3)]}
            recs.append(cur)
        elif cur:
            cur["lines"].append(s)
    out = []
    for r in recs:
        sp = split_options(join_lines(r["lines"]))
        if not sp:
            bad.append(r["no"])
            continue
        out.append({"no": r["no"], "answer": r["answer"], "stem": sp[0], "options": sp[1]})
    return out, bad, len(recs)


def read_b(pdf):
    """讀法 B：-layout，只取縮排 ≤ 2 格的行首「(數字)」，依出現順序。"""
    seq = []
    for l in pdftotext(pdf, "-layout").splitlines():
        m = re.match(r"^ {0,2}\((\d)\)", l)
        if m:
            seq.append(int(m.group(1)))
    return seq


def norm(s):
    return re.sub(r"[\s，。、；：「」（）()？?！!．.,_＿\-—]", "", s)


def grams(s, n=3):
    s = norm(s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def main():
    missing = [b["file"] for b in BANKS if not (SRC / b["file"]).exists()]
    if missing:
        print(f"IMPORT-SFI ABORT：找不到 {missing}（先照 docs/L 從證基會官網下載）")
        return 2
    fails, data = 0, {}
    print("母體核對（讀到幾題／官方公告幾題；兩種讀法的答案逐題比對）")
    for b in BANKS:
        pdf = SRC / b["file"]
        qs, bad, n_heads = read_a(pdf)
        seq_b = read_b(pdf)
        nos = [q["no"] for q in qs]
        ans_a = [q["answer"] for q in sorted(qs, key=lambda q: q["no"])]
        diff_ab = [i + 1 for i, (x, y) in enumerate(zip(ans_a, seq_b)) if x != y]
        ok = (n_heads == b["official"] and not bad and nos == list(range(1, b["official"] + 1))
              and len(seq_b) == b["official"] and not diff_ab and all(1 <= a <= 4 for a in ans_a))
        print(f"  {'✓' if ok else '✗'} {b['id']}（{b['file']}）：讀法 A 讀到 {n_heads} 題（官方公告 {b['official']}）"
              f"、選項切不出來 {len(bad)} 題{(' ' + str(bad[:8])) if bad else ''}；讀法 B 答案 {len(seq_b)} 個；"
              f"兩種讀法答案不同 {len(diff_ab)} 題{(' ' + str(diff_ab[:8])) if diff_ab else ''}")
        fails += 0 if ok else 1
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        data[b["id"]] = {**b, "sha256": sha, "questions": [
            {"id": f"ethics-{b['version']}-{b['part']}-{q['no']:03d}", "no": q["no"], "part": b["part"], "version": b["version"],
             "stem": q["stem"], "options": q["options"], "answer": q["answer"]} for q in qs]}
    if fails:
        print(f"IMPORT-SFI FAILED：{fails} 份題庫母體核對不符，不寫檔")
        return 1

    # 外部交叉核對：113 與 116 兩版裡題幹與選項完全相同的題，正解必須相同
    print("交叉核對：兩版裡題幹與四個選項完全相同的題，正解必須相同")
    xfail = 0
    for part in ("gen", "eth"):
        old = {norm(q["stem"] + "|" + "|".join(q["options"])): q for q in data[f"113-{part}"]["questions"]}
        same = [(old[k], q) for q in data[f"116-{part}"]["questions"] for k in [norm(q["stem"] + "|" + "|".join(q["options"]))] if k in old]
        conflict = [(a["no"], b["no"]) for a, b in same if a["answer"] != b["answer"]]
        print(f"  {'✓' if not conflict else '✗'} {PART_NAME[part]}：完全相同 {len(same)} 題，正解不同 {len(conflict)} 題{(' ' + str(conflict[:8])) if conflict else ''}")
        xfail += 1 if conflict else 0
    if xfail:
        print("IMPORT-SFI FAILED：兩版相同的題正解不同（讀錯或官方改了答案，要人工看），不寫檔")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in data.items():
        (OUT / f"ethics-{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"IMPORT-SFI OK：4 份題庫母體核對全部符合，寫出 {OUT}／ethics-*.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
