#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內控主題分組的驗收量測（docs/K_讀書模式方案.md 第 2 步「判準」）——只在驗收組上做
-------------------------------------------------------------------------------
流程（順序不能換）：
  python scripts/study_eval.py sample   抽樣：盲測配對 200 對（同組 100、跨組 100，洗牌、不給主題）＋名實相符 120 題（給主題）。
                                        題目文字寫進 data/local/study/（只在本機）；答案鍵另存；兩者雜湊記入 log.tsv。已抽過就拒絕。
  （判斷：在 judge-pairs.tsv、judge-precision.tsv 每一行填 有／沒有／說不準 或 合理／不合理／說不準）
  python scripts/study_eval.py lock     鎖定：把兩份判斷檔的 sha256 記入 log.tsv。判斷檔有空白就拒絕鎖定。
  python scripts/study_eval.py reveal   揭曉：先核對判斷檔與鎖定時的雜湊相同（不同就拒絕），再對答案鍵算分、套用事先寫死的門檻。

事先定死的內容（2026-10-08，抽樣之前）：
  - 判準 1：同組比例 ≥ 0.50 而且 同組比例 ≥ 3 × 跨組比例；分母含「說不準」；「說不準」超過 50 對（25%）＝判準 1 不過。
  - 判準 2：合理比例 ≥ 0.85，且每個主題各自 ≥ 0.70；分母含「說不準」。
  - 判準 3：所有考點群組（可練題）都落在同一個主題；由 reveal 一併全數檢查。
  - 抽樣細節：同一考點的兩題不配對（同組、跨組都排除）；「其他」不參加配對；同組配對先依驗收組各主題題數比例抽主題、再抽兩題；
    跨組配對隨機抽兩題、主題不同才收。名實相符：每個主題 6 題（不足 6 題的全收），其餘名額從驗收組（含「其他」以外）隨機補到 120。
"""
import hashlib
import json
import random
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
SEED = 20261009
N_PAIRS = 100
N_PREC = 120
PER_TOPIC = 6
OTHER = "T99"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def log(kind, p):
    h = sha(p)
    with (S / "log.tsv").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{kind}\t{Path(p).name}\t{h}\n")
    return h


def last_logged(kind, name):
    rows = [l.split("\t") for l in (S / "log.tsv").read_text(encoding="utf-8").splitlines()]
    hs = [r[3] for r in rows if len(r) >= 4 and r[1] == kind and r[2] == name]
    return hs[-1] if hs else None


def qtext(q):
    opts = "　".join(f"({k + 1}){o}" for k, o in enumerate(q["options"]))
    return f"{q['stem']}　{opts}　正解：({q['answer']}){q['options'][q['answer'] - 1]}"


def load():
    qs = {q["id"]: q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"]}
    split = json.loads((S / "split.json").read_text(encoding="utf-8"))
    tj = json.loads((S / "topics.json").read_text(encoding="utf-8"))
    points = json.loads((S / "points.json").read_text(encoding="utf-8"))["points"]
    return qs, split, tj, points


def sample():
    if (S / "key.json").exists():
        print("STUDY-EVAL ABORT：已經抽過樣（key.json 存在），不重抽——要重來只能作廢這一輪，見 docs/K")
        return 2
    qs, split, tj, points = load()
    topics, names = tj["topics"], tj["names"]
    hold = [i for i in split["holdout"] if topics[i] != OTHER]
    same_point = {}
    for k, p in enumerate(points):
        for i in p["ids"]:
            same_point[i] = k
    sp = lambda a, b: a in same_point and same_point.get(a) == same_point.get(b)
    rnd = random.Random(SEED)
    by_t = {}
    for i in hold:
        by_t.setdefault(topics[i], []).append(i)
    tlist = [t for t in by_t if len(by_t[t]) >= 2]
    weights = [len(by_t[t]) for t in tlist]
    seen, within, cross = set(), [], []
    while len(within) < N_PAIRS:
        t = rnd.choices(tlist, weights)[0]
        a, b = rnd.sample(by_t[t], 2)
        key = tuple(sorted((a, b)))
        if key in seen or sp(a, b):
            continue
        seen.add(key); within.append(key)
    while len(cross) < N_PAIRS:
        a, b = rnd.sample(hold, 2)
        key = tuple(sorted((a, b)))
        if key in seen or topics[a] == topics[b] or sp(a, b):
            continue
        seen.add(key); cross.append(key)
    pairs = [("within", p) for p in within] + [("cross", p) for p in cross]
    rnd.shuffle(pairs)
    # 名實相符
    prec = []
    for t in sorted(by_t):
        prec += rnd.sample(by_t[t], min(PER_TOPIC, len(by_t[t])))
    rest = [i for i in hold if i not in set(prec)]
    prec += rnd.sample(rest, N_PREC - len(prec))
    rnd.shuffle(prec)
    S.mkdir(parents=True, exist_ok=True)
    with (S / "judge-pairs.tsv").open("w", encoding="utf-8") as f:
        f.write("# 盲測配對：讀懂 A 的正解，對答對 B 有沒有幫助？在最後一欄填 有／沒有／說不準（可加 Tab 再寫一句理由）\n")
        for n, (_, (a, b)) in enumerate(pairs, 1):
            f.write(f"{n}\tA：{qtext(qs[a])}\n{n}\tB：{qtext(qs[b])}\n{n}\t判斷：\n")
    with (S / "judge-precision.tsv").open("w", encoding="utf-8") as f:
        f.write("# 名實相符：這題放在這個主題合理嗎、有沒有明顯更適合的主題？在最後一欄填 合理／不合理／說不準（可加 Tab 再寫一句理由）\n")
        for n, i in enumerate(prec, 1):
            f.write(f"{n}\t主題：{topics[i]} {names[topics[i]]}\n{n}\t題目：{qtext(qs[i])}\n{n}\t判斷：\n")
    key = {"seed": SEED, "pairs": [{"n": n, "kind": k, "a": a, "b": b, "ta": topics[a], "tb": topics[b]} for n, (k, (a, b)) in enumerate(pairs, 1)],
           "precision": [{"n": n, "id": i, "topic": topics[i]} for n, i in enumerate(prec, 1)]}
    (S / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in ("judge-pairs.tsv", "judge-precision.tsv", "key.json"):
        log("sample", S / p)
    print(f"STUDY-EVAL SAMPLED：配對 {len(pairs)}（同組 {len(within)}、跨組 {len(cross)}）、名實相符 {len(prec)} 題；"
          f"驗收組可配對題 {len(hold)}、主題 {len(by_t)} 個。三個檔的雜湊已記入 log.tsv。")
    return 0


def read_judgments(path, allowed):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith("判斷："):
            v = parts[1][3:].strip()
            out[int(parts[0])] = v
    bad = {n: v for n, v in out.items() if v not in allowed}
    return out, bad


def lock():
    for name, allowed in (("judge-pairs.tsv", {"有", "沒有", "說不準"}), ("judge-precision.tsv", {"合理", "不合理", "說不準"})):
        j, bad = read_judgments(S / name, allowed)
        if bad:
            print(f"STUDY-EVAL ABORT：{name} 有 {len(bad)} 行沒填或填錯（例：{list(bad.items())[:3]}），不鎖定")
            return 2
    for name in ("judge-pairs.tsv", "judge-precision.tsv"):
        h = log("lock", S / name)
        print(f"• 鎖定 {name}：sha256 {h[:16]}…")
    print("STUDY-EVAL LOCKED：之後不得修改判斷檔；揭曉時會核對雜湊")
    return 0


def reveal():
    for name in ("judge-pairs.tsv", "judge-precision.tsv"):
        h = last_logged("lock", name)
        if h is None:
            print(f"STUDY-EVAL ABORT：{name} 還沒鎖定（先 lock）")
            return 2
        if h != sha(S / name):
            print(f"STUDY-EVAL ABORT：{name} 在鎖定之後被改過（雜湊不同），拒絕揭曉")
            return 2
    qs, split, tj, points = load()
    key = json.loads((S / "key.json").read_text(encoding="utf-8"))
    names = tj["names"]
    jp, _ = read_judgments(S / "judge-pairs.tsv", set())
    jr, _ = read_judgments(S / "judge-precision.tsv", set())
    # 判準 1
    w = [p for p in key["pairs"] if p["kind"] == "within"]
    c = [p for p in key["pairs"] if p["kind"] == "cross"]
    rate = lambda ps: sum(1 for p in ps if jp[p["n"]] == "有") / len(ps)
    unsure = sum(1 for v in jp.values() if v == "說不準")
    rw, rc = rate(w), rate(c)
    c1 = unsure <= 50 and rw >= 0.50 and rw >= 3 * rc
    print(f"判準 1 互助性：同組 {rw:.0%}（{sum(1 for p in w if jp[p['n']] == '有')}/{len(w)}）、跨組 {rc:.0%}（{sum(1 for p in c if jp[p['n']] == '有')}/{len(c)}）、"
          f"說不準 {unsure}/200 → {'過' if c1 else '不過'}（門檻：同組 ≥50%、≥3 倍跨組、說不準 ≤50）")
    # 判準 2
    ok = lambda n: jr[n] == "合理"
    per = {}
    for p in key["precision"]:
        per.setdefault(p["topic"], []).append(ok(p["n"]))
    overall = sum(ok(p["n"]) for p in key["precision"]) / len(key["precision"])
    weak = {t: sum(v) / len(v) for t, v in per.items() if sum(v) / len(v) < 0.70}
    c2 = overall >= 0.85 and not weak
    print(f"判準 2 名實相符：整體 {overall:.0%}；低於 70% 的主題：{ {names[t]: f'{r:.0%}' for t, r in weak.items()} or '無'} → {'過' if c2 else '不過'}")
    for t in sorted(per):
        print(f"    {t} {names[t]}：{sum(per[t])}/{len(per[t])}")
    # 判準 3
    topics = tj["topics"]
    torn = []
    for p in points:
        ts = {topics[i] for i in p["ids"] if i in topics}
        if len(ts) > 1:
            torn.append((p["ids"], sorted(ts)))
    c3 = not torn
    print(f"判準 3 不拆散考點：{len(points)} 個考點中被拆到不同主題的 {len(torn)} 個 → {'過' if c3 else '不過'}")
    for ids, ts in torn[:20]:
        print(f"    {', '.join(i[-8:] for i in ids)} → {', '.join(names[t] for t in ts)}")
    other = sum(1 for v in topics.values() if v == OTHER)
    print(f"誠實度：其他 {other} 題（全部 {len(topics)} 題）")
    res = S / "result.json"
    res.write_text(json.dumps({"c1": {"within": rw, "cross": rc, "unsure": unsure, "pass": c1},
                               "c2": {"overall": overall, "weak": weak, "pass": c2},
                               "c3": {"torn": len(torn), "pass": c3}, "other": other}, ensure_ascii=False, indent=1), encoding="utf-8")
    log("reveal", res)
    print(f"STUDY-EVAL REVEALED：判準 1 {'過' if c1 else '不過'}、判準 2 {'過' if c2 else '不過'}、判準 3 {'過' if c3 else '不過'}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"sample": sample, "lock": lock, "reveal": reveal}.get(cmd, lambda: (print(__doc__), 2)[1])())
