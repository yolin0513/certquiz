#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」重點整理第一階段：字面統計（方法見 docs/L 第 9 節，算之前寫定並提交 7f9e664）
-------------------------------------------------------------------------------
  python -u scripts/ethics_stats.py classify   題型分類＋抽驗尺樣本（每類 20 題，種子 20261013）→ 給另一個代理獨立判斷
  python -u scripts/ethics_stats.py lock       鎖定代理的判斷檔（雜湊入 data/local/sfi/log.tsv）
  python -u scripts/ethics_stats.py build      算統計、比對驗尺、產出 HTML（data/local/sfi/ethics-重點整理.html，只放本機）
所有門檻與口徑照 docs/L 第 9 節，寫在下面的常數裡；揭曉後不改。
"""
import hashlib
import html
import json
import random
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_sfi as I  # noqa: E402

D = I.OUT
LOG = D / "log.tsv"
SAMPLE_MD = D / "stats-ruler-sample.md"
JUDGE = D / "stats-ruler-judge.tsv"
KEY = D / "stats-ruler-key.json"
STATS = D / "ethics-stats.json"
HTML_OUT = D / "ethics-重點整理.html"
SEED = 20261013
PER_CLASS = 20
EXPECT = {"gen": 558, "eth": 616}          # 116 年版官方公告
RANK_MIN = 3                                # 「常常就是答案」「最常被拿來騙人」：該角色 ≥ 3 次
CROSS_MIN = 2                               # 交叉：當正解 ≥ 2 而且當誘答 ≥ 2
LIST_MIN = 3                                # 一份排行符合門檻的說法少於 3 個 → 數量不足
RATE_MIN = 10                               # 比例的分母少於 10 → 數量不足
TOP = 20
ROBUST_K, ROBUST_OK = 10, 0.8
RULER_ALL, RULER_EACH = 0.90, 0.85
NEG = re.compile(r"錯誤|不正確|有誤|不適當|不恰當|非正確|不妥")
POS = re.compile(r"正確|適當|恰當|為真|妥當")
GENERIC = re.compile(r"^(以上|上述|前述)|^(無法判斷|視情況而定|不一定|皆可|皆非|皆是|都是|都不是)$")
COMBO_STRIP = re.compile(r"[僅只有皆均與及和、，,\s()（）]")
COMBO = re.compile(r"^[A-Ea-e甲乙丙丁戊]+$")
CLS_NAME = {"neg": "反向敘述題（問哪個是錯的）", "pos": "正向敘述題（問哪個是對的）", "other": "其他（問名詞、數字、對象、行為）"}
PART = I.PART_NAME


def n1(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s", "", s)
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("P"))
    return s.lower()


def n2(s):
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", s))


def is_generic(opt):
    t = n2(opt)
    if GENERIC.search(t):
        return True
    c = COMBO_STRIP.sub("", t)
    return bool(c) and bool(COMBO.match(c))


def qtype(q):
    return "neg" if NEG.search(q["stem"]) else "pos" if POS.search(q["stem"]) else "other"


def load116():
    qs = []
    for part in ("gen", "eth"):
        qs += json.loads((D / f"ethics-116-{part}.json").read_text(encoding="utf-8"))["questions"]
    return qs


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def logged(action, name):
    if not LOG.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOG.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def classify():
    if KEY.exists():
        print("CLASSIFY ABORT：驗尺樣本已經抽過了")
        return 2
    qs = load116()
    rnd = random.Random(SEED)
    sample = []
    for c in ("neg", "pos", "other"):
        pool = sorted([q for q in qs if qtype(q) == c], key=lambda q: q["id"])
        sample += [(q, c) for q in rnd.sample(pool, min(PER_CLASS, len(pool)))]
    rnd.shuffle(sample)
    md = ["# 題型判斷（給獨立判斷者；看不到程式的分類）", "",
          "每題只看題幹，判斷題目在問什麼：", "- **對**：問「哪一個敘述／作法是對的、正確的、適當的」",
          "- **錯**：問「哪一個敘述／作法是錯的、不正確的、不適當的」", "- **其他**：問名詞、數字、對象、哪個機關、哪種行為等，不是在問敘述的對錯", ""]
    judge = ["編號\t判斷（對／錯／其他）"]
    key = []
    for n, (q, c) in enumerate(sample, 1):
        code = f"T{n:02d}"
        md += [f"## {code}", q["stem"], ""]
        judge.append(f"{code}\t")
        key.append({"code": code, "id": q["id"], "mine": c})
    D.mkdir(parents=True, exist_ok=True)
    SAMPLE_MD.write_text("\n".join(md), encoding="utf-8")
    JUDGE.write_text("\n".join(judge) + "\n", encoding="utf-8")
    KEY.write_text(json.dumps({"seed": SEED, "sample": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), SAMPLE_MD, JUDGE, KEY):
        log("stats-classify", p)
    cnt = {c: sum(1 for q in qs if qtype(q) == c) for c in CLS_NAME}
    print(f"CLASSIFY OK：抽了 {len(sample)} 題（每類最多 {PER_CLASS}）→ {SAMPLE_MD}；判斷檔 {JUDGE}｜全體分類 {cnt}")
    return 0


def judge_rows():
    out = {}
    for l in JUDGE.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + [""])[:2]]
            out[c[0]] = c[1]
    return out


def lock():
    if logged("stats-lock", JUDGE.name):
        print("LOCK ABORT：已經鎖定過")
        return 2
    bad = [k for k, v in judge_rows().items() if v not in ("對", "錯", "其他")]
    if bad:
        print(f"LOCK ABORT：判斷檔有空白或格式不對：{bad}")
        return 2
    log("stats-lock", JUDGE)
    print(f"LOCK OK：{JUDGE.name} {sha(JUDGE)[:12]}…")
    return 0


def ruler():
    lk = logged("stats-lock", JUDGE.name)
    if not lk or sha(JUDGE) != lk[-1]:
        return None
    key = json.loads(KEY.read_text(encoding="utf-8"))["sample"]
    J = judge_rows()
    m = {"對": "pos", "錯": "neg", "其他": "other"}
    per = {}
    for k in key:
        ok = m.get(J.get(k["code"])) == k["mine"]
        per.setdefault(k["mine"], []).append(ok)
    allv = [x for v in per.values() for x in v]
    res = {"overall": sum(allv) / len(allv), "per": {c: (sum(v) / len(v), len(v)) for c, v in per.items()},
           "disagree": [(k["code"], k["id"], k["mine"], J.get(k["code"])) for k in key if m.get(J.get(k["code"])) != k["mine"]]}
    res["pass"] = res["overall"] >= RULER_ALL and all(r >= RULER_EACH for r, _ in res["per"].values())
    return res


def tally(qs, norm):
    """回傳 {部分: {正規化後的說法: {'text', 'correct', 'distract', 'true', 'false'}}}，只算實質選項。"""
    out = {"gen": {}, "eth": {}}
    for q in qs:
        c = qtype(q)
        for k, o in enumerate(q["options"], 1):
            if is_generic(o):
                continue
            key = norm(o)
            r = out[q["part"]].setdefault(key, {"text": o, "correct": 0, "distract": 0, "true": 0, "false": 0, "qs": []})
            role = "correct" if k == q["answer"] else "distract"
            r[role] += 1
            r["qs"].append(q["no"])
            if c in ("pos", "neg"):
                truth = (c == "pos") == (role == "correct")
                r["true" if truth else "false"] += 1
    return out


def rank(table, field, minimum):
    rows = [dict(key=k, **v) for k, v in table.items() if v[field] >= minimum]
    rows.sort(key=lambda r: (-r[field], -(r["correct"] + r["distract"]), r["text"]))
    return rows


def robust(qs, field, minimum, part):
    a = [r["key"] for r in rank(tally(qs, n1)[part], field, minimum)][:ROBUST_K]
    b_rows = rank(tally(qs, n2)[part], field, minimum)[:ROBUST_K]
    b = {n1(r["text"]) for r in b_rows}
    if not a:
        return None
    return sum(1 for k in a if k in b) / len(a)


def build():
    qs = load116()
    n_q = {p: sum(1 for q in qs if q["part"] == p) for p in EXPECT}
    n_opt = sum(len(q["options"]) for q in qs)
    ok_pop = n_q == EXPECT and n_opt == 4 * sum(EXPECT.values()) and all(len(q["options"]) == 4 for q in qs)
    print(f"母體核對：讀到 常識 {n_q['gen']}／應該 {EXPECT['gen']}、道德 {n_q['eth']}／應該 {EXPECT['eth']}；選項 {n_opt}／應該 {4 * sum(EXPECT.values())}")
    if not ok_pop:
        print("STATS ABORT：母體不符，不寫檔")
        return 1
    rl = ruler()
    if rl is None:
        print("STATS ABORT：驗尺判斷檔還沒鎖定（或鎖定後被改過）")
        return 2
    print(f"驗尺（題型）：整體一致 {rl['overall']:.0%}；各類 " + "、".join(f"{CLS_NAME[c][:5]} {r:.0%}（{n} 題）" for c, (r, n) in rl["per"].items())
          + f" → {'過，呈現對／錯那一層' if rl['pass'] else '沒過，只呈現當正解／當誘答'}")
    T = tally(qs, n1)
    stats = {"population": {"questions": n_q, "options": n_opt}, "ruler": rl, "parts": {}}
    for part in ("gen", "eth"):
        pq = [q for q in qs if q["part"] == part]
        types = {c: sum(1 for q in pq if qtype(q) == c) for c in CLS_NAME}
        combo_q = sum(1 for q in pq if all(is_generic(o) and not GENERIC.search(n2(o)) for o in q["options"]))
        gen_q = sum(1 for q in pq if any(is_generic(o) for o in q["options"]))
        # 通用選項：每種出現幾次、當正解幾次
        generic = {}
        for q in pq:
            for k, o in enumerate(q["options"], 1):
                if is_generic(o):
                    g = generic.setdefault(n1(o), {"text": o, "n": 0, "correct": 0})
                    g["n"] += 1
                    g["correct"] += int(k == q["answer"])
        lists = {
            "answer": rank(T[part], "correct", RANK_MIN),
            "trap": rank(T[part], "distract", RANK_MIN),
            "cross": [r for r in T[part].values() if r["correct"] >= CROSS_MIN and r["distract"] >= CROSS_MIN],
        }
        if rl["pass"]:
            lists["false"] = rank(T[part], "false", RANK_MIN)
            lists["true"] = rank(T[part], "true", RANK_MIN)
            lists["cross_flip"] = [r for r in lists["cross"] if r["true"] >= 1 and r["false"] >= 1]
            lists["cross_same"] = [r for r in lists["cross"] if not (r["true"] >= 1 and r["false"] >= 1)]
        rob = {name: robust(qs, f, m, part) for name, f, m in (("answer", "correct", RANK_MIN), ("trap", "distract", RANK_MIN))}
        if rl["pass"]:
            rob["false"] = robust(qs, "false", RANK_MIN, part)
            rob["true"] = robust(qs, "true", RANK_MIN, part)
        stats["parts"][part] = {"n": len(pq), "types": types, "combo_q": combo_q, "generic_q": gen_q,
                                "generic": sorted(generic.values(), key=lambda g: -g["n"]),
                                "lists": {k: v for k, v in lists.items()}, "robust": rob,
                                "distinct": len(T[part]), "repeated": sum(1 for r in T[part].values() if r["correct"] + r["distract"] >= 2)}
        print(f"  {PART[part]}：{len(pq)} 題；題型 {types}；實質說法 {len(T[part])} 種、出現 ≥2 次的 {stats['parts'][part]['repeated']} 種；"
              + "；".join(f"{k} {len(v)} 個" for k, v in lists.items()) + f"；穩健性 {rob}")
    diff = json.loads((D / "ethics-diff.json").read_text(encoding="utf-8"))
    old = {p: {q["no"]: q for q in json.loads((D / f"ethics-113-{p}.json").read_text(encoding="utf-8"))["questions"]} for p in ("gen", "eth")}
    new = {p: {q["no"]: q for q in json.loads((D / f"ethics-116-{p}.json").read_text(encoding="utf-8"))["questions"]} for p in ("gen", "eth")}
    stats["diff"] = {p: {k: (len(v) if isinstance(v, list) else v) for k, v in diff[p].items()} for p in diff}
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    HTML_OUT.write_text(render(stats, diff, old, new), encoding="utf-8")
    print(f"STATS OK：{STATS}；HTML → {HTML_OUT}")
    return 0


# ---------------------------------------------------------------- HTML
def esc(s):
    return html.escape(str(s))


def pct(a, b):
    return f"{a / b:.0%}" if b else "—"


def render(st, diff, old, new):
    rl = st["ruler"]
    truth_ok = rl["pass"]
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    def table(rows, cols):
        if not rows:
            return ""
        head = "".join(f"<th>{esc(c[0])}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td{' class=num' if c[2] else ''}>{c[1](r)}</td>" for c in cols) + "</tr>" for r in rows[:TOP])
        more = f'<p class="muted">共 {len(rows)} 個，列前 {TOP} 個。</p>' if len(rows) > TOP else ""
        return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}'

    def ranked(rows, cols, robust_val, empty_text):
        if len(rows) < LIST_MIN:
            return f'<p class="insufficient">數量不足（符合門檻的有 {len(rows)} 個），不排名。</p>' if rows or empty_text is None else f'<p class="insufficient">{esc(empty_text)}</p>'
        rb = ""
        if robust_val is not None:
            rb = (f'<p class="muted">兩種口徑結果一致：主口徑前 {ROBUST_K} 名有 {robust_val:.0%} 也在穩健性口徑的前 {ROBUST_K} 名。</p>' if robust_val >= ROBUST_OK
                  else f'<p class="warn-line">口徑敏感，排名不可信：主口徑前 {ROBUST_K} 名只有 {robust_val:.0%} 在穩健性口徑的前 {ROBUST_K} 名。</p>')
        return table(rows, cols) + rb

    txt = ("說法", lambda r: esc(r["text"]), False)
    c_cor = ("當正解", lambda r: r["correct"], True)
    c_dis = ("當誘答", lambda r: r["distract"], True)
    c_t = ("是對的", lambda r: r["true"], True)
    c_f = ("是錯的", lambda r: r["false"], True)

    parts_html = []
    for part in ("gen", "eth"):
        P = st["parts"][part]
        L = P["lists"]
        rb = P["robust"]
        sec = [f'<section class="part" id="{part}"><h2>{esc(PART[part])}（{P["n"]} 題）</h2>']
        # 問題一
        sec.append('<h3>問題一：看到這句話，它通常是對的還是錯的？</h3>')
        if truth_ok:
            sec.append('<p class="lead">只算「問哪個對」「問哪個錯」的題目。反向題（問哪個錯）的正解是一句<b>錯的</b>敘述，這裡已經換算成對錯，不是「被選幾次」。</p>')
            sec.append('<h4>常常是「對的」敘述</h4>' + ranked(L["true"], [txt, c_t, c_f], rb.get("true"), None))
            sec.append('<h4>常常是「錯的」敘述</h4>' + ranked(L["false"], [txt, c_f, c_t], rb.get("false"), None))
        else:
            sec.append(f'<p class="warn-line">題型分類的驗尺沒有過（見最後一節），所以這裡不換算對錯，只列「當正解／當誘答」。注意：在問「哪個錯」的題目裡，正解是一句錯的敘述。</p>')
        sec.append('<h4>常常就是答案的說法（當正解 ≥ 3 次）</h4>' + ranked(L["answer"], [txt, c_cor, c_dis], rb.get("answer"), None))
        # 問題二
        sec.append('<h3>問題二：哪些說法最常被拿來騙人？</h3>')
        sec.append('<p class="lead">當誘答（錯誤選項）的次數。</p>' + ranked(L["trap"], [txt, c_dis, c_cor], rb.get("trap"), None))
        # 交叉
        sec.append('<h3>小心：「看到這句就選」會中陷阱的說法</h3>')
        sec.append(f'<p class="lead">同一句話，有時是正解、有時是誘答（各 ≥ {CROSS_MIN} 次）。背成「看到這句就選」會錯。</p>')
        if not L["cross"]:
            sec.append('<p class="insufficient">未發現：沒有說法同時當正解、當誘答各 2 次以上。</p>')
        elif truth_ok:
            sec.append('<h4>最危險：同一句話在不同題目裡對錯不一致</h4>' + (table(L["cross_flip"], [txt, c_cor, c_dis, c_t, c_f]) if L["cross_flip"] else '<p class="insufficient">未發現。</p>'))
            sec.append('<h4>對錯一致、只是題目問法不同（問哪個對時是正解，問哪個錯時變誘答）</h4>'
                       + (table(L["cross_same"], [txt, c_cor, c_dis, c_t, c_f]) if L["cross_same"] else '<p class="insufficient">未發現。</p>'))
        else:
            sec.append(table(L["cross"], [txt, c_cor, c_dis]))
        # 通用選項
        g = P["generic"]
        sec.append('<h3>「以上皆是」這類通用選項</h3><p class="lead">四選一的基準是 25%。這類選項不進上面的排行。</p>')
        if g:
            sec.append(table(g, [("選項", lambda r: esc(r["text"]), False), ("出現", lambda r: r["n"], True), ("當正解", lambda r: r["correct"], True),
                                 ("當正解的比例", lambda r: pct(r["correct"], r["n"]) if r["n"] >= RATE_MIN else "數量不足", True)]))
        else:
            sec.append('<p class="insufficient">這一部分沒有通用選項。</p>')
        sec.append("</section>")
        parts_html.append("".join(sec))

    # 題型分布
    rows = []
    for part in ("gen", "eth"):
        P = st["parts"][part]
        n = P["n"]
        rows.append(f"<tr><td>{esc(PART[part])}</td>" + "".join(f"<td class=num>{P['types'][c]}（{pct(P['types'][c], n)}）</td>" for c in ("pos", "neg", "other"))
                    + f"<td class=num>{P['combo_q']}（{pct(P['combo_q'], n)}）</td><td class=num>{P['generic_q']}（{pct(P['generic_q'], n)}）</td></tr>")
    types_html = ('<div class="tw"><table><thead><tr><th>部分</th><th>問哪個對</th><th>問哪個錯</th><th>其他</th><th>組合題</th><th>含通用選項</th></tr></thead><tbody>'
                  + "".join(rows) + "</tbody></table></div>")

    # 兩版差異
    def qblock(q, mark=None):
        opts = "".join(f'<li{" class=right" if k == q["answer"] else ""}>{esc(o)}{"<b>（正解）</b>" if k == q["answer"] else ""}</li>' for k, o in enumerate(q["options"], 1))
        return f'<div class="q"><p class="stem">{esc(q["stem"])}</p><ol class="opts">{opts}</ol></div>'
    dsec = []
    for part in ("gen", "eth"):
        d = diff[part]
        dsec.append(f'<h3>{esc(PART[part])}：相同 {len(d["same"])}、改過 {len(d["modified"])}、113 版刪除 {len(d["deleted"])}、116 版新增 {len(d["added"])}</h3>')
        chg = [m for m in d["modified"] if "正解" in m["changes"]]
        for m in chg:
            o, n = old[part][m["no113"]], new[part][m["no116"]]
            dsec.append(f'<div class="alert"><p class="alert-h">正解換了：116 年版第 {n["no"]} 題（113 年版第 {o["no"]} 題）</p>'
                        f'<p>照 113 年版背會答錯。113 年版的正解是 ({o["answer"]})「{esc(o["options"][o["answer"] - 1])}」；'
                        f'<b>116 年版改成 ({n["answer"]})「{esc(n["options"][n["answer"] - 1])}」</b>，考試以這個為準。</p>{qblock(n)}</div>')
        mods = "".join(f'<div class="pair"><p class="muted">116 年版第 {m["no116"]} 題（改了：{"、".join(m["changes"])}）</p>'
                       f'<p class="tag new">116 年版（考試範圍）</p>{qblock(new[part][m["no116"]])}<p class="tag old">113 年版（舊的，不要背）</p>{qblock(old[part][m["no113"]])}</div>'
                       for m in d["modified"])
        dsec.append(f'<details><summary>改過的 {len(d["modified"])} 題：新舊並排</summary>{mods}</details>')
        dsec.append(f'<details><summary>113 年版刪除的 {len(d["deleted"])} 題（不在 116 年考試範圍）</summary>' + "".join(qblock(old[part][no]) for no in d["deleted"]) + "</details>")
        dsec.append(f'<details><summary>116 年版新增的 {len(d["added"])} 題</summary>' + "".join(qblock(new[part][no]) for no in d["added"]) + "</details>")

    # 方法與限度
    per = "、".join(f"{CLS_NAME[c]} {r:.0%}（{n} 題）" for c, (r, n) in rl["per"].items())
    method = f"""
<ul>
<li>母體：116 年版題庫 {st['population']['questions']['gen']}＋{st['population']['questions']['eth']} 題、{st['population']['options']} 個選項；程式核對讀到的題數等於官方公告。113 年版不進統計。</li>
<li>只分「金融市場常識」「職業道德」兩部分：題庫 PDF 沒有章節標示，不能依官方章節分。</li>
<li>「同一個選項」：全形半形統一、去掉空白與標點後完全相同才算同一個（主口徑）；另用「保留標點」的口徑重算一次，比較兩者前 {ROBUST_K} 名的重疊（≥ {ROBUST_OK:.0%} 才寫「一致」）。</li>
<li>門檻：排行要該角色出現 ≥ {RANK_MIN} 次；交叉要當正解、當誘答各 ≥ {CROSS_MIN} 次；符合的少於 {LIST_MIN} 個就寫「數量不足」；比例的分母少於 {RATE_MIN} 寫「數量不足」。</li>
<li>題型（問哪個對／問哪個錯／其他）是程式依題幹關鍵字分的。驗尺：每類隨機抽題，請另一個判斷者在看不到程式分類的情況下獨立判斷，整體一致 {rl['overall']:.0%}；{per}。{'達到門檻（整體 ≥ 90%、每類 ≥ 85%），所以呈現「對／錯」。' if truth_ok else '沒達到門檻，所以不呈現「對／錯」，只呈現當正解／當誘答。'}</li>
<li>只看字面：同一個意思換個說法，不會被算成同一個。</li>
<li>這份方法在算之前就寫定並提交（專案文件 docs/L 第 9 節）。</li>
</ul>"""

    css = """
:root{--bg:#f7f8fa;--paper:#fff;--ink:#1b2430;--muted:#536071;--line:#d8dee6;--accent:#1f5a8a;--ok:#1d6b3a;--ok-bg:#e5f3ea;--ng:#a32a20;--ng-bg:#fbe7e5;--warn:#7a4b00;--warn-bg:#fbf0dc;
--f:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161c;--paper:#1a2129;--ink:#e6eaef;--muted:#a1adbb;--line:#2e3844;--accent:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn:#f0c779;--warn-bg:#33281a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161c;--paper:#1a2129;--ink:#e6eaef;--muted:#a1adbb;--line:#2e3844;--accent:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn:#f0c779;--warn-bg:#33281a;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 var(--f)}
main{max-width:760px;margin:0 auto;padding-inline:16px;padding-block:20px 48px}
h1{font-size:1.45rem;line-height:1.35;margin:0 0 6px;text-wrap:balance}
h2{font-size:1.2rem;margin:0 0 10px;text-wrap:balance}h3{font-size:1.05rem;margin:22px 0 8px}h4{font-size:.98rem;margin:16px 0 6px;color:var(--accent)}
p{margin:6px 0}.lead{color:var(--muted)}.muted{color:var(--muted);font-size:.9rem}
section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px;min-width:0}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:6px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.insufficient{color:var(--warn);background:var(--warn-bg);border-radius:8px;padding:8px 10px}
.warn-line{color:var(--ng);font-weight:600}
.alert{border:2px solid var(--ng);background:var(--ng-bg);border-radius:10px;padding:12px;margin:10px 0}.alert-h{font-weight:700;color:var(--ng);margin-top:0}
.q{border-top:1px dashed var(--line);padding-top:8px;margin-top:8px}.stem{margin:0 0 4px}.opts{margin:4px 0;padding-left:1.6em}
.opts li{margin:2px 0;padding:2px 6px;border-radius:6px}.opts li.right{background:var(--ok-bg);border:1px solid var(--ok)}
.pair{border-top:2px solid var(--line);padding-top:10px;margin-top:14px}.tag{display:inline-block;font-size:.8rem;padding:1px 8px;border-radius:999px;margin:6px 0 0}
.tag.new{background:var(--ok-bg);color:var(--ok)}.tag.old{background:var(--ng-bg);color:var(--ng)}
details{margin:10px 0}summary{cursor:pointer;font-weight:600;color:var(--accent);padding:6px 0}
.facts td:first-child{white-space:nowrap;color:var(--muted)}
nav a{color:var(--accent)}nav{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.92rem}
.keynote{border-left:4px solid var(--accent);padding-left:10px}
"""
    facts = [("考試", "金融市場常識與職業道德（共同科目）"), ("題數／時間", "一百題，四選一單選，六十分鐘"), ("配分", "金融市場常識 50%、職業道德 50%"),
             ("及格", "七十分；成績保留五年"), ("報名費", "300 元（2027 年 1 月 1 日起；2026 年底前的場次是 250 元）"),
             ("考試範圍", "116 年版題庫（1,174 題），2027 年 1 月 1 日起適用"),
             ("應試方式", "證基會網頁寫「單科筆試」，報名網站幾乎天天有筆試場次；研訓院網頁另有電腦應試選項。兩邊說法不一，建議打電話確認：證基會測驗中心 02-2357-4388")]
    facts_html = '<div class="tw"><table class="facts"><tbody>' + "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in facts) + "</tbody></table></div>"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><title>金融常識與道德重點整理</title><style>{css}</style></head><body><main>
<h1>金融市場常識與職業道德・重點整理</h1>
<p class="muted">依證基會公告的 116 年版題庫（2027 年 1 月 1 日起適用）由程式算出；產生時間 {esc(gen_at)}。只放在你自己的裝置，不要轉貼。</p>
<nav><a href="#how">怎麼讀</a><a href="#facts">考試怎麼考</a><a href="#scope">各科範圍</a><a href="#types">題型</a><a href="#gen">金融市場常識</a><a href="#eth">職業道德</a><a href="#diff">兩版差異</a><a href="#method">方法與限度</a></nav>
<section id="how"><h2>這份怎麼讀</h2>
<p class="keynote">每一節都在回答一個問題：「看到這句話，它通常是對的還是錯的？」「哪些說法最常被拿來騙人？」數字是這句話在 116 年版題庫裡出現的次數。</p>
<p>題庫只有字面統計：同一個意思換個說法，不會算在一起。所以「沒出現在排行裡」不代表不重要，只代表這句話沒有<b>一字不差</b>地重複出現很多次。</p>
<p>這裡不逐題解釋為什麼選那個答案；答案以官方題庫為準。</p></section>
<section id="facts"><h2>考試怎麼考</h2>{facts_html}
<p class="muted">以上手抄自證基會「測驗方式及內容」「測驗費用」「題庫下載區」與台灣金融研訓院證照頁（2026-10-12 查）。</p>
<p class="warn-line">考題是否全部出自公告題庫：在已檢索範圍內未見明文，官方只寫「據此作為辦理依據」。請不要當成保證。</p></section>
<section id="scope"><h2>各科範圍（官方）</h2>
<p><b>金融市場常識（50%）</b>：金融體系、證券期貨市場、銀行實務、信託實務、貨幣市場實務、保險實務</p>
<p><b>職業道德（50%）</b>：業務推廣與招攬、受託執行業務、告知義務與通知、誠實信用原則、有關利益衝突、保密原則、遵守法律規範與自律</p>
<p class="muted">題庫 PDF 沒有標每題屬於哪一章，所以下面的統計只分這兩部分。</p></section>
<section id="types"><h2>各科常見的題型</h2>{types_html}
<p class="muted">「問哪個錯」的題目，正解是一句錯的敘述——背答案時要看清楚題目問的是對還是錯。</p></section>
{''.join(parts_html)}
<section id="diff"><h2>兩版差異（113 年版 → 116 年版）</h2>
<p class="lead">練 113 年版會學到錯東西的，就是這一批：被刪掉的題、被改過的題。考試範圍是 116 年版。</p>{''.join(dsec)}</section>
<section id="method"><h2>方法與限度</h2>{method}</section>
</main></body></html>"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"classify": classify, "lock": lock, "build": build}.get(cmd, lambda: (print("用法：classify｜lock｜build"), 2)[1])())
