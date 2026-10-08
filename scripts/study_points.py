#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內控考點群組（docs/K_讀書模式方案.md 第 3 點）：哪些題目是跨期反覆考的同一個考點
-------------------------------------------------------------------------------
讀本機匯入包 data/local/import/bic-匯入包.json，輸出 data/local/study/points.json（只在本機，含題號、不含題目文字）。

兩級，只承認證明得了的：
  一、逐字重複：匯入包裡的 dupOf（題幹＋四個選項逐字相同）。
  二、跨期相似：題幹＋正解的三字組 Jaccard ≥ 門檻；只連「不同期」的題（同一期再像也不連，所以一個考點每期最多一題）；
     **全連結**：群組內每一對都必須 ≥ 門檻（不准 A 像 B、B 像 C 但 A 不像 C 的鏈狀合併）。

驗尺（同一次執行裡）：
  反對照：隨機抽 20,000 對不同期的題目，門檻必須高於它們相似度的 99 百分位，否則中止（門檻沒有鑑別力）。
  正對照：把逐字重複的題（dupOf）也放進第二級的演算法，每一組都必須被併在一起，否則中止（演算法漏抓）。
輸出：群組數、涵蓋題數、組大小分布；結束碼 0 正常、2 驗尺失敗。
"""
import json
import random
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
OUT = ROOT / "data" / "local" / "study" / "points.json"
THRESHOLD = 0.5          # docs/K 事先定的門檻
SEED = 20261008
PUNCT = re.compile(r"[\s，。、；：「」（）()？?！!．.,]")


def grams(s, n=3):
    s = PUNCT.sub("", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def cluster(items, G, per, th):
    """全連結的凝聚分群：兩群合併的條件是跨群每一對都 ≥ th 且期別不重複。回傳 [[id, ...], ...]（只回 ≥2 題的群）。"""
    ids = [q["id"] for q in items]
    # 先算所有 ≥ th 的跨期配對（候選邊）
    sim = {}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if per[a] == per[b]:
                continue
            v = jac(G[a], G[b])
            if v >= th:
                sim[(a, b)] = sim[(b, a)] = v
    groups = {i: [i] for i in ids}
    of = {i: i for i in ids}
    # 由最像的配對開始合併
    for (a, b), v in sorted(((k, v) for k, v in sim.items() if k[0] < k[1]), key=lambda kv: -kv[1]):
        ga, gb = of[a], of[b]
        if ga == gb:
            continue
        A, B = groups[ga], groups[gb]
        if {per[x] for x in A} & {per[y] for y in B}:
            continue                                   # 合併後會有同一期兩題
        if all((x, y) in sim for x in A for y in B):   # 全連結：每一對都要 ≥ th
            groups[ga] = A + B
            for y in B:
                of[y] = ga
            del groups[gb]
    return [g for g in groups.values() if len(g) > 1]


def main():
    if not PACK.exists():
        print(f"STUDY-POINTS ABORT：沒有本機匯入包 {PACK}")
        return 2
    allq = json.loads(PACK.read_text(encoding="utf-8"))["questions"]
    per = {q["id"]: f"{q.get('period')}" for q in allq}
    G = {q["id"]: grams(q["stem"] + q["options"][q["answer"] - 1]) for q in allq}
    active = [q for q in allq if not q.get("dupOf")]

    # 反對照：隨機不同期配對的相似度分布
    rnd = random.Random(SEED)
    vals = []
    while len(vals) < 20000:
        a, b = rnd.sample(active, 2)
        if per[a["id"]] != per[b["id"]]:
            vals.append(jac(G[a["id"]], G[b["id"]]))
    vals.sort()
    p99, p999 = vals[int(len(vals) * 0.99)], vals[int(len(vals) * 0.999)]
    ok_neg = THRESHOLD > p99
    print(f"{'✓' if ok_neg else '✗'} 反對照：隨機不同期配對 20,000 對，相似度 99 百分位 {p99:.3f}、99.9 百分位 {p999:.3f}；門檻 {THRESHOLD} 必須高於 99 百分位")

    # 正對照：逐字重複（dupOf）放進演算法，必須被併在一起
    dup_groups = {}
    for q in allq:
        if q.get("dupOf"):
            dup_groups.setdefault(q["dupOf"], {q["dupOf"]}).add(q["id"])
    cl_all = cluster(allq, G, per, THRESHOLD)
    where = {i: k for k, g in enumerate(cl_all) for i in g}
    missed = [k for k, g in dup_groups.items() if len({where.get(i, ("solo", i)) for i in g}) != 1]
    ok_pos = not missed
    print(f"{'✓' if ok_pos else '✗'} 正對照：逐字重複 {len(dup_groups)} 組放進演算法，全部被併在一起（漏 {len(missed)} 組）")
    if not (ok_neg and ok_pos):
        print("STUDY-POINTS ABORT：驗尺失敗，不輸出考點群組")
        return 2

    # 正式：在不重複的題目上做第二級（第一級就是 dupOf，已由匯入包標好）
    cl = cluster(active, G, per, THRESHOLD)
    sizes = {}
    for g in cl:
        sizes[len(g)] = sizes.get(len(g), 0) + 1
    # 合併：第一級留下的代表題也參加第二級，所以同一個考點可能既有逐字重複、又有改寫版——有共同題目的就併成一個考點
    raw = [{"lv": {2}, "ids": set(g)} for g in cl] + [{"lv": {1}, "ids": set(v), "keep": k} for k, v in dup_groups.items()]
    merged = []
    for r in raw:
        hit = [m for m in merged if m["ids"] & r["ids"]]
        for m in hit:
            merged.remove(m)
            r = {"lv": r["lv"] | m["lv"], "ids": r["ids"] | m["ids"]}
        merged.append(r)
    points = [{"level": "+".join(str(x) for x in sorted(m["lv"])), "ids": sorted(m["ids"], key=lambda i: (per[i], i)),
               "periods": sorted({per[i] for i in m["ids"]})} for m in merged]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"threshold": THRESHOLD, "p99_random": round(p99, 4), "points": points}, ensure_ascii=False, indent=1), encoding="utf-8")
    covered = sum(len(p["ids"]) for p in points)
    lv = {}
    for p_ in points:
        lv[p_["level"]] = lv.get(p_["level"], 0) + 1
    times = {}
    for p_ in points:
        times[len(p_["periods"])] = times.get(len(p_["periods"]), 0) + 1
    print(f"• 第一級（逐字重複）{len(dup_groups)} 組；第二級（跨期相似、全連結）{len(cl)} 組，組大小分布 {dict(sorted(sizes.items()))}")
    print(f"• 合併有共同題目的之後：{len(points)} 個考點（依來源 {dict(sorted(lv.items()))}），涵蓋 {covered} 題次（共 {len(allq)} 題）")
    print(f"• 考過幾期：{dict(sorted(times.items()))}")
    multi = [p_ for p_ in points if len(p_["ids"]) != len(set(per[i] for i in p_["ids"]))]
    print(f"• 同一期出現兩題以上的考點：{len(multi)} 個（應為 0：一個考點每期最多一題）")
    print(f"STUDY-POINTS OK：輸出 {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
