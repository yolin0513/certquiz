#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「金融市場常識與職業道德」重點整理第一階段：字面統計（方法見 docs/L 第 9 節，算之前寫定並提交 7f9e664）
-------------------------------------------------------------------------------
  python -u scripts/ethics_stats.py classify   題型分類＋抽驗尺樣本（每類 20 題，種子 20261013）→ 給另一個代理獨立判斷
  python -u scripts/ethics_stats.py lock       鎖定代理的判斷檔（雜湊入 data/local/sfi/log.tsv）
  python -u scripts/ethics_stats.py build      算統計、比對驗尺、產出 HTML（data/local/sfi/ethics-重點整理.html，只放本機）
所有門檻與口徑照 docs/L 第 9 節，寫在下面的常數裡；揭曉後不改。

第二輪（docs/L 第 11 節，算之前寫定並提交 638c60c）：
  python -u scripts/ethics_stats.py classify2  題型分類 v2（只看題幹最後一句）＋全新驗尺樣本（排除第一輪 60 題，每類 20 題，種子 20261014）
  python -u scripts/ethics_stats.py lock2      鎖定新代理的判斷檔
  python -u scripts/ethics_stats.py build 2    用 v2 分類與通用選項 v2 重算；組合型修正前後比較；驗尺 v2 過才呈現「對／錯」
第一輪的規則（qtype1、is_generic1）保留不覆蓋。

第三輪（最後一輪；docs/L 第 13 節的規格，算之前寫定並提交 3731921）：
  python -u scripts/ethics_stats.py classify3 / lock3 / build 3
  程式與判斷說明都只從同一份規格實作；判斷說明直接引用規格原文。量到的是「關鍵字有沒有忠實反映規格」，不是「規格本身對不對」。
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
# 事後補充（2026-10-12，看到排行之後才發現；**不改計數、不改口徑**，只在畫面上標註）：
# 事先定的通用選項規則沒抓到「A.、B.都正確」「只 A.正確」「(1)及(2)」這類組合型寫法，它們混進了實質選項的排行。
POSTHOC_COMBO = re.compile(r"(都|皆|均)(不?正確|錯誤)$|^只?[A-Ea-e]\.?(正確|錯誤)$|^\(\d\)(及|、|與|和)\(\d\)")
# ---- 第二輪（docs/L 第 11 節）
SEED2 = 20261014
SAMPLE2_MD = D / "stats-ruler2-sample.md"
JUDGE2 = D / "stats-ruler2-judge.tsv"
KEY2 = D / "stats-ruler2-key.json"
ROUND1_STATS = D / "ethics-stats-round1.json"
ROUND2_STATS = D / "ethics-stats-round2.json"
DIAG3 = D / "stats-ruler3-diagnosis.txt"   # 揭曉後看不一致的題寫的原因說明（只是說明，不改任何口徑或門檻）
NEG2 = re.compile(r"錯誤|不正確|有誤|不適當|不恰當|非正確|不妥|為非|何者非|不是|並非|非屬|不屬|不包括|不包含|不得|不可|不宜|不應|不能|除外|不符|不需|無關|違反")
POS2 = re.compile(r"正確|適當|恰當|為真|妥當|合宜|妥適")
LAST_CLAUSE = re.compile(r"[，,；;：:。]")
COMBO_FIX_OK = 0.8
# ---- 第三輪（docs/L 第 13 節的規格）
SEED3 = 20261015
SAMPLE3_MD = D / "stats-ruler3-sample.md"
JUDGE3 = D / "stats-ruler3-judge.tsv"
KEY3 = D / "stats-ruler3-key.json"
R3_DO = re.compile(r"應如何|應採取?何種|如何處理|如何辦理|如何應對")
R3_NEG = re.compile(r"錯誤|錯的|不正確|有誤|不適當|不恰當|不妥|不當|違反|違規|為非[？?]?$|何者非[？?]?$|不得(有|從事|為)|不可(為|從事)")
R3_POS = re.compile(r"正確|適當|恰當|為真|妥當|合宜|妥適")
R3_MEMBER = re.compile(r"不是|並非|非屬|不屬於?|屬於|不包括|包括|不包含|包含|是下列")
SPEC3 = """看題目**最後在問的那一句**，依下面的順序，第一個符合的就是答案：

1. **問「該怎麼做」→ 對**：題目問應如何處理、應如何辦理、應如何應對、應採何種方式等「正確的做法」。即使前文出現「不正確」，只要最後問的是該怎麼做，就算這一類。
2. **問「哪個是錯的」→ 錯**：題目明確要你找出錯誤、不正確、不適當、不當、違反規定、不得從事、不可為的那一個。「下列何者為非？」這種只問對錯、沒有後接類別名稱的，也算這一類。
3. **問「哪個是對的」→ 對**：題目明確要你找出正確、適當、恰當、妥當的那一個。
4. **問「屬不屬於某一類」→ 屬類**：題目問哪一個是／不是、屬於／不屬於、包括／不包括某個**有名稱的類別**（例：何者不是基金銷售機構、何者非屬專業銀行、何者屬於間接授信）。
5. **其他**：問名詞、數字、期間、金額、機關、人等，不屬於上面四類。"""
CLS_NAME = {"neg": "反向敘述題（問哪個是錯的）", "pos": "正向敘述題（問哪個是對的）", "other": "其他（問名詞、數字、對象、行為）"}
CLS_NAME3 = {"pos": "問對（含問該怎麼做）", "neg": "問錯", "member": "問屬不屬於某一類", "other": "其他"}
PART = I.PART_NAME


def n1(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s", "", s)
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("P"))
    return s.lower()


def n2(s):
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", s))


def is_generic1(opt):
    t = n2(opt)
    if GENERIC.search(t):
        return True
    c = COMBO_STRIP.sub("", t)
    return bool(c) and bool(COMBO.match(c))


def qtype1(q):
    return "neg" if NEG.search(q["stem"]) else "pos" if POS.search(q["stem"]) else "other"


def is_generic2(opt):
    """第一輪的規則，加上事後發現的組合型寫法（docs/L 第 11 節）。"""
    return is_generic1(opt) or bool(POSTHOC_COMBO.search(n2(opt)))


def qtype2(q):
    """只看題幹最後一句（最後一個，；：。之後）；最後一句沒有關鍵字才看整個題幹。先判反向。"""
    stem = q["stem"]
    last = LAST_CLAUSE.split(stem.rstrip("？?"))[-1]
    for text in (last, stem):
        if NEG2.search(text):
            return "neg"
        if POS2.search(text):
            return "pos"
    return "other"


def qtype3(q):
    """docs/L 第 13 節規格的關鍵字實作：看最後一句（沒有關鍵字才看整個題幹）；依序 該怎麼做→錯→對→屬類→其他。"""
    stem = q["stem"]
    last = LAST_CLAUSE.split(stem.rstrip("？?"))[-1]
    for text in (last, stem):
        if R3_DO.search(text):
            return "pos"
        if R3_NEG.search(text):
            return "neg"
        if R3_POS.search(text):
            return "pos"
        if R3_MEMBER.search(text):
            return "member"
    return "other"


# 目前用哪一版（build 2 時換成第二輪）
qtype, is_generic = qtype1, is_generic1


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


def classify2():
    if KEY2.exists():
        print("CLASSIFY2 ABORT：第二輪驗尺樣本已經抽過了")
        return 2
    seen = {k["id"] for k in json.loads(KEY.read_text(encoding="utf-8"))["sample"]}
    qs = [q for q in load116() if q["id"] not in seen]   # 全部用沒看過的題
    rnd = random.Random(SEED2)
    sample = []
    for c in ("neg", "pos", "other"):
        pool = sorted([q for q in qs if qtype2(q) == c], key=lambda q: q["id"])
        sample += [(q, c) for q in rnd.sample(pool, min(PER_CLASS, len(pool)))]
    rnd.shuffle(sample)
    # 判斷說明跟第一輪一字不改
    md = SAMPLE_MD.read_text(encoding="utf-8").split("\n## T01")[0].rstrip("\n").split("\n") + [""]
    judge, key = ["編號\t判斷（對／錯／其他）"], []
    for n, (q, c) in enumerate(sample, 1):
        code = f"T{n:02d}"
        md += [f"## {code}", q["stem"], ""]
        judge.append(f"{code}\t")
        key.append({"code": code, "id": q["id"], "mine": c})
    SAMPLE2_MD.write_text("\n".join(md), encoding="utf-8")
    JUDGE2.write_text("\n".join(judge) + "\n", encoding="utf-8")
    KEY2.write_text(json.dumps({"seed": SEED2, "excluded_round1": len(seen), "sample": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), SAMPLE2_MD, JUDGE2, KEY2):
        log("stats2-classify", p)
    allq = load116()
    cnt = {c: sum(1 for q in allq if qtype2(q) == c) for c in CLS_NAME}
    overlap = sum(1 for q, _ in sample if q["id"] in seen)
    print(f"CLASSIFY2 OK：抽了 {len(sample)} 題（排除第一輪 {len(seen)} 題；樣本與第一輪重疊 {overlap} 題）→ {SAMPLE2_MD}｜v2 全體分類 {cnt}")
    return 0


def classify3():
    if KEY3.exists():
        print("CLASSIFY3 ABORT：第三輪驗尺樣本已經抽過了")
        return 2
    seen = {k["id"] for k in json.loads(KEY.read_text(encoding="utf-8"))["sample"]} | {k["id"] for k in json.loads(KEY2.read_text(encoding="utf-8"))["sample"]}
    qs = [q for q in load116() if q["id"] not in seen]
    rnd = random.Random(SEED3)
    sample = []
    for c in CLS_NAME3:
        pool = sorted([q for q in qs if qtype3(q) == c], key=lambda q: q["id"])
        sample += [(q, c) for q in rnd.sample(pool, min(PER_CLASS, len(pool)))]
    rnd.shuffle(sample)
    md = ["# 題型判斷（給獨立判斷者；看不到程式的分類）", "", "每題只看題幹，照下面的規格判斷（規格原文）：", "", SPEC3, "",
          "判斷寫成四個字之一：**對**（第 1 或第 3 類）、**錯**（第 2 類）、**屬類**（第 4 類）、**其他**（第 5 類）。", ""]
    judge, key = ["編號\t判斷（對／錯／屬類／其他）"], []
    for n, (q, c) in enumerate(sample, 1):
        code = f"T{n:02d}"
        md += [f"## {code}", q["stem"], ""]
        judge.append(f"{code}\t")
        key.append({"code": code, "id": q["id"], "mine": c})
    SAMPLE3_MD.write_text("\n".join(md), encoding="utf-8")
    JUDGE3.write_text("\n".join(judge) + "\n", encoding="utf-8")
    KEY3.write_text(json.dumps({"seed": SEED3, "excluded": len(seen), "sample": key}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), SAMPLE3_MD, JUDGE3, KEY3):
        log("stats3-classify", p)
    allq = load116()
    cnt = {c: sum(1 for q in allq if qtype3(q) == c) for c in CLS_NAME3}
    overlap = sum(1 for q, _ in sample if q["id"] in seen)
    print(f"CLASSIFY3 OK：抽了 {len(sample)} 題（排除前兩輪 {len(seen)} 題；重疊 {overlap} 題）→ {SAMPLE3_MD}｜v3 全體分類 {cnt}")
    return 0


def lock3():
    if logged("stats3-lock", JUDGE3.name):
        print("LOCK3 ABORT：已經鎖定過")
        return 2
    bad = [k for k, v in judge_rows(JUDGE3).items() if v not in ("對", "錯", "屬類", "其他")]
    if bad:
        print(f"LOCK3 ABORT：判斷檔有空白或格式不對：{bad}")
        return 2
    log("stats3-lock", JUDGE3)
    print(f"LOCK3 OK：{JUDGE3.name} {sha(JUDGE3)[:12]}…")
    return 0


def judge_rows(path=None):
    out = {}
    for l in (path or JUDGE).read_text(encoding="utf-8").splitlines()[1:]:
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


def lock2():
    if logged("stats2-lock", JUDGE2.name):
        print("LOCK2 ABORT：已經鎖定過")
        return 2
    bad = [k for k, v in judge_rows(JUDGE2).items() if v not in ("對", "錯", "其他")]
    if bad:
        print(f"LOCK2 ABORT：判斷檔有空白或格式不對：{bad}")
        return 2
    log("stats2-lock", JUDGE2)
    print(f"LOCK2 OK：{JUDGE2.name} {sha(JUDGE2)[:12]}…")
    return 0


def ruler(round_=1):
    judge, keyf, act = {1: (JUDGE, KEY, "stats-lock"), 2: (JUDGE2, KEY2, "stats2-lock"), 3: (JUDGE3, KEY3, "stats3-lock")}[round_]
    lk = logged(act, judge.name)
    if not lk or sha(judge) != lk[-1]:
        return None
    key = json.loads(keyf.read_text(encoding="utf-8"))["sample"]
    J = judge_rows(judge)
    m = {"對": "pos", "錯": "neg", "屬類": "member", "其他": "other"}
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
    global qtype, is_generic
    round_ = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] in ("2", "3") else 1
    if round_ == 2:
        qtype, is_generic = qtype2, is_generic2
    if round_ == 3:
        qtype, is_generic = qtype3, is_generic2
    qs = load116()
    n_q = {p: sum(1 for q in qs if q["part"] == p) for p in EXPECT}
    n_opt = sum(len(q["options"]) for q in qs)
    ok_pop = n_q == EXPECT and n_opt == 4 * sum(EXPECT.values()) and all(len(q["options"]) == 4 for q in qs)
    print(f"母體核對：讀到 常識 {n_q['gen']}／應該 {EXPECT['gen']}、道德 {n_q['eth']}／應該 {EXPECT['eth']}；選項 {n_opt}／應該 {4 * sum(EXPECT.values())}")
    if not ok_pop:
        print("STATS ABORT：母體不符，不寫檔")
        return 1
    rl = ruler(round_)
    if rl is None:
        print("STATS ABORT：驗尺判斷檔還沒鎖定（或鎖定後被改過）")
        return 2
    info_r1 = None
    if round_ == 2:   # 第三輪的類別跟前兩輪不同（多了屬類），不做這個參考比對
        # 參考資訊（不計入驗尺）：第一輪那 60 題用 v2 重分，跟第一輪判斷者一致的比例
        k1 = json.loads(KEY.read_text(encoding="utf-8"))["sample"]
        J1 = judge_rows(JUDGE)
        byid = {q["id"]: q for q in qs}
        m = {"對": "pos", "錯": "neg", "其他": "other"}
        hit = sum(1 for k in k1 if m.get(J1.get(k["code"])) == qtype2(byid[k["id"]]))
        info_r1 = {"agree": hit / len(k1), "n": len(k1)}
        print(f"參考（不計入驗尺）：第一輪 60 題用 v2 重分，跟第一輪判斷者一致 {info_r1['agree']:.0%}")
    names = CLS_NAME3 if round_ == 3 else CLS_NAME
    print(f"驗尺（題型）：整體一致 {rl['overall']:.0%}；各類 " + "、".join(f"{names[c][:6]} {r:.0%}（{n} 題）" for c, (r, n) in rl["per"].items())
          + f" → {'過，呈現對／錯那一層' if rl['pass'] else '沒過，只呈現當正解／當誘答'}")
    T = tally(qs, n1)
    stats = {"round": round_, "population": {"questions": n_q, "options": n_opt}, "ruler": rl, "ruler_r1_info": info_r1, "parts": {}}
    if round_ >= 2:
        # 組合型選項修正前後：v1 與 v2 的「當正解」「當誘答」排行前 10 名重疊
        cmp = {}
        for part in ("gen", "eth"):
            for name, field in (("answer", "correct"), ("trap", "distract")):
                tops = []
                for g in (is_generic1, is_generic2):
                    is_generic = g
                    tops.append([r["key"] for r in rank(tally(qs, n1)[part], field, RANK_MIN)][:ROBUST_K])
                is_generic = is_generic2
                cmp[f"{part}-{name}"] = sum(1 for k in tops[0] if k in tops[1]) / len(tops[0]) if tops[0] else None
        stats["combo_cmp"] = cmp
        print("組合型選項修正前後（v1 前 10 名有幾成仍在 v2 前 10 名）：" + "、".join(f"{k} {v:.0%}" if v is not None else f"{k} —" for k, v in cmp.items()))
        T = tally(qs, n1)
    for part in ("gen", "eth"):
        pq = [q for q in qs if q["part"] == part]
        types = {c: sum(1 for q in pq if qtype(q) == c) for c in (CLS_NAME3 if round_ == 3 else CLS_NAME)}
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
    if round_ >= 2 and ROUND1_STATS.exists():
        stats["round1"] = {k: json.loads(ROUND1_STATS.read_text(encoding="utf-8"))[k] for k in ("ruler",)}
    if round_ == 3:
        if ROUND2_STATS.exists():
            stats["round2"] = {k: json.loads(ROUND2_STATS.read_text(encoding="utf-8"))[k] for k in ("ruler", "ruler_r1_info")}
        pairs = {}
        for _, _, mine, theirs in rl["disagree"]:
            k = f"{mine}→{theirs}"
            pairs[k] = pairs.get(k, 0) + 1
        stats["disagree_pairs"] = sorted(pairs.items(), key=lambda kv: -kv[1])
        stats["diagnosis"] = DIAG3.read_text(encoding="utf-8").strip() if DIAG3.exists() else ""
        print("不一致的配對（程式→判斷者）：" + "、".join(f"{k} {v}" for k, v in stats["disagree_pairs"]))
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

    def label(r):
        t = esc(r["text"])
        if POSTHOC_COMBO.search(n2(r["text"])):
            t += '<span class="posthoc">（事後才發現是組合型選項：事先定的規則沒抓到，看的時候略過）</span>'
        return t
    txt = ("說法", label, False)
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
            if st.get("round") == 3:
                sec.append('<p class="warn-line">這一層比下面的「當正解／當誘答」弱：題型分類過了驗尺，但驗尺量到的是「程式有沒有照規格分」，不是「規格本身分得對不對」；'
                           '規格對不對沒有外部真值。「當正解／當誘答」是直接數出來的，不靠任何分類。</p>')
            sec.append('<p class="lead">只算「問哪個對」「問哪個錯」（含「應如何處理」）的題目；「屬不屬於某一類」與「其他」不換算。反向題（問哪個錯）的正解是一句<b>錯的</b>敘述，這裡已經換算成對錯，不是「被選幾次」。'
                       '題目問「何者不是／不得」時，選項常是名詞或行為，這裡的「對／錯」就是「屬於／不屬於題目問的那一類」「可以做／不能做」。</p>')
            sec.append('<h4>常常是「對的」敘述</h4>' + ranked(L["true"], [txt, c_t, c_f], rb.get("true"), None))
            sec.append('<h4>常常是「錯的」敘述</h4>' + ranked(L["false"], [txt, c_f, c_t], rb.get("false"), None))
        else:
            if st.get("round") == 3:
                sec.append('<p class="warn-line">這份重點整理答不了這個問題（原因見最上面「答不了的問題」那一節）。下面只列「當正解／當誘答」。注意：在問「哪個錯」的題目裡，正解是一句錯的敘述。</p>')
            else:
                sec.append(f'<p class="warn-line">這個問題這一輪也答不了：題型分類的驗尺{"兩輪都" if st.get("round") == 2 else ""}沒有過（見最後一節），所以這裡不換算對錯，只列「當正解／當誘答」。注意：在問「哪個錯」的題目裡，正解是一句錯的敘述。</p>')
        cc = st.get("combo_cmp", {})
        def downgrade(name):
            v = cc.get(f"{part}-{name}")
            return (f'<p class="warn-line">第一階段的這份排行受組合型選項影響很大（修正前後前 {ROBUST_K} 名只重疊 {v:.0%}），那一版的可信度要降一級；以這裡的為準。</p>'
                    if v is not None and v < COMBO_FIX_OK else "")
        sec.append(downgrade("answer"))
        sec.append('<h4>常常就是答案的說法（當正解 ≥ 3 次）</h4>'
                   + '<p class="warn-line">「當正解」是「被選為答案」，不是「這句話是對的」：題目如果問「何者錯誤」「何者不得」「何者為非」，'
                   + '被選的那句反而是錯的、或是不能做的事。背的時候要連題目一起看，不要只背這句話。</p>'
                   + ranked(L["answer"], [txt, c_cor, c_dis], rb.get("answer"), None))
        # 問題二
        sec.append('<h3>問題二：哪些說法最常被拿來騙人？</h3>')
        sec.append(downgrade("trap"))
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
        ya = next((x for x in g if n1(x["text"]) == "以上皆是"), None)
        if ya and ya["n"] >= RATE_MIN:
            miss = ya["n"] - ya["correct"]
            sec.append(f'<p class="warn-line">「以上皆是」出現 {ya["n"]} 次、{pct(ya["correct"], ya["n"])} 是正解——另一面是 {pct(miss, ya["n"])} 不是，'
                       f'也就是 {miss} 題。可以當傾向，不能當規則：拿不準時才用它偏向，看得懂題目時以內容為準。養成「看到以上皆是就選」的反射，這 {miss} 題會穩定地答錯。</p>')
        if g:
            sec.append(table(g, [("選項", lambda r: esc(r["text"]), False), ("出現", lambda r: r["n"], True), ("當正解", lambda r: r["correct"], True),
                                 ("當正解的比例", lambda r: pct(r["correct"], r["n"]) if r["n"] >= RATE_MIN else "數量不足", True)]))
        else:
            sec.append('<p class="insufficient">這一部分沒有通用選項。</p>')
        sec.append("</section>")
        parts_html.append("".join(sec))

    # 題型分布
    rows = []
    tcols = ("pos", "neg", "member", "other") if st.get("round") == 3 else ("pos", "neg", "other")
    for part in ("gen", "eth"):
        P = st["parts"][part]
        n = P["n"]
        rows.append(f"<tr><td>{esc(PART[part])}</td>" + "".join(f"<td class=num>{P['types'][c]}（{pct(P['types'][c], n)}）</td>" for c in tcols)
                    + f"<td class=num>{P['combo_q']}（{pct(P['combo_q'], n)}）</td><td class=num>{P['generic_q']}（{pct(P['generic_q'], n)}）</td></tr>")
    th = {"pos": "問哪個對", "neg": "問哪個錯", "member": "屬不屬於某類", "other": "其他"}
    types_html = ('<div class="tw"><table><thead><tr><th>部分</th>' + "".join(f"<th>{th[c]}</th>" for c in tcols) + '<th>組合題</th><th>含通用選項</th></tr></thead><tbody>'
                  + "".join(rows) + "</tbody></table></div>")
    if st.get("round") == 3:
        types_html += '<p class="muted">題型是程式照同一份規格、依題幹關鍵字分的；「問哪個對」含「應如何處理」這類問做法的題。</p>'
        if not truth_ok:
            types_html += '<p class="warn-line">這個分類沒過驗尺，數字只當參考。</p>' 

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
    names = CLS_NAME3 if st.get("round") == 3 else CLS_NAME
    per = "、".join(f"{names[c]} {r:.0%}（{n} 題）" for c, (r, n) in rl["per"].items())
    r2 = ""
    if st.get("round") == 2:
        r1 = st.get("round1", {}).get("ruler")
        info = st.get("ruler_r1_info") or {}
        r1txt = (f"第一輪：整體 {r1['overall']:.0%}，其他那一類 {r1['per'].get('other', [0])[0]:.0%}，沒過。" if r1 else "")
        cmp = st.get("combo_cmp", {})
        r2 = (f"<li><b>這是第二輪</b>。{r1txt}第二輪把題型分類改成只看題幹最後一句、補上「非、不得、不是」等關鍵字，並用<b>全部沒看過的題</b>重新驗尺（排除第一輪 60 題）。"
              f"第一輪那 60 題用新規則重分，跟第一輪判斷者一致 {info.get('agree', 0):.0%}——只當參考，不計入，因為拿已知的失敗樣本驗自己的修法一定會過。</li>"
              "<li>組合型選項的規則補上了「都正確／只 A.正確／(1)及(2)」這類寫法。修正前後排行前 " + str(ROBUST_K) + " 名的重疊："
              + "、".join(f"{PART[k.split('-')[0]]}{'常是答案' if k.endswith('answer') else '常被拿來騙人'} {v:.0%}" for k, v in cmp.items() if v is not None) + "。</li>")
    why_not = ("<li><b>為什麼不呈現對／錯</b>：題型分類只靠關鍵字，抓不到「下列何者為非」「不得有下列何種情事」這類寫法，也會把「不慎作出不正確之解釋，應如何正確處理？」誤判成問哪個錯。"
               f"驗尺因此在「其他」那一類只有 {rl['per'].get('other', (0, 0))[0]:.0%}，低於事先定的 85%。</li>") if st.get("round") == 1 else ""
    limit3 = ""
    if st.get("round") == 3:
        r1 = (st.get("round1") or {}).get("ruler")
        r2r = (st.get("round2") or {}).get("ruler")
        info = (st.get("round2") or {}).get("ruler_r1_info") or {}
        hist = []
        if r1:
            hist.append(f"第一輪 整體 {r1['overall']:.0%}（沒過）")
        if r2r:
            hist.append(f"第二輪 整體 {r2r['overall']:.0%}（沒過）")
        hist.append(f"第三輪 整體 {rl['overall']:.0%}（{'過' if truth_ok else '沒過'}）")
        r2 = ("<li><b>這是第三輪，也是最後一輪</b>。" + "；".join(hist) + "。第三輪先把題型寫成一份規格（五類、有先後順序），程式的關鍵字與判斷者的說明都只照那一份規格各自實作；"
              "判斷者的說明直接引用規格原文。樣本是前兩輪都沒看過的題。</li>"
              f"<li><b>為什麼一律用沒看過的題驗</b>：第二輪的修法拿第一輪已知的失敗樣本重驗，一致 {info.get('agree', 0.88):.0%}；換成沒看過的題只有 {r2r['overall'] if r2r else 0.68:.0%}。"
              "差距全部來自樣本有沒有被看過。</li>")
        limit3 = ("<li><b>這一輪量到的是什麼</b>：兩邊都照同一份規格之後，一致率衡量的是「程式的關鍵字有沒有忠實反映規格」，不是「規格本身分得對不對」。"
                  "規格對不對沒有外部真值，只能靠人判斷。所以就算過了，「對／錯」這一層的結論強度也低於「當正解／當誘答」那一層。</li>")
    method = f"""
<ul>
{r2}
{limit3}
<li>母體：116 年版題庫 {st['population']['questions']['gen']}＋{st['population']['questions']['eth']} 題、{st['population']['options']} 個選項；程式核對讀到的題數等於官方公告。113 年版不進統計。</li>
<li>只分「金融市場常識」「職業道德」兩部分：題庫 PDF 沒有章節標示，不能依官方章節分。</li>
<li>「同一個選項」：全形半形統一、去掉空白與標點後完全相同才算同一個（主口徑）；另用「保留標點」的口徑重算一次，比較兩者前 {ROBUST_K} 名的重疊（≥ {ROBUST_OK:.0%} 才寫「一致」）。</li>
<li>門檻：排行要該角色出現 ≥ {RANK_MIN} 次；交叉要當正解、當誘答各 ≥ {CROSS_MIN} 次；符合的少於 {LIST_MIN} 個就寫「數量不足」；比例的分母少於 {RATE_MIN} 寫「數量不足」。</li>
<li>題型（{"／".join(names.values())}）是程式依題幹關鍵字分的。驗尺：每類隨機抽題，請另一個判斷者在看不到程式分類的情況下獨立判斷，整體一致 {rl['overall']:.0%}；{per}。{'達到門檻（整體 ≥ 90%、每類 ≥ 85%），所以呈現「對／錯」。' if truth_ok else '沒達到門檻，所以不呈現「對／錯」，只呈現當正解／當誘答。'}</li>
<li>只看字面：同一個意思換個說法，不會被算成同一個。</li>
<li><b>事後發現的漏洞</b>：事先定的「通用選項」規則沒抓到「A.、B.都正確」「只 A.正確」「(1)及(2)」這類組合型寫法，所以它們混進了上面的排行。照「揭曉後不改口徑」的規則，計數沒有改，只在排行裡標註，看的時候略過。</li>
{why_not}
<li>這份方法在算之前就寫定並提交（專案文件 docs/L {"第 13 節" if st.get("round") == 3 else "第 11 節" if st.get("round") == 2 else "第 9 節"}）。</li>
</ul>"""

    # 色票名稱跟 App 一致（--fg、--muted、--pri、--pri-fg、--ok、--ng），App 的對比檢查才能原樣套用
    css = """
:root{--pri-fg:#ffffff;--bg:#f7f8fa;--paper:#fff;--fg:#1b2430;--muted:#536071;--line:#d8dee6;--pri:#1f5a8a;--ok:#1d6b3a;--ok-bg:#e5f3ea;--ng:#a32a20;--ng-bg:#fbe7e5;--warn:#7a4b00;--warn-bg:#fbf0dc;
--f:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--pri-fg:#11161c;--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn:#f0c779;--warn-bg:#33281a;color-scheme:dark}}
:root[data-theme="dark"]{--pri-fg:#11161c;--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn:#f0c779;--warn-bg:#33281a;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 var(--f)}
main{max-width:760px;margin:0 auto;padding-inline:16px;padding-block:20px 48px}
h1{font-size:1.45rem;line-height:1.35;margin:0 0 6px;text-wrap:balance}
h2{font-size:1.2rem;margin:0 0 10px;text-wrap:balance}h3{font-size:1.05rem;margin:22px 0 8px}h4{font-size:.98rem;margin:16px 0 6px;color:var(--pri)}
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
details{margin:10px 0}summary{cursor:pointer;font-weight:600;color:var(--pri);padding:6px 0}
.facts td:first-child{white-space:nowrap;color:var(--muted)}
nav a{color:var(--pri)}nav{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.92rem}
.keynote{border-left:4px solid var(--pri);padding-left:10px}
.posthoc{display:block;font-size:.82rem;color:var(--warn)}
"""
    unanswered = ""
    slow = ""
    if st.get("round") == 3 and not truth_ok:
        r1 = (st.get("round1") or {}).get("ruler")
        r2r = (st.get("round2") or {}).get("ruler")
        pn = {"pos": "問對", "neg": "問錯", "member": "屬類", "other": "其他", "None": "空白"}
        pairs = "、".join(f"程式判「{pn.get(k.split('→')[0], k)}」、判斷者判「{k.split('→')[1]}」{v} 題" for k, v in st.get("disagree_pairs", []))
        rows3 = "".join(f"<tr><td>{a}</td><td class=num>{b}</td><td>{c}</td></tr>" for a, b, c in [
            ("第一輪：只看關鍵字，三類", f"{r1['overall']:.0%}" if r1 else "—", "「其他」那一類只有 80%：「何者為非」「不得有下列何種情事」沒抓到，「應如何正確處理」被當成問錯"),
            ("第二輪：只看最後一句，補關鍵字", f"{r2r['overall']:.0%}" if r2r else "—", "主要是定義不一致：「何者不是某類」程式判問錯、判斷者判其他；「應如何處理」判斷者算問對"),
            ("第三輪：先寫規格，兩邊照同一份規格", f"{rl['overall']:.0%}", "各類 " + "、".join(f"{CLS_NAME3[c]} {r:.0%}" for c, (r, n) in rl["per"].items()))])
        diag = f"<p>{esc(st['diagnosis'])}</p>" if st.get("diagnosis") else ""
        # 換方法：模型逐題分類（docs/L 第 15 節）；結果檔由 scripts/ethics_modelcls.py report 寫
        mcf = D / "modelcls" / "modelcls-result.json"
        mc = json.loads(mcf.read_text(encoding="utf-8")) if mcf.exists() else None
        mc_html = ""
        if mc and mc.get("stab") and not mc["stab"]["pass"]:
            rows3 += (f"<tr><td>換方法：模型逐題讀全部 1,174 題</td><td class=num>{mc['stab']['rate']:.0%}</td>"
                      f"<td>卡在第一關「自己跟自己比」（門檻 95%）：同一個模型把同樣 {mc['stab']['n']} 題換個順序再分一次，就有 {round((1 - mc['stab']['rate']) * mc['stab']['n'])} 題分得不一樣，"
                      "所以後面的獨立驗證沒有跑</td></tr>")
            mc_html = ('<p><b>第四種做法也停了</b>：關鍵字分不出來，就改讓模型逐題讀懂再分。但同一個模型對同一批題連自己都對不上——'
                       '分得不一樣的那幾題，都卡在規格本身的邊界：「何者不是應注意的事項」算屬不屬於某類還是問錯、「應拒絕哪一個」「最宜採用哪種方法」算問做法還是問名詞、'
                       '「內容應包括哪些」算屬類還是問對。也就是說，<b>這一步卡住的不是分類工具，是「題目在問對還是問錯」對一部分題目本來就沒有唯一答案</b>。'
                       '事先承諾這是最後一種方法；不再換方法、不再調門檻、不再改規格（修規格的邊界再重跑，也算繼續這條路）。</p>')
            # 對讀者的推論（docs/L 第 16 節）：問法本身有歧義的題，不能靠規則，只能讀完。例子取自 ④ 分得不一樣的題與分類者回報的難題。
            # 例子含題庫原文的問句，只放本機（data/local/sfi/slow-examples.json：[問法 HTML, 例子, 為什麼要慢讀]）；沒有檔就不出這一節
            exf = D / "slow-examples.json"
            ex = json.loads(exf.read_text(encoding="utf-8"))["examples"] if exf.exists() else []
            rows_ex = "".join(f"<tr><td>{a}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in ex)
            slow = '' if not ex else ('<section id="slow"><h2>這幾種問法要特別慢讀</h2>'
                    '<p class="keynote">上面那一節查出來的根因，對你考試直接有用：有一部分題目連「在問對還是問錯」都有兩種讀法，'
                    '同一個模型讀兩次都會讀出不同結果。<b>碰到這類題，沒有規則可以套，只能把題目讀完。</b></p>'
                    '<p class="lead">下面是分類時最常讀出兩種結果的問法。例子是題庫裡的寫法（只節錄問句）。</p>'
                    '<div class="tw"><table><thead><tr><th>問法</th><th>例子</th><th>為什麼要慢讀</th></tr></thead><tbody>' + rows_ex + '</tbody></table></div>'
                    '<p class="muted">這不是完整清單：只是分類時被認出來的幾種。沒列在這裡的題，也可能有同樣的問題。</p></section>')
        intro = ("試過三輪關鍵字、再換成模型逐題讀題，四次都沒過，所以不換算。這條路已經走完，不再試。" if mc_html
                 else "試過三輪，三輪都沒過，所以不換算。這是最後一輪，不再試。")
        unanswered = (f'<section id="unanswered" class="alert"><h2>這份重點整理有一個它答不了的問題</h2>'
                      '<p class="alert-h">「看到這句話，它通常是對的還是錯的？」——答不了。</p>'
                      '<p>要回答它，得先知道每一題問的是「哪個對」還是「哪個錯」：問「哪個錯」的題目，正解是一句錯的敘述。這一步只能讓程式依題幹的字分，'
                      '而事先定好：程式的分法要跟另一個獨立判斷者一致（整體 ≥ 90%、每一類 ≥ 85%），才拿來換算對錯。' + intro + '</p>'
                      '<div class="tw"><table><thead><tr><th>做法</th><th>一致</th><th>沒過的地方</th></tr></thead><tbody>' + rows3 + '</tbody></table></div>'
                      f'<p><b>第三輪不一致的題</b>：{esc(pairs) or "—"}。</p>{diag}{mc_html}'
                      '<p>能答的是「哪些說法常被選為答案」「哪些說法常被拿來當誘答」——那是直接數出來的，不靠任何分類。用的時候記得看題目問的是對還是錯。</p>'
                      '<h3>同一個資料夾裡的三份重點整理：哪份是最新的</h3>'
                      '<div class="tw"><table><thead><tr><th>檔名</th><th>是什麼</th></tr></thead><tbody>'
                      '<tr><td>ethics-重點整理.html</td><td><b>最新版，以這份為準</b>（三輪關鍵字＋換方法的結果都在這份；就是你正在看的這份）</td></tr>'
                      '<tr><td>ethics-重點整理-round2.html</td><td>第二輪的舊版，只留作紀錄。題型驗尺沒過</td></tr>'
                      '<tr><td>ethics-重點整理-round1.html</td><td>第一輪的舊版，只留作紀錄。題型驗尺沒過，組合型選項還混在排行裡（有兩份排行的前 10 名有兩到三成是假的）</td></tr>'
                      '</tbody></table></div><p class="muted">三份檔名看起來都很合理。沒有 round 字樣的那份才是最新的；舊版不要拿來背。</p></section>')
    facts = [("考試", "金融市場常識與職業道德（共同科目）"), ("題數／時間", "一百題，四選一單選，六十分鐘"), ("配分", "金融市場常識 50%、職業道德 50%"),
             ("及格", "七十分；成績保留五年"), ("報名費", "300 元（2027 年 1 月 1 日起；2026 年底前的場次是 250 元）"),
             ("考試範圍", "116 年版題庫（1,174 題），2027 年 1 月 1 日起適用"),
             ("應試方式", "證基會網頁寫「單科筆試」，報名網站幾乎天天有筆試場次；研訓院網頁另有電腦應試選項。兩邊說法不一，建議打電話確認：證基會測驗中心 02-2357-4388")]
    facts_html = '<div class="tw"><table class="facts"><tbody>' + "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in facts) + "</tbody></table></div>"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><title>金融常識與道德重點整理</title><style>{css}</style></head><body><main>
<h1>金融市場常識與職業道德・重點整理</h1>
<p class="muted">依證基會公告的 116 年版題庫（2027 年 1 月 1 日起適用）由程式算出；產生時間 {esc(gen_at)}。只放在你自己的裝置，不要轉貼。</p>
<nav>{'<a href="#unanswered">答不了的問題</a>' if unanswered else ''}{'<a href="#slow">要慢讀的問法</a>' if slow else ''}<a href="#how">怎麼讀</a><a href="#facts">考試怎麼考</a><a href="#scope">各科範圍</a><a href="#types">題型</a><a href="#gen">金融市場常識</a><a href="#eth">職業道德</a><a href="#diff">兩版差異</a><a href="#method">方法與限度</a></nav>
<section id="how"><h2>這份怎麼讀</h2>
<p class="keynote">每一節都在回答一個問題：「看到這句話，它通常是對的還是錯的？」「哪些說法最常被拿來騙人？」數字是這句話在 116 年版題庫裡出現的次數。</p>
<p>題庫只有字面統計：同一個意思換個說法，不會算在一起。所以「沒出現在排行裡」不代表不重要，只代表這句話沒有<b>一字不差</b>地重複出現很多次。</p>
<p>這裡不逐題解釋為什麼選那個答案；答案以官方題庫為準。</p></section>
<section id="facts"><h2>考試怎麼考</h2>{facts_html}
<p class="muted">以上是整理（改寫、合併幾個頁面，不是原文）：證基會「測驗方式及內容」「測驗費用」「題庫下載區」與台灣金融研訓院證照頁，2026-10-12 查。年份換成西元，題數 1,174 是算出來的，「建議打電話確認」是我們的建議。</p>
<p class="warn-line">考題是否全部出自公告題庫：在已檢索範圍內未見明文，官方只寫「……據此作為本項測驗辦理依據」（證基會「測驗辦理說明」，前面省略）。請不要當成保證。</p></section>
<section id="scope"><h2>各科範圍（官方）</h2>
<p class="muted">官方網頁是逐項編號的清單；這裡把每一科併成一行、用頓號隔開。項目名稱照 2026-10-12 查到時的記錄，當時沒有存網頁，不能再逐字核對。</p>
<p><b>金融市場常識（50%）</b>：金融體系、證券期貨市場、銀行實務、信託實務、貨幣市場實務、保險實務</p>
<p><b>職業道德（50%）</b>：業務推廣與招攬、受託執行業務、告知義務與通知、誠實信用原則、有關利益衝突、保密原則、遵守法律規範與自律</p>
<p class="muted">題庫 PDF 沒有標每題屬於哪一章，所以下面的統計只分這兩部分。</p></section>
{unanswered}{slow}
<section id="types"><h2>各科常見的題型</h2>{types_html}
<p class="muted">「問哪個錯」的題目，正解是一句錯的敘述——背答案時要看清楚題目問的是對還是錯。</p></section>
{''.join(parts_html)}
<section id="diff"><h2>兩版差異（113 年版 → 116 年版）</h2>
<p class="lead">練 113 年版會學到錯東西的，就是這一批：被刪掉的題、被改過的題。考試範圍是 116 年版。</p>{''.join(dsec)}</section>
<section id="method"><h2>方法與限度</h2>{method}</section>
</main></body></html>"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"classify": classify, "lock": lock, "build": build, "classify2": classify2, "lock2": lock2, "classify3": classify3, "lock3": lock3}
             .get(cmd, lambda: (print("用法：classify｜lock｜build [2|3]｜classify2｜lock2｜classify3｜lock3"), 2)[1])())
