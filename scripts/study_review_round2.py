#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二級群組重新核對（第二輪）：判準改成「同一條規定」，對照組先經另一個代理審核（docs/K「第二級群組重新核對（第二輪）」，造假組之前寫定）
-------------------------------------------------------------------------------
流程（順序不能換）：
  python -u scripts/study_review_round2.py candidates  造候選假組（硬湊、換一題各 14 組），寫候選檔與空白審核檔。核對者不讀候選檔。
  （審核：另一個代理用新判準逐組檢查候選，在 round2-vet.tsv 填 採用／剔除、兩條規定各是什麼、理由；拿不準就剔除）
  python -u scripts/study_review_round2.py sample      從採用的候選抽假組，組成兩批盲核對檔（第一批：其餘真組＋假組；第二批：被借去造「換一題」的原組＋另抽的硬湊）。
  （核對：在 round2-judge-1.tsv、round2-judge-2.tsv 每組填 判定、不屬於的題、規定、理由）
  python -u scripts/study_review_round2.py lock        兩份判斷檔的 sha256 記入 log.tsv；有空白就拒絕。
  python -u scripts/study_review_round2.py reveal      核對判斷檔與答案鍵都沒被改過，再算分。
每一步都只印檔名、組數與雜湊，不印哪幾組是假的。
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
CAND = S / "round2-candidates.json"
CAND_MD = S / "round2-candidates.md"
VET = S / "round2-vet.tsv"
SHOW = [S / "round2-review-1.md", S / "round2-review-2.md"]
JUDGE = [S / "round2-judge-1.tsv", S / "round2-judge-2.tsv"]
KEY = S / "round2-key.json"
RESULT = S / "round2-result.json"
LOG = S / "log.tsv"
SEED = 20261011
BAND = (0.15, 0.5)
N_CAND = 14
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


def load():
    qs = {q["id"]: q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"]}
    points = json.loads(POINTS.read_text(encoding="utf-8"))["points"]
    real = [[i for i in p["ids"] if not qs[i].get("dupOf")] for p in points if "2" in p["level"]]
    return qs, points, real


def show_q(q, lab):
    out = [f"**{lab}**（第 {q['period']} 期・{SUBJ.get(q['subject'], q['subject'])}）{q['stem']}"]
    out += [f"- ({k}) {o}{'　**（正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
    return out + [""]


def candidates():
    if CAND.exists():
        print("ROUND2 ABORT：候選已經造過了")
        return 2
    qs, points, real = load()
    G = {i: grams(q["stem"] + q["options"][q["answer"] - 1]) for i, q in qs.items()}
    in_point = {i for p in points for i in p["ids"]}
    pool = [i for i, q in qs.items() if not q.get("dupOf") and i not in in_point]
    rnd = random.Random(SEED)
    used = set()

    def ok_with(c, members):
        if c in used or c in members:
            return False
        if qs[c]["subject"] != qs[members[0]]["subject"] or qs[c]["period"] in {qs[m]["period"] for m in members}:
            return False
        js = [jac(G[c], G[m]) for m in members]
        return BAND[0] <= max(js) < BAND[1]

    cands = []
    order = list(range(len(real)))
    rnd.shuffle(order)
    for gi in order:
        if sum(c["kind"] == "換一題" for c in cands) == N_CAND:
            break
        m = list(real[gi])
        victim = rnd.randrange(len(m))
        keep = m[:victim] + m[victim + 1:]
        opts = [c for c in pool if ok_with(c, keep)]
        if not opts:
            continue
        c = rnd.choice(opts)
        used.add(c)
        cands.append({"kind": "換一題", "members": keep + [c], "inserted": c, "replaced": m[victim], "source": gi})
    tries = 0
    while sum(c["kind"] == "硬湊" for c in cands) < N_CAND and tries < 20000:
        tries += 1
        a = rnd.choice(pool)
        if a in used:
            continue
        mem, size = [a], (3 if rnd.random() < 1 / 6 else 2)
        while len(mem) < size:
            opts = [c for c in pool if ok_with(c, mem)]
            if not opts:
                break
            mem.append(rnd.choice(opts))
        if len(mem) < size:
            continue
        used.update(mem)
        cands.append({"kind": "硬湊", "members": mem})
    rnd.shuffle(cands)
    md = ["# 第二輪候選假組（給審核代理；核對者不讀這個檔）", "",
          "判準：組內每一題在問同一條規定、而且那條規定指得出來（條號，或法規名稱＋該條內容）才算同一組。",
          "審核要做的：逐組判斷這組是否**確定是不同規定**——是就「採用」（拿去當假組），拿不準或其實是同一條就「剔除」。", ""]
    vet = ["候選\t審核（採用／剔除）\t各題分屬的規定（法規名稱＋內容；標題幹或未查證）\t理由"]
    for n, c in enumerate(cands, 1):
        c["cid"] = f"C{n:02d}"
        mem = sorted(c["members"], key=lambda i: (qs[i]["period"], i))
        c["members"] = mem
        lab = {i: LABELS[k] for k, i in enumerate(mem)}
        head = f"## {c['cid']}（{c['kind']}"
        head += f"：被換進來的是{lab[c['inserted']]}，要確定它跟其他題是不同規定）" if c["kind"] == "換一題" else "：要確定每一題都不是同一條規定）"
        md.append(head)
        for i in mem:
            md += show_q(qs[i], lab[i])
        vet.append(f"{c['cid']}\t\t\t")
    S.mkdir(parents=True, exist_ok=True)
    CAND.write_text(json.dumps({"seed": SEED, "candidates": cands}, ensure_ascii=False, indent=1), encoding="utf-8")
    CAND_MD.write_text("\n".join(md), encoding="utf-8")
    VET.write_text("\n".join(vet) + "\n", encoding="utf-8")
    for p in (Path(__file__), CAND, CAND_MD, VET):
        log("round2-candidates", p)
    print(f"ROUND2 CANDIDATES OK：候選 {len(cands)} 組（硬湊 {sum(c['kind'] == '硬湊' for c in cands)}、換一題 {sum(c['kind'] == '換一題' for c in cands)}）")
    print(f"  給審核代理：{CAND_MD}；審核檔：{VET}")
    return 0


def vet_rows():
    out = {}
    for l in VET.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + ["", "", "", ""])[:4]]
            out[c[0]] = c
    return out


def sample():
    if KEY.exists():
        print("ROUND2 ABORT：已經抽過了")
        return 2
    V = vet_rows()
    bad = [k for k, r in V.items() if r[1] not in ("採用", "剔除") or not r[2] or not r[3]]
    if bad:
        print(f"ROUND2 ABORT：審核檔有空白或格式不對：{bad}")
        return 2
    log("round2-vet", VET)
    qs, points, real = load()
    cands = json.loads(CAND.read_text(encoding="utf-8"))["candidates"]
    ok = [c for c in cands if V[c["cid"]][1] == "採用"]
    rnd = random.Random(SEED + 1)
    A = [c for c in ok if c["kind"] == "硬湊"]
    B = [c for c in ok if c["kind"] == "換一題"]
    rnd.shuffle(A)
    rnd.shuffle(B)
    n_a, n_b, m = rnd.randint(3, 6), rnd.randint(3, 6), rnd.randint(2, 4)
    fa, fb = A[:n_a], B[:n_b]
    fa2 = A[len(fa):len(fa) + m]
    sources = {c["source"] for c in fb}
    batch1 = [{"kind": "真", "members": real[gi], "real": gi} for gi in range(len(real)) if gi not in sources] \
        + [{"kind": c["kind"], "members": c["members"], "cid": c["cid"], **({"inserted": c["inserted"]} if "inserted" in c else {})} for c in fa + fb]
    batch2 = [{"kind": "真", "members": real[gi], "real": gi} for gi in sorted(sources)] \
        + [{"kind": c["kind"], "members": c["members"], "cid": c["cid"]} for c in fa2]
    key = {"seed": SEED, "approved": {"硬湊": len(A), "換一題": len(B)}, "used": {"硬湊": len(fa) + len(fa2), "換一題": len(fb)}, "batches": []}
    for bi, (batch, show, judge) in enumerate(zip((batch1, batch2), SHOW, JUDGE), 1):
        rnd.shuffle(batch)
        prefix = "AB"[bi - 1]
        md = [f"# 第二輪盲核對・第 {bi} 批（有混入假組；判斷寫在 {judge.name}）", "",
              "判準：組內每一題在問同一條規定、而且那條規定指得出來（條號，或法規名稱＋該條內容）→ 保留；指不出一條同時涵蓋每一題的規定 → 拆開。", ""]
        jl = ["組\t判定（保留／拆開）\t不屬於的題（三題以上的組才要；兩題組留空）\t規定（法規名稱＋內容，或條號；標題幹／未查證）\t理由"]
        kb = []
        for n, g in enumerate(batch, 1):
            code = f"{prefix}{n:02d}"
            mem = sorted(g["members"], key=lambda i: (qs[i]["period"], i))
            lab = {i: LABELS[k] for k, i in enumerate(mem)}
            md.append(f"## {code}")
            for i in mem:
                md += show_q(qs[i], lab[i])
            jl.append(f"{code}\t\t\t\t")
            kb.append({"code": code, "kind": g["kind"], "ids": mem, **({"real": g["real"]} if "real" in g else {}),
                       **({"cid": g["cid"]} if "cid" in g else {}), **({"odd": lab[g["inserted"]]} if "inserted" in g else {})})
        show.write_text("\n".join(md), encoding="utf-8")
        judge.write_text("\n".join(jl) + "\n", encoding="utf-8")
        key["batches"].append(kb)
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (*SHOW, *JUDGE, KEY):
        log("round2-sample", p)
    print(f"ROUND2 SAMPLE OK：第 1 批 {len(batch1)} 組、第 2 批 {len(batch2)} 組；答案鍵已另存（揭曉前不讀）")
    return 0


def jrows(p):
    out = {}
    for l in p.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + [""] * 5)[:5]]
            out[c[0]] = c
    return out


def lock():
    if any(logged("round2-lock", j.name) for j in JUDGE):
        print("ROUND2 ABORT：已經鎖定過")
        return 2
    for j in JUDGE:
        bad = [k for k, r in jrows(j).items() if r[1] not in ("保留", "拆開") or not r[4] or (r[1] == "保留" and not r[3])]
        if bad:
            print(f"ROUND2 ABORT：{j.name} 有空白或格式不對：{bad}")
            return 2
    for j in JUDGE:
        log("round2-lock", j)
    print("ROUND2 LOCK OK：" + "、".join(f"{j.name} {len(jrows(j))} 組 {sha(j)[:12]}…" for j in JUDGE))
    return 0


def reveal():
    for j in JUDGE:
        lk = logged("round2-lock", j.name)
        if not lk or sha(j) != lk[-1]:
            print(f"ROUND2 ABORT：{j.name} 沒鎖定或鎖定後被改過")
            return 2
    if sha(KEY) != logged("round2-sample", KEY.name)[-1]:
        print("ROUND2 ABORT：答案鍵在抽樣之後被改過")
        return 2
    key = json.loads(KEY.read_text(encoding="utf-8"))
    caught, missed, reals = [], [], []
    for kb, j in zip(key["batches"], JUDGE):
        J = jrows(j)
        for g in kb:
            r = J[g["code"]]
            if g["kind"] == "真":
                reals.append({"code": g["code"], "real": g["real"], "ids": g["ids"], "verdict": r[1], "rule": r[3], "reason": r[4]})
                continue
            need = g.get("odd") if (g["kind"] == "換一題" and len(g["ids"]) >= 3) else None
            hit = r[1] == "拆開" and (need is None or r[2] == need)
            (caught if hit else missed).append({"code": g["code"], "kind": g["kind"], "cid": g.get("cid"), "size": len(g["ids"]),
                                                "need": need, "verdict": r[1], "named": r[2], "rule": r[3], "reason": r[4]})
    split = [r for r in reals if r["verdict"] == "拆開"]
    res = {"approved": key["approved"], "used": key["used"], "fakes": len(caught) + len(missed), "caught": caught, "missed": missed,
           "reals": len(reals), "reals_split": split, "reals_all": reals, "pass": not missed}
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("round2-reveal", RESULT)
    print(f"審核通過的候選：硬湊 {key['approved']['硬湊']}、換一題 {key['approved']['換一題']}；用掉：硬湊 {key['used']['硬湊']}、換一題 {key['used']['換一題']}")
    for c in caught:
        print(f"  ✓ {c['code']}（{c['kind']}・{c['size']} 題{('・該點名 ' + c['need']) if c['need'] else ''}）→ {c['verdict']}{('／' + c['named']) if c['named'] else ''}：{c['reason']}")
    for c in missed:
        print(f"  ✗ {c['code']}（{c['kind']}・{c['size']} 題{('・該點名 ' + c['need']) if c['need'] else ''}）→ {c['verdict']}{('／' + c['named']) if c['named'] else ''}：{c['reason']}")
    print(f"真組 {len(reals)} 組：保留 {len(reals) - len(split)}、拆開 {len(split)}" + "".join(f"\n  · {r['code']}（原第 {r['real'] + 1} 組）拆開：{r['reason']}" for r in split))
    print(f"ROUND2 {'PASS' if not missed else 'FAIL'}：假組 {len(caught)}／{len(caught) + len(missed)} 判拆開（三題以上的換一題要點名正確）")
    return 0 if not missed else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"candidates": candidates, "sample": sample, "lock": lock, "reveal": reveal}.get(cmd, lambda: (print("用法：candidates｜sample｜lock｜reveal"), 2)[1])())
