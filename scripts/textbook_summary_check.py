#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「法規重點」摘要的獨立核對（Dispatch 2026-10-13：完整條文不再預設顯示，可複查性收進了摘要，所以摘要要另一個獨立代理逐題對照條文全文核對）
-------------------------------------------------------------------------------
  python -u scripts/textbook_summary_check.py sheet T08   → summary-T08-check.md（題目、官方正解、摘要、條文全文）＋空白判斷檔
  python -u scripts/textbook_summary_check.py lock T08    鎖定判斷檔，同時記下摘要檔當時的雜湊
  python -u scripts/textbook_summary_check.py result T08  印出結果；不一致的列出來

判準：摘要說的條號、那一款的內容、跟選項的對應，是否都跟條文全文一致、沒有偏離或多講。
textbook_build.py 只用「判一致、而且摘要檔在鎖定後沒被改過」的摘要。
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def logged(action, name):
    if not LOG.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOG.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def summaries(topic):
    out = {}
    for line in (D / f"summary-{topic}.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            qid, text = (line.split("\t") + [""])[:2]
            out[qid] = text.strip()
    return out


def files(topic):
    return D / f"summary-{topic}-check.md", D / f"summary-{topic}-judge.tsv", D / f"summary-{topic}-key.json"


def sheet(topic):
    md_p, judge_p, key_p = files(topic)
    if key_p.exists():
        print("SHEET ABORT：已經產生過")
        return 2
    basis = json.loads((D / f"basis-{topic}.json").read_text(encoding="utf-8"))["basis"]
    Q = {q["id"]: q for q in json.loads((ROOT / "data" / "local" / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))["questions"]}
    S = summaries(topic)
    if set(S) != set(basis):
        print(f"SHEET ABORT：摘要與有依據的題不一致：多 {sorted(set(S) - set(basis))}、少 {sorted(set(basis) - set(S))}")
        return 1
    md = ["# 法規重點摘要核對", "",
          "每題給你：題目、官方正解、我們寫的一句「法規重點」、以及那一條的條文全文（題目考試當時的版本）。",
          "請判斷摘要是否**跟條文一致**：條號（含款）對不對、那一款的內容有沒有講錯或講多、跟選項的對應對不對。",
          "判「一致」或「偏離」；偏離要寫一句理由。只看這份單子，不要讀其他檔案。", ""]
    rows, key = ["編號\t判斷（一致／偏離）\t理由（偏離才寫）"], {}
    for n, qid in enumerate(sorted(S), 1):
        code = f"S{n:02d}"
        q, b = Q[qid], basis[qid]
        md += [f"## {code}", q["stem"]] + [f"- ({k}) {o}{'　**（官方正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
        md += ["", f"**我們的摘要**：{S[qid]}", "", f"**條文全文**（{b['law']}{b['article']}，{b['version']} 版）：", "", "```", b["text"], "```", ""]
        rows.append(f"{code}\t\t")
        key[code] = qid
    md_p.write_text("\n".join(md), encoding="utf-8")
    judge_p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    key_p.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), md_p, key_p, D / f"summary-{topic}.tsv"):
        log("summary-sheet", p)
    print(f"SHEET OK：{len(S)} 題 → {md_p}")
    return 0


def rows(p):
    out = {}
    for l in p.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + ["", ""])[:3]]
            out[c[0]] = c
    return out


def lock(topic):
    _, judge_p, _ = files(topic)
    bad = [k for k, c in rows(judge_p).items() if c[1] not in ("一致", "偏離") or (c[1] == "偏離" and not c[2])]
    if bad:
        print(f"LOCK ABORT：判斷檔有空白或格式不對：{bad}")
        return 2
    if logged("summary-lock", judge_p.name):
        print("LOCK ABORT：已經鎖定過")
        return 2
    log("summary-lock", judge_p)
    log("summary-lock-text", D / f"summary-{topic}.tsv")
    print(f"LOCK OK：{judge_p.name}")
    return 0


def checked(topic):
    """回傳 {題號: 摘要}：判一致、判斷檔與摘要檔都在鎖定後沒被改過。沒鎖定或被改過回 None。"""
    _, judge_p, key_p = files(topic)
    sp = D / f"summary-{topic}.tsv"
    lj, ls = logged("summary-lock", judge_p.name), logged("summary-lock-text", sp.name)
    if not lj or not ls or sha(judge_p) != lj[-1] or sha(sp) != ls[-1]:
        return None
    key = json.loads(key_p.read_text(encoding="utf-8"))
    S = summaries(topic)
    J = rows(judge_p)
    return {key[c]: S[key[c]] for c in key if J.get(c, ["", ""])[1] == "一致"}, [(c, key[c], J[c][2]) for c in key if J.get(c, ["", ""])[1] != "一致"]


def result(topic):
    r = checked(topic)
    if r is None:
        print("RESULT ABORT：還沒鎖定，或鎖定後判斷檔／摘要檔被改過")
        return 2
    ok, bad = r
    print(f"RESULT：{len(ok) + len(bad)} 題，一致 {len(ok)}、偏離 {len(bad)}" + "".join(f"\n  偏離 {c} {q}：{why}" for c, q, why in bad))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] + ["", ""]
    sys.exit({"sheet": lambda: sheet(a[1]), "lock": lambda: lock(a[1]), "result": lambda: result(a[1])}.get(a[0], lambda: (print(__doc__), 2)[1])())
