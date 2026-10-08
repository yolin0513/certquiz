#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二級考點群組核對的對照：混入假組再核對一次（docs/K_讀書模式方案.md「第二級考點群組核對的對照」，造假組之前寫定）
-------------------------------------------------------------------------------
流程（順序不能換）：
  python -u scripts/study_review_check.py sample   造假組、洗牌、寫出盲核對檔與空白判斷檔；答案鍵另存。全部只在本機（data/local/study/）。
                                                   本程式、盲核對檔、判斷檔、答案鍵的 sha256 記入 log.tsv。已造過就拒絕。
  （核對：在 review-check-judge.tsv 每一列填 保留／拆開、拆開時點名哪一題（甲／乙／丙…或「整組」）、一句理由）
  python -u scripts/study_review_check.py lock     鎖定：判斷檔的 sha256 記入 log.tsv。有空白就拒絕。
  python -u scripts/study_review_check.py reveal   揭曉：先核對判斷檔跟鎖定時相同（不同就拒絕），再對答案鍵算分。

sample 只印檔名與雜湊，不印假組數量、不印哪幾組是假的（三個數字只寫進答案鍵）。
"""
import hashlib
import json
import random
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
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
S = ROOT / "data" / "local" / "study"
POINTS = S / "points.json"
SHOW = S / "review-check.md"
JUDGE = S / "review-check-judge.tsv"
KEY = S / "review-check-key.json"
RESULT = S / "review-check-result.json"
LOG = S / "log.tsv"
SEED = 20261010
BAND = (0.15, 0.5)
LABELS = "甲乙丙丁戊己庚"
SUBJ = {"law": "法規", "gen": "實務"}
PUNCT = re.compile(r"[\s，。、；：「」（）()？?！!．.,]")   # 跟 study_points.py 同一套相似度


def grams(s, n=3):
    s = PUNCT.sub("", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, path):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{path.name}\t{sha(path)}\n")


def logged(action, name):
    if not LOG.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOG.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def sample():
    if KEY.exists() or SHOW.exists() or JUDGE.exists():
        print("REVIEW-CHECK ABORT：已經造過了（不重造；要重來先跟 Dispatch 說）")
        return 2
    qs = {q["id"]: q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"]}
    points = json.loads(POINTS.read_text(encoding="utf-8"))["points"]
    G = {i: grams(q["stem"] + q["options"][q["answer"] - 1]) for i, q in qs.items()}
    in_point = {i for p in points for i in p["ids"]}
    pool = [i for i, q in qs.items() if not q.get("dupOf") and i not in in_point]
    real = [[i for i in p["ids"] if not qs[i].get("dupOf")] for p in points if "2" in p["level"]]
    rnd = random.Random(SEED)
    n_a, n_b, n_drop = rnd.randint(3, 6), rnd.randint(3, 6), rnd.randint(0, 4)
    used = set()

    def ok_with(c, members):
        if c in used or c in members:
            return False
        if qs[c]["subject"] != qs[members[0]]["subject"] or qs[c]["period"] in {qs[m]["period"] for m in members}:
            return False
        js = [jac(G[c], G[m]) for m in members]
        return max(js) >= BAND[0] and max(js) < BAND[1]

    groups = []   # {members, kind, odd}
    # 乙、換一題
    order = list(range(len(real)))
    rnd.shuffle(order)
    swapped = set()
    for gi in order:
        if len(swapped) == n_b:
            break
        m = list(real[gi])
        victim = rnd.randrange(len(m))
        keep = m[:victim] + m[victim + 1:]
        cands = [c for c in pool if ok_with(c, keep)]
        if not cands:
            continue
        c = rnd.choice(cands)
        used.add(c)
        swapped.add(gi)
        groups.append({"members": keep + [c], "kind": "乙", "odd": c, "source": real[gi], "replaced": m[victim]})
    # 甲、硬湊（大小比例跟真組差不多：約六分之一是三題）
    tries = 0
    while sum(g["kind"] == "甲" for g in groups) < n_a and tries < 10000:
        tries += 1
        a = rnd.choice(pool)
        if a in used:
            continue
        mem = [a]
        size = 3 if rnd.random() < 1 / 6 else 2
        while len(mem) < size:
            cands = [c for c in pool if ok_with(c, mem)]
            if not cands:
                break
            mem.append(rnd.choice(cands))
        if len(mem) < size:
            continue
        used.update(mem)
        groups.append({"members": mem, "kind": "甲", "odd": "整組"})
    # 真組：拿掉換題用掉的，再隨機拿掉 n_drop 組
    rest = [gi for gi in range(len(real)) if gi not in swapped]
    dropped = set(rnd.sample(rest, n_drop))
    for gi in rest:
        if gi not in dropped:
            groups.append({"members": real[gi], "kind": "真", "odd": None, "source": real[gi]})
    rnd.shuffle(groups)

    key, lines, judge = [], ["# 第二級考點群組核對（盲核對：有混入假組；判斷寫在 review-check-judge.tsv）", ""], ["組\t判定（保留／拆開）\t不屬於的題（甲／乙／丙…或整組；保留就留空）\t理由"]
    for n, g in enumerate(groups, 1):
        code = f"R{n:02d}"
        mem = sorted(g["members"], key=lambda i: (qs[i]["period"], i))
        lab = {i: LABELS[k] for k, i in enumerate(mem)}
        lines.append(f"## {code}")
        for i in mem:
            q = qs[i]
            lines.append(f"**{lab[i]}**（第 {q['period']} 期・{SUBJ.get(q['subject'], q['subject'])}）{q['stem']}")
            for k, o in enumerate(q["options"], 1):
                lines.append(f"- ({k}) {o}{'　**（正解）**' if k == q['answer'] else ''}")
            lines.append("")
        judge.append(f"{code}\t\t\t")
        key.append({"code": code, "kind": g["kind"], "ids": mem, "odd": lab.get(g["odd"], g["odd"]),
                    **({"source": g["source"]} if "source" in g else {}), **({"replaced": g["replaced"]} if "replaced" in g else {})})
    S.mkdir(parents=True, exist_ok=True)
    SHOW.write_text("\n".join(lines), encoding="utf-8")
    JUDGE.write_text("\n".join(judge) + "\n", encoding="utf-8")
    KEY.write_text(json.dumps({"seed": SEED, "n_a": sum(g["kind"] == "甲" for g in groups), "n_b": len(swapped), "n_drop": n_drop,
                               "groups": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), SHOW, JUDGE, KEY):
        log("review-check-sample", p)
    print(f"REVIEW-CHECK SAMPLE OK：盲核對檔 {SHOW.name}（{len(groups)} 組）、判斷檔 {JUDGE.name}；答案鍵已另存（揭曉前不讀）")
    print(f"  雜湊：{SHOW.name} {sha(SHOW)[:12]}…、{KEY.name} {sha(KEY)[:12]}…（全文在 log.tsv）")
    return 0


def rows():
    out = []
    for l in JUDGE.read_text(encoding="utf-8").splitlines()[1:]:
        if not l.strip():
            continue
        c = (l.split("\t") + ["", "", "", ""])[:4]
        out.append([x.strip() for x in c])
    return out


def lock():
    if logged("review-check-lock", JUDGE.name):
        print("REVIEW-CHECK ABORT：已經鎖定過")
        return 2
    bad = [r[0] for r in rows() if r[1] not in ("保留", "拆開") or not r[3] or (r[1] == "拆開" and not r[2])]
    if bad:
        print(f"REVIEW-CHECK ABORT：判斷檔有空白或格式不對：{bad}")
        return 2
    log("review-check-lock", JUDGE)
    print(f"REVIEW-CHECK LOCK OK：{len(rows())} 組，判斷檔雜湊 {sha(JUDGE)[:12]}… 已記入 log.tsv")
    return 0


def reveal():
    locked = logged("review-check-lock", JUDGE.name)
    if not locked:
        print("REVIEW-CHECK ABORT：還沒鎖定")
        return 2
    if sha(JUDGE) != locked[-1]:
        print("REVIEW-CHECK ABORT：判斷檔在鎖定之後被改過")
        return 2
    if sha(KEY) != logged("review-check-sample", KEY.name)[-1]:
        print("REVIEW-CHECK ABORT：答案鍵在造好之後被改過")
        return 2
    key = json.loads(KEY.read_text(encoding="utf-8"))
    J = {r[0]: r for r in rows()}
    fakes = [g for g in key["groups"] if g["kind"] != "真"]
    reals = [g for g in key["groups"] if g["kind"] == "真"]
    caught, missed = [], []
    for g in fakes:
        r = J[g["code"]]
        hit = r[1] == "拆開" and (g["kind"] == "甲" or r[2] == g["odd"])
        (caught if hit else missed).append({"code": g["code"], "kind": g["kind"], "odd": g["odd"], "verdict": r[1], "named": r[2], "reason": r[3]})
    changed = [{"code": g["code"], "ids": g["ids"], "verdict": J[g["code"]][1], "named": J[g["code"]][2], "reason": J[g["code"]][3]}
               for g in reals if J[g["code"]][1] != "保留"]
    res = {"fakes": len(fakes), "n_a": key["n_a"], "n_b": key["n_b"], "n_drop": key["n_drop"], "reals": len(reals),
           "caught": caught, "missed": missed, "reals_changed": changed, "pass": not missed}
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("review-check-reveal", RESULT)
    print(f"假組 {len(fakes)} 組（甲 硬湊 {key['n_a']}、乙 換一題 {key['n_b']}）；真組 {len(reals)} 組（另拿掉 {key['n_drop']} 組不核對）")
    for c in caught:
        print(f"  ✓ {c['code']}（{c['kind']}，該點名：{c['odd']}）→ {c['verdict']}／{c['named']}：{c['reason']}")
    for c in missed:
        print(f"  ✗ {c['code']}（{c['kind']}，該點名：{c['odd']}）→ {c['verdict']}／{c['named'] or '—'}：{c['reason']}")
    print(f"真組改判（第一次全部保留）：{len(changed)} 組" + "".join(f"\n  · {c['code']} → {c['verdict']}／{c['named']}：{c['reason']}" for c in changed))
    print(f"REVIEW-CHECK {'PASS' if not missed else 'FAIL'}：假組 {len(caught)}／{len(fakes)} 抓到並點名正確")
    return 0 if not missed else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"sample": sample, "lock": lock, "reveal": reveal}.get(cmd, lambda: (print("用法：sample｜lock｜reveal"), 2)[1])())
