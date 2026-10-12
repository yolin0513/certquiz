#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」換方法：模型逐題分類全部 1,174 題（docs/L 第 15 節，算之前寫定並提交 c58c3c8）
-------------------------------------------------------------------------------
  python -u scripts/ethics_modelcls.py batches        全量打亂分 12 批 → 給 12 個分類代理（Opus），各填一個判斷檔
  python -u scripts/ethics_modelcls.py lock cls       12 批都填完 → 合併、鎖雜湊（之後才能抽任何驗證樣本）
  python -u scripts/ethics_modelcls.py draw stab      ④ 抽 100 題給另一個新的分類代理（同模型）重分
  python -u scripts/ethics_modelcls.py lock stab
  python -u scripts/ethics_modelcls.py check stab     ④ 沒過就停，不往下
  python -u scripts/ethics_modelcls.py draw verify    ① 難題 80＋每類 20 → 驗證者（Sonnet）盲判
  python -u scripts/ethics_modelcls.py lock verify
  python -u scripts/ethics_modelcls.py draw dispatch  ⑤ 難題 30＋其他 10（同一份也開給使用者本人的欄位）
  python -u scripts/ethics_modelcls.py lock dispatch｜lock owner
  python -u scripts/ethics_modelcls.py report         算 ④①③⑤（＋本人，若已補）→ modelcls-result.json
門檻寫在下面的常數裡，揭曉後不改。所有輸出只放本機 data/local/sfi/。
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ethics_stats as E  # noqa: E402

D = E.D / "modelcls"
SEED_ALL, SEED_STAB, SEED_VER, SEED_DIS = 20261016, 20261017, 20261018, 20261019
N_BATCH = 12
N_STAB, STAB_OK = 100, 0.95
N_HARD, PER_CLASS = 80, 20
N_DIS_HARD, N_DIS_OTHER, DIS_OK = 30, 10, 0.90
ALL_OK, EACH_OK, HARD_OK = E.RULER_ALL, E.RULER_EACH, 0.90
LABELS = {"對": "pos", "錯": "neg", "屬類": "member", "其他": "other"}
RESULT = D / "modelcls-result.json"
CLS = D / "cls-merged.json"

HEAD = ["# 題型判斷", "", "每題只看題幹，照下面的規格判斷（規格原文）：", "", E.SPEC3, "",
        "判斷寫成四個字之一：**對**（第 1 或第 3 類）、**錯**（第 2 類）、**屬類**（第 4 類）、**其他**（第 5 類）。", ""]


def write_set(name, qs, prefix, rnd):
    """寫一份給判斷者的題目檔（md）、空白判斷檔（tsv）、對照檔（key，判斷者不可讀）。"""
    rnd.shuffle(qs)
    md, tsv, key = list(HEAD), ["編號\t判斷（對／錯／屬類／其他）"], []
    for n, q in enumerate(qs, 1):
        code = f"{prefix}{n:03d}"
        md += [f"## {code}", q["stem"], ""]
        tsv.append(f"{code}\t")
        key.append({"code": code, "id": q["id"]})
    paths = (D / f"{name}-sample.md", D / f"{name}-judge.tsv", D / f"{name}-key.json")
    paths[0].write_text("\n".join(md), encoding="utf-8")
    paths[1].write_text("\n".join(tsv) + "\n", encoding="utf-8")
    paths[2].write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in paths:
        E.log(f"modelcls-draw-{name}", p)
    return paths


def judged(name):
    """回傳 {題目 id: 標記}；判斷檔要已鎖定、而且鎖定後沒被改過。"""
    tsv, key = D / f"{name}-judge.tsv", D / f"{name}-key.json"
    lk = E.logged(f"modelcls-lock-{name}", tsv.name)
    if not lk or E.sha(tsv) != lk[-1]:
        return None
    J = E.judge_rows(tsv)
    return {k["id"]: LABELS.get(J.get(k["code"])) for k in json.loads(key.read_text(encoding="utf-8"))}


def cls():
    lk = E.logged("modelcls-lock-cls", CLS.name)
    if not lk or E.sha(CLS) != lk[-1]:
        return None
    return json.loads(CLS.read_text(encoding="utf-8"))


def prior_ids():
    out = set()
    for kf in (E.KEY, E.KEY2, E.KEY3):
        out |= {k["id"] for k in json.loads(kf.read_text(encoding="utf-8"))["sample"]}
    return out


def batches():
    D.mkdir(exist_ok=True)
    if (D / "b01-key.json").exists():
        print("BATCHES ABORT：已經分過批了")
        return 2
    qs = sorted(E.load116(), key=lambda q: q["id"])
    random.Random(SEED_ALL).shuffle(qs)
    size = -(-len(qs) // N_BATCH)
    for b in range(N_BATCH):
        write_set(f"b{b + 1:02d}", qs[b * size:(b + 1) * size], f"B{b + 1:02d}-", random.Random(SEED_ALL + b))
    E.log("modelcls-code", Path(__file__))
    print(f"BATCHES OK：{len(qs)} 題分 {N_BATCH} 批（每批 ≤ {size} 題）→ {D}")
    return 0


def lock(name):
    if name == "cls":
        if E.logged("modelcls-lock-cls", CLS.name):
            print("LOCK ABORT：全量分類已經鎖定過")
            return 2
        merged = {}
        for b in range(N_BATCH):
            n = f"b{b + 1:02d}"
            rows = E.judge_rows(D / f"{n}-judge.tsv")
            bad = [k for k, v in rows.items() if v not in LABELS]
            key = json.loads((D / f"{n}-key.json").read_text(encoding="utf-8"))
            if bad or len(rows) != len(key):
                print(f"LOCK ABORT：{n} 有空白或格式不對：{bad[:8]}（{len(rows)}／{len(key)} 行）")
                return 2
            E.log(f"modelcls-lock-{n}", D / f"{n}-judge.tsv")
            merged.update({k["id"]: LABELS[rows[k["code"]]] for k in key})
        if len(merged) != sum(E.EXPECT.values()):
            print(f"LOCK ABORT：合併後 {len(merged)} 題，應該 {sum(E.EXPECT.values())}")
            return 2
        CLS.write_text(json.dumps(merged, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        E.log("modelcls-lock-cls", CLS)
        cnt = {c: sum(1 for v in merged.values() if v == c) for c in E.CLS_NAME3}
        hard = sum(1 for q in E.load116() if E.qtype3(q) != merged[q["id"]])
        print(f"LOCK OK：全量 {len(merged)} 題；分類 {cnt}；跟關鍵字規則不同（難題）{hard} 題")
        return 0
    tsv = D / f"{name}-judge.tsv"
    if E.logged(f"modelcls-lock-{name}", tsv.name):
        print(f"LOCK ABORT：{name} 已經鎖定過")
        return 2
    rows = E.judge_rows(tsv)
    bad = [k for k, v in rows.items() if v not in LABELS]
    if bad:
        print(f"LOCK ABORT：{name} 有空白或格式不對：{bad[:8]}")
        return 2
    E.log(f"modelcls-lock-{name}", tsv)
    print(f"LOCK OK：{tsv.name} {E.sha(tsv)[:12]}…")
    return 0


def draw(name):
    C = cls()
    if C is None:
        print("DRAW ABORT：全量分類還沒鎖定")
        return 2
    if (D / f"{name}-key.json").exists():
        print(f"DRAW ABORT：{name} 已經抽過")
        return 2
    qs = sorted(E.load116(), key=lambda q: q["id"])
    used = prior_ids()
    for n in ("verify", "stab"):
        kf = D / f"{n}-key.json"
        if kf.exists():
            used |= {k["id"] for k in json.loads(kf.read_text(encoding="utf-8"))}
    hard = [q for q in qs if E.qtype3(q) != C[q["id"]]]
    if name == "stab":
        rnd = random.Random(SEED_STAB)
        write_set("stab", rnd.sample(qs, N_STAB), "S", rnd)
        print(f"DRAW OK：④ 抽 {N_STAB} 題")
    elif name == "verify":
        rnd = random.Random(SEED_VER)
        pool = [q for q in qs if q["id"] not in prior_ids()]
        hpool = [q for q in hard if q["id"] not in prior_ids()]
        hs = rnd.sample(hpool, min(N_HARD, len(hpool)))
        hid = {q["id"] for q in hs}
        cs = []
        for c in E.CLS_NAME3:
            cp = [q for q in pool if C[q["id"]] == c and q["id"] not in hid]
            cs += rnd.sample(cp, min(PER_CLASS, len(cp)))
        write_set("verify", hs + cs, "V", rnd)
        (D / "verify-strata.json").write_text(json.dumps({"hard": sorted(hid)}, ensure_ascii=False), encoding="utf-8")
        E.log("modelcls-draw-verify", D / "verify-strata.json")
        print(f"DRAW OK：① 難題 {len(hs)}（難題母體 {len(hpool)}）＋各類 {len(cs)} 題")
    elif name == "dispatch":
        rnd = random.Random(SEED_DIS)
        hp = [q for q in hard if q["id"] not in used]
        hs = rnd.sample(hp, min(N_DIS_HARD, len(hp)))
        hid = {q["id"] for q in hs}
        op = [q for q in qs if q["id"] not in used and q["id"] not in hid]
        os_ = rnd.sample(op, N_DIS_OTHER)
        paths = write_set("dispatch", hs + os_, "P", rnd)
        # 使用者本人的欄位：同一份題、同一組編號，判斷檔另開
        owner = D / "owner-judge.tsv"
        owner.write_text(paths[1].read_text(encoding="utf-8"), encoding="utf-8")
        (D / "owner-key.json").write_text(paths[2].read_text(encoding="utf-8"), encoding="utf-8")
        E.log("modelcls-draw-owner", owner)
        print(f"DRAW OK：⑤ 難題 {len(hs)}＋其他 {len(os_)} 題（本人欄位已開，同一份題）")
    else:
        print("DRAW ABORT：未知的樣本名稱")
        return 2
    return 0


def rate(pairs):
    return sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else 0.0


def per_class(pairs):
    """pairs = [(模型的分類, 判斷者的標記)]；依模型的分類算每類一致。"""
    out = {}
    for c, j in pairs:
        out.setdefault(c, []).append(c == j)
    return {c: (sum(v) / len(v), len(v)) for c, v in out.items()}


def check_stab(C):
    S = judged("stab")
    if S is None:
        return None
    r = rate([(C[i], v) for i, v in S.items()])
    return {"rate": r, "n": len(S), "pass": r >= STAB_OK}


def report():
    C = cls()
    if C is None:
        print("REPORT ABORT：全量分類還沒鎖定")
        return 2
    res = {"counts": {c: sum(1 for v in C.values() if v == c) for c in E.CLS_NAME3}}
    qs = E.load116()
    res["hard_total"] = sum(1 for q in qs if E.qtype3(q) != C[q["id"]])
    st = check_stab(C)
    res["stab"] = st
    if st is None:
        print("REPORT ABORT：④ 還沒鎖定")
        return 2
    print(f"④ 自己跟自己比：{st['rate']:.0%}（{st['n']} 題；門檻 {STAB_OK:.0%}）→ {'過' if st['pass'] else '沒過，停'}")
    gates = {"stab": st["pass"]}
    if st["pass"]:
        V = judged("verify")
        if V is not None:
            hid = set(json.loads((D / "verify-strata.json").read_text(encoding="utf-8"))["hard"])
            pairs = [(C[i], v) for i, v in V.items()]
            hp = [(C[i], v) for i, v in V.items() if i in hid]
            pc = per_class(pairs)
            ok = rate(pairs) >= ALL_OK and all(r >= EACH_OK for r, _ in pc.values()) and rate(hp) >= HARD_OK
            res["verify"] = {"overall": rate(pairs), "n": len(pairs), "per": pc, "hard": rate(hp), "n_hard": len(hp), "pass": ok,
                             "disagree": [(i, C[i], v) for i, v in V.items() if C[i] != v]}
            gates["verify"] = ok
            print(f"① 主驗尺：整體 {rate(pairs):.0%}（{len(pairs)} 題）；難題 {rate(hp):.0%}（{len(hp)} 題）；各類 "
                  + "、".join(f"{E.CLS_NAME3[c][:4]} {r:.0%}（{n}）" for c, (r, n) in pc.items()) + f" → {'過' if ok else '沒過'}")
        # ③ 第三輪鎖定的判斷
        k3 = json.loads(E.KEY3.read_text(encoding="utf-8"))["sample"]
        J3 = E.judge_rows(E.JUDGE3)
        pairs3 = [(C[k["id"]], LABELS.get(J3.get(k["code"]))) for k in k3]
        pc3 = per_class(pairs3)
        ok3 = rate(pairs3) >= ALL_OK and all(r >= EACH_OK for r, _ in pc3.values())
        res["r3"] = {"overall": rate(pairs3), "n": len(pairs3), "per": pc3, "pass": ok3}
        gates["r3"] = ok3
        print(f"③ 第三輪鎖定的判斷：整體 {rate(pairs3):.0%}；各類 " + "、".join(f"{E.CLS_NAME3[c][:4]} {r:.0%}（{n}）" for c, (r, n) in pc3.items())
              + f" → {'過' if ok3 else '沒過'}")
        for name, label in (("dispatch", "⑤ Dispatch（第三個 Claude 實例）"), ("owner", "使用者本人")):
            P = judged(name)
            if P is None:
                print(f"{label}：還沒判")
                continue
            r = rate([(C[i], v) for i, v in P.items()])
            res[name] = {"overall": r, "n": len(P), "pass": r >= DIS_OK, "disagree": [(i, C[i], v) for i, v in P.items() if C[i] != v]}
            gates[name] = r >= DIS_OK
            print(f"{label}：{r:.0%}（{len(P)} 題；門檻 {DIS_OK:.0%}）→ {'過' if r >= DIS_OK else '沒過'}")
    res["gates"] = gates
    need = ("stab", "verify", "r3", "dispatch")
    res["pass"] = all(gates.get(g) for g in need) and gates.get("owner", True)
    res["complete"] = all(g in gates for g in need) or not st["pass"]
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    E.log("modelcls-report", RESULT)
    print(f"REPORT：{'全部過，可以呈現對／錯' if res['pass'] else ('有一項沒過 → 退路' if res['complete'] else '還沒判完')} → {RESULT}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] + ["", ""]
    cmd = {"batches": batches, "lock": lambda: lock(a[1]), "draw": lambda: draw(a[1]), "report": report,
           "check": lambda: (print((lambda s: f"④ {s['rate']:.0%} → {'過' if s['pass'] else '沒過，停'}" if s else "④ 還沒鎖定")(check_stab(cls()))), 0)[1]}
    sys.exit(cmd.get(a[0], lambda: (print(__doc__), 2)[1])())
