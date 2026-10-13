#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「我們寫的（未查證）」的複核（docs/M 第一節，開工前寫定）
-------------------------------------------------------------------------------
  python -u scripts/textbook_ours_check.py c1 T07          C1 全量：每一段「說明」都給獨立代理判 不矛盾／矛盾 → ours-T07-c1.md／.tsv
  python -u scripts/textbook_ours_check.py sample T07      抽樣（以寫手批次分層；每批 8 段或 15% 取多；種子 20261014＋批次號）→ ours-T07-sample.md／.tsv
  python -u scripts/textbook_ours_check.py lock T07 c1|sample
  python -u scripts/textbook_ours_check.py result T07      依 docs/M 的規則判定：通過／只修那幾段＋加抽／整批退回；通過時鎖定 ours 檔

這一層沒有真值：「寫得對不對」不是核對項目。核的是 C1 不跟官方正解矛盾、C2 沒有延伸、C4 不是空話、C5 內部一致（C3 在建置時機械全量）。
「看不出」的題不寫說明（畫面上不出現），不在核對範圍。
寫手批次：ours-<章>.tsv 第四欄（例如 w1、w2）；沒有寫就算同一批。
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
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"
SEED = 20261014
RND = 1   # 第幾輪（整批退回重寫後是第 2 輪起；檔名加 -r2…，種子也加輪次，抽到的不會跟上一輪一樣）


def sfx():
    return "" if RND == 1 else f"-r{RND}"
CRIT = """- **C1 不跟官方正解矛盾**：說明的結論指向官方正解；沒有暗示別的選項才對、沒有說官方答案錯。
- **C2 沒有延伸**：只解釋為什麼正解對；沒有引進題目和選項裡都沒有的數字、期限、金額、條件或規定。
- **C4 不是空話**：要給出比「把答案換句話說」更多的理由。
- **C5 內部一致**：提到的選項編號對得上；段落沒有自相矛盾。"""


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def logged(action, name):
    if not LOG.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOG.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def ours(topic):
    """{題號: (類別, 內容, 寫手批次)}"""
    out = {}
    for line in (D / f"ours-{topic}.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            c = (line.split("\t") + ["", "", ""])[:4]
            out[c[0].strip()] = (c[1].strip(), c[2].strip(), c[3].strip() or "w1")
    return out


def qmap():
    return {q["id"]: q for q in json.loads((ROOT / "data" / "local" / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))["questions"]}


def block(q, text):
    return [q["stem"]] + [f"- ({k}) {o}{'　**（官方正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)] + ["", f"**說明**：{text}", ""]


def c1(topic):
    md_p, tsv_p = D / f"ours-{topic}-c1{sfx()}.md", D / f"ours-{topic}-c1{sfx()}.tsv"
    if md_p.exists():
        print("C1 ABORT：已經產生過")
        return 2
    O, Q = ours(topic), qmap()
    items = [(i, v) for i, v in sorted(O.items()) if v[0] == "說明"]
    md = ["# 「我們寫的」C1 全量核對", "", "每一段只判一件事：", CRIT.splitlines()[0], "", "判「不矛盾」或「矛盾」；矛盾要寫一句理由。只看這份單子。", ""]
    rows = ["題號\t判斷（不矛盾／矛盾）\t理由"]
    for i, (_, text, _) in items:
        md += [f"## {i}"] + block(Q[i], text)
        rows.append(f"{i}\t\t")
    md_p.write_text("\n".join(md), encoding="utf-8")
    tsv_p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log(f"ours-c1-sheet{sfx()}", D / f"ours-{topic}.tsv")
    print(f"C1 OK：{len(items)} 段 → {md_p}")
    return 0


def sample(topic):
    md_p, tsv_p = D / f"ours-{topic}-sample{sfx()}.md", D / f"ours-{topic}-sample{sfx()}.tsv"
    if md_p.exists():
        print("SAMPLE ABORT：已經抽過")
        return 2
    O, Q = ours(topic), qmap()
    by = {}
    for i, v in sorted(O.items()):
        if v[0] == "說明":
            by.setdefault(v[2], []).append(i)
    pick = []
    for n, (w, ids) in enumerate(sorted(by.items()), 1):
        k = min(len(ids), max(8, -(-len(ids) * 15 // 100)))
        pick += [(w, i) for i in random.Random(SEED + n + 1000 * (RND - 1)).sample(ids, k)]
    random.Random(SEED + 1000 * (RND - 1)).shuffle(pick)
    md = ["# 「我們寫的」抽樣複核", "", "每一段判四項（不要判「寫得對不對」——那沒有真值）：", CRIT, "",
          "每項填「合格」或「不合格」；有不合格要寫一句理由。只看這份單子。", ""]
    rows = ["題號\tC1\tC2\tC4\tC5\t理由"]
    for w, i in pick:
        md += [f"## {i}"] + block(Q[i], O[i][1])
        rows.append(f"{i}\t\t\t\t\t")
    md_p.write_text("\n".join(md), encoding="utf-8")
    tsv_p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (D / f"ours-{topic}-sample-key{sfx()}.json").write_text(json.dumps({i: w for w, i in pick}, ensure_ascii=False), encoding="utf-8")
    log(f"ours-sample-sheet{sfx()}", D / f"ours-{topic}.tsv")
    print(f"SAMPLE OK：{len(pick)} 段（批次 {', '.join(f'{w}:{len(v)}' for w, v in sorted(by.items()))}）→ {md_p}")
    return 0


def rows(p, ncol):
    out = {}
    for l in p.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + [""] * ncol)[:ncol]]
            out[c[0]] = c
    return out


def lock(topic, what):
    p = D / f"ours-{topic}-{what}{sfx()}.tsv"
    R = rows(p, 3 if what == "c1" else 6)
    if what == "extra":
        p = D / f"ours-{topic}-extra{sfx()}.tsv"
        R = rows(p, 6)
    if what == "c1":
        bad = [k for k, c in R.items() if c[1] not in ("不矛盾", "矛盾") or (c[1] == "矛盾" and not c[2])]
    else:
        bad = [k for k, c in R.items() if any(x not in ("合格", "不合格") for x in c[1:5]) or ("不合格" in c[1:5] and not c[5])]
    if bad:
        print(f"LOCK ABORT：{p.name} 有空白或格式不對：{bad[:5]}")
        return 2
    log(f"ours-{what}-lock", p) if what != "extra" else log("ours-extra-lock", p)
    print(f"LOCK OK：{p.name}")
    return 0


def result(topic):
    of = D / f"ours-{topic}.tsv"
    c1p, sp = D / f"ours-{topic}-c1{sfx()}.tsv", D / f"ours-{topic}-sample{sfx()}.tsv"
    for p, w in ((c1p, "c1"), (sp, "sample")):
        lk = logged(f"ours-{w}-lock", p.name)
        if not lk or sha(p) != lk[-1]:
            print(f"RESULT ABORT：{p.name} 還沒鎖定或被改過")
            return 2
    sheet_sha = (logged(f"ours-sample-sheet{sfx()}", of.name) or [""])[-1]
    if sha(of) != sheet_sha:
        print("RESULT ABORT：ours 檔在抽樣之後被改過——要重新做 C1 與抽樣")
        return 2
    C = rows(c1p, 3)
    S = rows(sp, 6)
    key = json.loads((D / f"ours-{topic}-sample-key{sfx()}.json").read_text(encoding="utf-8"))
    c1bad = [k for k, c in C.items() if c[1] == "矛盾"]
    verdict = {}
    for w in sorted(set(key.values())):
        mine = [k for k in S if key[k] == w]
        s_c1 = [k for k in mine if S[k][1] == "不合格"]
        other = [k for k in mine if "不合格" in S[k][2:5]]
        if s_c1:
            verdict[w] = ("整批退回", f"抽樣裡 C1 不合格 {s_c1}（全量 C1 漏掉了）")
        elif len(other) >= 2:
            verdict[w] = ("整批退回", f"C2／C4／C5 不合格 {len(other)} 段：{other}")
        elif len(other) == 1:
            verdict[w] = ("只修那一段並加抽 8 段", f"{other}：{S[other[0]][5]}")
        else:
            verdict[w] = ("通過", "")
    print(f"C1 全量：{len(C)} 段，矛盾 {len(c1bad)}" + "".join(f"\n  矛盾 {k}：{C[k][2]}" for k in c1bad))
    for w, (v, why) in verdict.items():
        print(f"批次 {w}：{v}{'｜' + why if why else ''}")
    if not c1bad and all(v == "通過" for v, _ in verdict.values()):
        log("ours-pass", of)
        print(f"RESULT PASS：{of.name} 鎖定（之後改過，建置會擋）")
        return 0
    print("RESULT：還沒通過——照上面的處理（docs/M 第一節的規則），修完要重新做 C1 與抽樣")
    return 1


def extra(topic, batch):
    """docs/M：抽樣只有 1 段不合格 → 修那一段＋從同一批「還沒抽過的」再加抽 8 段（輪次用 RND；上一輪的抽樣排除）。"""
    md_p, tsv_p = D / f"ours-{topic}-extra{sfx()}.md", D / f"ours-{topic}-extra{sfx()}.tsv"
    if md_p.exists():
        print("EXTRA ABORT：已經加抽過")
        return 2
    prev = set()
    for r in range(max(1, RND - 1), RND):   # 只排除上一輪（同一份文字）抽過的；更早的輪次是重寫前的舊文字
        kf = D / f"ours-{topic}-sample-key{'' if r == 1 else f'-r{r}'}.json"
        if kf.exists():
            prev |= set(json.loads(kf.read_text(encoding="utf-8")))
    O, Q = ours(topic), qmap()
    pool = sorted(i for i, v in O.items() if v[0] == "說明" and v[2] == batch and i not in prev)
    pick = random.Random(SEED + 7000 + RND).sample(pool, min(8, len(pool)))
    md = ["# 「我們寫的」加抽複核", "", "每一段判四項（不要判「寫得對不對」——那沒有真值）：", CRIT, "",
          "每項填「合格」或「不合格」；有不合格要寫一句理由。只看這份單子。", ""]
    lines = ["題號\tC1\tC2\tC4\tC5\t理由"]
    for i in pick:
        md += [f"## {i}"] + block(Q[i], O[i][1])
        lines.append(f"{i}\t\t\t\t\t")
    md_p.write_text("\n".join(md), encoding="utf-8")
    tsv_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"ours-extra-sheet{sfx()}", D / f"ours-{topic}.tsv")
    print(f"EXTRA OK：批次 {batch} 還沒抽過的 {len(pool)} 段裡加抽 {len(pick)} 段 → {md_p}")
    return 0


def result_extra(topic):
    of, xp = D / f"ours-{topic}.tsv", D / f"ours-{topic}-extra{sfx()}.tsv"
    lk = logged(f"ours-extra-lock", xp.name)
    if not lk or sha(xp) != lk[-1] or sha(of) != (logged(f"ours-extra-sheet{sfx()}", of.name) or [""])[-1]:
        print("RESULT ABORT：加抽判斷檔還沒鎖定、被改過，或 ours 檔在加抽後被改過")
        return 2
    S = rows(xp, 6)
    bad = [k for k, c in S.items() if "不合格" in c[1:5]]
    if bad:
        print(f"RESULT：加抽 {len(S)} 段有不合格 {bad} → 整批退回（docs/M）")
        return 1
    log("ours-pass", of)
    print(f"RESULT PASS：加抽 {len(S)} 段全部合格；{of.name} 鎖定")
    return 0


def passed(topic):
    """建置用：ours 檔通過複核、而且之後沒被改過。"""
    of = D / f"ours-{topic}.tsv"
    lk = logged("ours-pass", of.name)
    return bool(lk) and of.exists() and sha(of) == lk[-1]


if __name__ == "__main__":
    a = sys.argv[1:] + ["", "", "", ""]
    # 最後一個參數可以是 r2、r3…（第幾輪）
    for x in list(a):
        if x[:1] == "r" and x[1:].isdigit():
            RND = int(x[1:])
            a.remove(x)
            a.append("")
    sys.exit({"c1": lambda: c1(a[1]), "sample": lambda: sample(a[1]), "lock": lambda: lock(a[1], a[2]), "result": lambda: result(a[1]), "extra": lambda: extra(a[1], a[2]), "result-extra": lambda: result_extra(a[1])}
             .get(a[0], lambda: (print(__doc__), 2)[1])())
