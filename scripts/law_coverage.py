#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
讀書模式第 3 步：法規條文（C 層）涵蓋率的量測——先量、回報數字，再決定做不做（docs/K）
-------------------------------------------------------------------------------
  python -u scripts/law_coverage.py names    從本機匯入包抓題幹點名的法規名稱（正規化後）→ data/local/law/cited.json
  python -u scripts/law_coverage.py fetch    逐部到全國法規資料庫查：有沒有、pcode、現行全文、歷次版本清單（每次請求間隔 1.2 秒）
                                             原始頁存 data/local/law/raw/；結果 data/local/law/sources.json
  python -u scripts/law_coverage.py report   印出漏斗：題幹點名 → 資料庫查得到 → 有考試當時的版本
只讀公開頁面、不登入；抓下來的頁面只放本機。
"""
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
OUT = ROOT / "data" / "local" / "law"
RAW = OUT / "raw"
CITED = OUT / "cited.json"
SOURCES = OUT / "sources.json"
MOJ = "https://law.moj.gov.tw"
UA = "Mozilla/5.0 (CertQuiz law coverage; personal study tool)"
# 全國法規資料庫的憑證缺 Subject Key Identifier，Python 3.13 預設的 X509 嚴格模式會拒絕（curl 用 Windows 的 TLS 沒這個問題）。
# 只關掉「嚴格模式」這一個旗標；憑證鏈與主機名稱照樣驗證，不是關掉驗證。
CTX = ssl.create_default_context()
CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

SUF = r"(?:辦法|規則|準則|要點|條例|細則|規範|原則|標準|基準|注意事項|守則|須知|作業程序|法)"
Q = re.compile(r"「([^」]{4,40}?" + SUF + r")」")
BARE = re.compile(r"(?:依|根據|按)((?:[^\s，、「」（）()依]{2,20}?)" + SUF + r")(?=第|規定|之規定|所稱|，|有關|及|、|中|對)")
BARE2 = re.compile(r"(?:及|、)([^\s，、「」（）()]{2,20}?" + SUF + r")(?=之規定|規定)")
UNNAMED = re.compile(r"依(?:相關)?(?:主管機關|金管會|財政部|中央銀行|央行)?(?:之)?(?:規定|函釋|函令)")
# 正規化：同一部的不同寫法、抓錯的片段（逐一看過題幹上下文才定的，2026-10-08）
ALIAS = {
    "銀行公會會員徵信準則": "中華民國銀行公會會員徵信準則",
    "據證券投資顧問事業從業人員行為準則": "證券投資顧問事業從業人員行為準則",
    "金融機構辦理電子銀行業務安全控制作業基準": "金融機構辦理電子銀行業務安全控管作業基準",
    "約定方式提取存款之規範": "活期存款依約定方式提取存款之規範",
}
DROP = {"審查準則", "每日市價為原則", "適當性(Suitability)原則", "瞭解金融消費者審查原則"}   # 不是法規名稱：概念或抓錯的片段


def names():
    qs = [q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"] if not q.get("dupOf")]
    per, cat = {}, {}
    for q in qs:
        t = q["stem"]
        f = set(Q.findall(t)) | set(BARE.findall(t)) | set(BARE2.findall(t))
        f = {ALIAS.get(x, x) for x in f if not re.fullmatch(r"(?:主管機關|相關|上述|下列|本)" + SUF, x)} - DROP
        per[q["id"]] = sorted(f)
        cat[q["id"]] = "named" if f else ("unnamed" if UNNAMED.search(t) else "none")
    cnt = {}
    for f in per.values():
        for x in f:
            cnt[x] = cnt.get(x, 0) + 1
    OUT.mkdir(parents=True, exist_ok=True)
    CITED.write_text(json.dumps({"per_question": per, "category": cat, "subject": {q["id"]: q["subject"] for q in qs},
                                 "law_as_of": {q["id"]: q.get("law_as_of") for q in qs},
                                 "names": sorted(cnt.items(), key=lambda x: -x[1])}, ensure_ascii=False, indent=1), encoding="utf-8")
    n_named = sum(1 for v in cat.values() if v == "named")
    print(f"NAMES OK：{len(qs)} 題；題幹點名法規 {n_named} 題、只寫依規定 {sum(1 for v in cat.values() if v == 'unnamed')} 題、沒提到 {sum(1 for v in cat.values() if v == 'none')} 題；不同法規 {len(cnt)} 部")
    return 0


def get(url, path):
    if path.exists():
        return path.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        html = r.read().decode("utf-8", "replace")
    path.write_text(html, encoding="utf-8")
    time.sleep(1.2)
    return html


def parse_search(html):
    """搜尋結果頁：每筆是 <a id="hlkLawLink" title="法規名稱" href="../Hot/AddHotLaw.ashx?pcode=XXX&...">。回傳 [(名稱, pcode)]。
    （第一版用 LawAll.aspx 的連結找，那是英文版與附件的連結，結果 0／41——驗尺就是為了擋這種「0 是程式錯不是真的沒有」）"""
    return re.findall(r'id="hlkLawLink"\s+title="([^"]+)"\s+href="[^"]*?pcode=([A-Z0-9]+)', html)


def ruler():
    """正對照：內控稽核辦法（pcode G0380218，2026-10-08 手動查過）與銀行法一定要查得到；反對照：編造的名稱一定查不到。"""
    def look(name):
        safe = re.sub(r"[^\w]", "_", name)[:60]
        html = get(f"{MOJ}/Law/LawSearchResult.aspx?ty=ONEBAR&kw={urllib.parse.quote(name)}", RAW / f"search-{safe}.html")
        return [p for t, p in parse_search(html) if re.sub(r"\s", "", t) == name]
    pos1 = look("金融控股公司及銀行業內部控制及稽核制度實施辦法")
    pos2 = look("銀行法")
    neg = look("銀行業辦理月球分行業務管理辦法")
    ok = pos1[:1] == ["G0380218"] and len(pos2) >= 1 and not neg
    print(f"{'✓' if ok else '✗'} 驗尺：內控稽核辦法 → {pos1[:1]}（應 G0380218）、銀行法 → {pos2[:1]}（應查得到）、編造的名稱 → {neg}（應查不到）")
    return ok


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    if not ruler():
        print("FETCH ABORT：驗尺失敗，查得到幾部的數字不能下結論")
        return 2
    d = json.loads(CITED.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    res = {}
    for i, (name, n) in enumerate(d["names"], 1):
        safe = re.sub(r"[^\w]", "_", name)[:60]
        html = get(f"{MOJ}/Law/LawSearchResult.aspx?ty=ONEBAR&kw={urllib.parse.quote(name)}", RAW / f"search-{safe}.html")
        # 搜尋結果：每筆是 <a ... href="...LawAll.aspx?pcode=XXX" ...>名稱</a>；只收名稱完全相同的
        hits = parse_search(html)
        exact = [(p, t) for t, p in hits if re.sub(r"\s", "", t) == name]
        entry = {"count": n, "moj": None, "candidates": sorted({t for t, _ in hits})[:8]}
        if exact:
            pcode = exact[0][0]
            hist = get(f"{MOJ}/LawClass/LawHistory.aspx?pcode={pcode}", RAW / f"hist-{pcode}.html")
            vers = sorted(set(re.findall(r"LawOldVer\.aspx\?pcode=" + pcode + r"&(?:amp;)?lnndate=(\d{8})", hist)))
            cur = get(f"{MOJ}/LawClass/LawAll.aspx?pcode={pcode}", RAW / f"all-{pcode}.html")
            m = re.search(r"修正日期[：:]\s*(?:<[^>]+>\s*)*民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", cur) or \
                re.search(r"(?:公發布日|發布日期)[：:]\s*(?:<[^>]+>\s*)*民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", cur)
            current = f"{int(m.group(1)) + 1911:04d}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else None
            abolished = "廢止" in re.sub(r"<[^>]+>", "", cur)[:3000]
            entry["moj"] = {"pcode": pcode, "old_versions": vers, "current_date": current, "abolished_hint": abolished}
        res[name] = entry
        print(f"  {i:02d}/{len(d['names'])} {'✓' if entry['moj'] else '·'} {name}（{n} 題）"
              + (f" pcode={entry['moj']['pcode']}・歷次版本 {len(entry['moj']['old_versions'])}・現行 {entry['moj']['current_date']}" if entry["moj"] else ""))
    SOURCES.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FETCH OK：{sum(1 for v in res.values() if v['moj'])}／{len(res)} 部在全國法規資料庫查得到（名稱完全相同）")
    return 0


def report():
    d = json.loads(CITED.read_text(encoding="utf-8"))
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    per, cat, subj, asof = d["per_question"], d["category"], d["subject"], d["law_as_of"]
    rows = {}
    for qid, names_ in per.items():
        s = subj[qid]
        r = rows.setdefault(s, {"all": 0, "named": 0, "moj": 0, "ver": 0})
        r["all"] += 1
        if not names_:
            continue
        r["named"] += 1
        hits = [src[n]["moj"] for n in names_ if src.get(n, {}).get("moj")]
        if not hits:
            continue
        r["moj"] += 1
        # 有考試當時的版本：考試基準日（law_as_of）之前最近一次修正的那一版查得到；
        # 基準日早於資料庫最早的一版、或抓不到現行日期，都算查不到
        a = (asof.get(qid) or "").replace("-", "")
        ok = False
        for h in hits:
            dates = sorted(set(h["old_versions"]) | ({h["current_date"]} if h["current_date"] else set()))
            if a and dates and dates[0] <= a:
                ok = True
        r["ver"] += ok
    tot = {k: sum(r[k] for r in rows.values()) for k in ("all", "named", "moj", "ver")}
    for s, r in sorted(rows.items()) + [("合計", tot)]:
        print(f"{s}：全部 {r['all']}｜題幹點名法規 {r['named']}（{r['named'] / r['all']:.0%}）｜資料庫查得到 {r['moj']}（{r['moj'] / r['all']:.0%}）"
              f"｜有考試當時的版本 {r['ver']}（{r['ver'] / r['all']:.0%}）")
    miss = [(n, v["count"]) for n, v in src.items() if not v["moj"]]
    print(f"資料庫查不到的 {len(miss)} 部（題數）：" + "、".join(f"{n}（{c}）" for n, c in sorted(miss, key=lambda x: -x[1])))
    return 0


# ---------------------------------------------------------------- 第四層：條文對不對得上（抽樣；docs/K 寫在抽樣之前）
SEED_ART = 20261012
N_ART = 30
TEXT = OUT / "text"
SHEET = OUT / "article-sample.md"
JUDGES = {"me": OUT / "article-judge-me.tsv", "agent": OUT / "article-judge-agent.tsv"}
LOGF = OUT / "log.tsv"


def _sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _log(action, p):
    from datetime import datetime, timezone
    with LOGF.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{_sha(p)}\n")


def _logged(action, name):
    if not LOGF.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOGF.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def articles(html):
    """一版的全文：[(條號, 條文)]；條文是該條各項／款接起來的純文字。"""
    out = []
    for no, body in re.findall(r'<div class="col-no">\s*(?:<a[^>]*>)?\s*(第\s*[0-9\-]+\s*條)\s*(?:</a>)?\s*</div>\s*<div class="col-data">(.*?)</div>\s*</div>\s*</div>', html, flags=re.S):
        txt = re.sub(r"<[^>]+>", "\n", body)
        txt = "\n".join(x.strip() for x in txt.splitlines() if x.strip())
        out.append((re.sub(r"\s", "", no), txt))
    return out


def eligible():
    """有考試當時版本的題目，以及每題要用的那一版（法規名稱、pcode、版本日期、網址）。"""
    d = json.loads(CITED.read_text(encoding="utf-8"))
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    out = {}
    for qid, names_ in d["per_question"].items():
        a = (d["law_as_of"].get(qid) or "").replace("-", "")
        for n in names_:
            m = (src.get(n) or {}).get("moj")
            if not m or not a:
                continue
            olds = sorted(set(m["old_versions"]))
            dates = sorted(set(olds) | ({m["current_date"]} if m["current_date"] else set()))
            ok = [x for x in dates if x <= a]
            if not ok:
                continue
            ver = ok[-1]
            if ver == m["current_date"] and ver not in olds:
                url = f"{MOJ}/LawClass/LawAll.aspx?pcode={m['pcode']}"
            else:
                url = f"{MOJ}/LawClass/LawOldVer.aspx?pcode={m['pcode']}&lnndate={ver}&lser=001"
            out[qid] = {"law": n, "pcode": m["pcode"], "version": ver, "url": url, "law_as_of": a}
            break
    return out


def grams3(s):
    s = re.sub(r"[\s，。、；：「」（）()？?！!．.,]", "", s)
    return {s[i:i + 3] for i in range(len(s) - 2)}


def sample():
    if SHEET.exists():
        print("SAMPLE ABORT：已經抽過了")
        return 2
    import random
    qs = {q["id"]: q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"]}
    el = eligible()
    pick = sorted(random.Random(SEED_ART).sample(sorted(el), N_ART))
    TEXT.mkdir(parents=True, exist_ok=True)
    md = ["# C 層抽樣：條文對不對得上（30 題）", "",
          "判準：該題考試當天施行的那一版裡，有一條的條文**寫出了正解的關鍵內容**，而且對正解的支持高於對每一個錯誤選項 →「對得上」（記條號）；"
          "否則「對不上」（記理由：條文沒寫到、關鍵內容在別的法規、條文同樣支持錯誤選項……）。",
          "每題下面列的「字面最接近的 4 條」只是幫忙找，判定時請讀整部（全文檔路徑在每題裡）。", ""]
    judge = ["題號\t判定（對得上／對不上）\t條號（對得上才填）\t理由"]
    for n, qid in enumerate(pick, 1):
        q, e = qs[qid], el[qid]
        tag = f"{e['pcode']}-{e['version']}"
        html = get(e["url"], RAW / f"ver-{tag}.html")
        arts = articles(html)
        if not arts:
            print(f"SAMPLE ABORT：{tag} 解析不到條文（{e['url']}）")
            return 2
        tf = TEXT / f"{tag}.txt"
        tf.write_text("\n\n".join(f"{no}\n{t}" for no, t in arts), encoding="utf-8")
        key = grams3(q["stem"] + q["options"][q["answer"] - 1] * 2)
        top = sorted(arts, key=lambda x: -len(key & grams3(x[1])))[:4]
        md += [f"## S{n:02d}　{qid}（{'法規' if q['subject'] == 'law' else '實務'}，考試基準日 {e['law_as_of']}）", q["stem"]]
        md += [f"- ({k}) {o}{'　**（正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
        md += ["", f"**法規**：{e['law']}（pcode {e['pcode']}）；**考試當天施行的版本**：{e['version']}；全文檔：`{tf}`（共 {len(arts)} 條）",
               f"網址：{e['url']}", "", "字面最接近的 4 條："]
        for no, t in top:
            md += [f"- **{no}**：{t[:500]}{'…' if len(t) > 500 else ''}"]
        md.append("")
        judge.append(f"S{n:02d}\t\t\t")
    SHEET.write_text("\n".join(md), encoding="utf-8")
    for j in JUDGES.values():
        j.write_text("\n".join(judge) + "\n", encoding="utf-8")
    for p in (Path(__file__), SHEET):
        _log("article-sample", p)
    print(f"SAMPLE OK：母體 {len(el)} 題，抽 {len(pick)} 題 → {SHEET}；判斷檔 {', '.join(str(j) for j in JUDGES.values())}")
    return 0


def _rows(p):
    out = {}
    for l in p.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + [""] * 4)[:4]]
            out[c[0]] = c
    return out


def lock():
    who = sys.argv[2] if len(sys.argv) > 2 else ""
    if who not in JUDGES:
        print("用法：lock me｜lock agent")
        return 2
    j = JUDGES[who]
    if _logged("article-lock", j.name):
        print("LOCK ABORT：已經鎖定過")
        return 2
    bad = [k for k, r in _rows(j).items() if r[1] not in ("對得上", "對不上") or not r[3] or (r[1] == "對得上" and not r[2])]
    if bad or len(_rows(j)) != N_ART:
        print(f"LOCK ABORT：{j.name} 有空白或格式不對：{bad}")
        return 2
    _log("article-lock", j)
    print(f"LOCK OK：{j.name} {_sha(j)[:12]}…")
    return 0


def score():
    import math
    for j in JUDGES.values():
        lk = _logged("article-lock", j.name)
        if not lk or _sha(j) != lk[-1]:
            print(f"SCORE ABORT：{j.name} 沒鎖定或鎖定後被改過")
            return 2
    pop = len(eligible())
    R = {w: _rows(j) for w, j in JUDGES.items()}

    def wilson(k, n, z=1.96):
        p = k / n
        c = (p + z * z / (2 * n)) / (1 + z * z / n)
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return c - h, c + h

    for w, r in R.items():
        k = sum(1 for x in r.values() if x[1] == "對得上")
        lo, hi = wilson(k, N_ART)
        print(f"{'我' if w == 'me' else '獨立代理'}：對得上 {k}／{N_ART}（{k / N_ART:.0%}，95% 信賴區間 {lo:.0%}～{hi:.0%}）"
              f" → 推估全部 801 題的 C 層涵蓋 ≈ {pop * k / N_ART:.0f} 題（{pop * k / N_ART / 801:.1%}；區間 {pop * lo / 801:.1%}～{pop * hi / 801:.1%}）")
    both = [s for s in R["me"] if R["me"][s][1] == "對得上" and R["agent"][s][1] == "對得上"]
    diff = [s for s in R["me"] if R["me"][s][1] != R["agent"][s][1] or (R["me"][s][1] == "對得上" and R["me"][s][2].replace(" ", "") != R["agent"][s][2].replace(" ", ""))]
    print(f"兩人都判對得上（而且條號相同才算一致）：{len([s for s in both if s not in diff])}／{N_ART}；不一致 {len(diff)} 題：")
    for s in diff:
        print(f"  · {s}：我 {R['me'][s][1]}{('（' + R['me'][s][2] + '）') if R['me'][s][2] else ''}——{R['me'][s][3]}｜代理 {R['agent'][s][1]}"
              f"{('（' + R['agent'][s][2] + '）') if R['agent'][s][2] else ''}——{R['agent'][s][3]}")
    return 0


# ---------------------------------------------------------------- 全國法規資料庫查不到的那幾部：到金管會主管法規查詢系統查（Dispatch 2026-10-08 選 c）
FSC = "https://law.fsc.gov.tw"
FSC_OUT = OUT / "sources-fsc.json"


def roc(s):
    """「110.09.23」或「民國 110 年 09 月 23 日」→ 20210923。"""
    m = re.search(r"(\d{2,3})\s*[.年]\s*(\d{1,2})\s*[.月]\s*(\d{1,2})", s)
    return f"{int(m.group(1)) + 1911:04d}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else None


def fsc_lookup(name):
    """回傳 {'hits': [(id, 標題)], 'exact': [{id, current, history:[日期], has_history}]}。"""
    safe = re.sub(r"[^\w]", "_", name)[:60]
    html = get(f"{FSC}/SearchAllResultList.aspx?KW={urllib.parse.quote(name)}&type=B", RAW / f"fsc-B-{safe}.html")
    t = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    hits = [(i, re.sub(r"\s", "", x)) for i, x in re.findall(r'href="LawContent\.aspx\?id=([A-Z0-9]+)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,120})', t)]
    exact = []
    for i, title in hits:
        if title != name or i in [e["id"] for e in exact]:
            continue
        c = get(f"{FSC}/LawContent.aspx?id={i}", RAW / f"fsc-content-{i}.html")
        ct = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", c, flags=re.S))
        m = re.search(r"(?:修正日期|發布日期|發文日期)\s*[：:]\s*(民國\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日|\d{2,3}\.\d{1,2}\.\d{1,2})", ct)
        has_h = f"LawContentHistoryList.aspx?id={i}" in c
        hist = []
        if has_h:
            hl = get(f"{FSC}/LawContentHistoryList.aspx?id={i}", RAW / f"fsc-hist-{i}.html")
            hist = sorted({roc(d) for d in re.findall(r">\s*(\d{2,3}\.\d{2}\.\d{2})\s*<", hl)} - {None})
        exact.append({"id": i, "current": roc(m.group(1)) if m else None, "has_history": has_h, "history": hist})
    return {"hits": hits[:10], "exact": exact}


def fsc():
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    missing = [n for n, v in src.items() if not v["moj"]]
    # 驗尺：內控稽核辦法在金管會系統一定查得到，而且歷史法規裡有 110.09.23（2021-09-23）那一版；編造的名稱一定查不到
    r = fsc_lookup("金融控股公司及銀行業內部控制及稽核制度實施辦法")
    ok_pos = any(e["has_history"] and "20210923" in e["history"] for e in r["exact"])
    neg = fsc_lookup("銀行業辦理月球分行業務管理辦法")
    ok = ok_pos and not neg["exact"]
    print(f"{'✓' if ok else '✗'} 驗尺：內控稽核辦法 → {[(e['id'], e['has_history'], len(e['history'])) for e in r['exact']]}（要有歷史法規且含 20210923）；編造的名稱 → {neg['exact']}（應查不到）")
    if not ok:
        print("FSC ABORT：驗尺失敗，查得到幾部的數字不能下結論")
        return 2
    res = {}
    for n in missing:
        r = fsc_lookup(n)
        res[n] = {"count": src[n]["count"], **r}
        ex = r["exact"]
        desc = "；".join(f"{e['id']} 現行 {e['current']}・歷史法規 {'有 ' + str(len(e['history'])) + ' 版（' + (e['history'][0] if e['history'] else '') + ' 起）' if e['has_history'] else '無'}" for e in ex)
        print(f"  {'✓' if ex else '·'} {n}（{src[n]['count']} 題）：{desc or '名稱完全相同的查不到'}" + ("" if ex else f"｜相近結果：{[h[1][:24] for h in r['hits'][:3]]}"))
    FSC_OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FSC OK：{sum(1 for v in res.values() if v['exact'])}／{len(res)} 部在金管會主管法規查詢系統查得到（名稱完全相同）")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"names": names, "fetch": fetch, "report": report, "sample": sample, "lock": lock, "score": score, "fsc": fsc}.get(cmd, lambda: (print("用法：names｜fetch｜report｜sample｜lock me|agent｜score"), 2)[1])())
