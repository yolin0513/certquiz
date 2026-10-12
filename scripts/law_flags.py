#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N1：標出「這題點名的法規，在那期考試之後修正過」（Dispatch 2026-10-12 准做）
-------------------------------------------------------------------------------
  python -u scripts/law_flags.py      讀 data/local/law/ 的法規資料 → data/local/law/flags.json（只放本機）
之後 `python scripts/build_data.py --local` 會把結果放進內控匯入包（每題的 law 欄位）；App 從匯入的題目自己數，不寫死任何數字。

輸入（都由 scripts/law_coverage.py 產生）：
  cited.json         每題題幹點名的法規、法規基準日（law_as_of：答案卷疑義申請起日，測驗後約兩天）
  sources.json       全國法規資料庫：歷次版本日期、現行修正日期
  sources-fsc.json   金管會主管法規查詢系統：全國法規資料庫查不到的那幾部
  raw/all-<pcode>.html  全國法規資料庫現行條文頁：讀「生效狀態」（有沒有條文尚未施行）

每題分四類（母體核對：四類相加＝匯入包可練的題數，不等就不寫檔）：
  amended    題幹點名的法規裡，至少一部查得到「晚於法規基準日」的修正
  unchanged  點名的每一部都查得到版本資料，而且都沒有晚於法規基準日的修正
  partial    沒有查到晚於基準日的修正，但點名的法規裡有的查不到版本資料
  none       題幹沒有點名法規，或點名的法規都查不到版本資料
「查得到版本資料」＝至少知道一個版本日期（歷次版本或現行修正日期）。
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
LAW = ROOT / "data" / "local" / "law"
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
OUT = LAW / "flags.json"
STATUSES = ("amended", "unchanged", "partial", "none")


def iso(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def pending_text(pcode):
    """全國法規資料庫現行條文頁的「生效狀態」：有條文尚未施行時，回傳頁面上那一句（例：第 44～47 條施行日期由主管機關定）。"""
    p = LAW / "raw" / f"all-{pcode}.html"
    if not p.exists():
        return None
    t = re.sub(r"\s+", " ", re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", " ", p.read_text(encoding="utf-8"))))
    # 原文照抄網頁上連續的那一段（只把排版的換行與標籤換成一個空格），不拼接、不改字：畫面上會標成「原文」
    m = re.search(r"生效狀態[：:]\s*※(本法規部分或全部條文尚未生效.*?施行日期[^。]*?定)", t)
    return m.group(1).strip() if m else None


def law_table():
    src = json.loads((LAW / "sources.json").read_text(encoding="utf-8"))
    fsc = json.loads((LAW / "sources-fsc.json").read_text(encoding="utf-8"))
    out = {}
    for name in set(src) | set(fsc):
        dates, pend = set(), None
        m = (src.get(name) or {}).get("moj")
        if m:
            dates |= set(m["old_versions"]) | ({m["current_date"]} if m["current_date"] else set())
            pend = pending_text(m["pcode"])
        for e in (fsc.get(name) or {}).get("exact", []):
            dates |= set(e["history"]) | ({e["current"]} if e["current"] else set())
        out[name] = {"dates": sorted(dates), "pending": pend}
    return out


def ruler(T):
    """驗尺（兩個方向，常設規則 17）：內控辦法一定有 2021-09-23 與 2026-05-06 兩版、而且有尚未施行的條文；
    銀行法的現行頁不該被讀出尚未施行；沒有任何一個日期晚於今天。"""
    today = datetime.now().strftime("%Y%m%d")
    ic = T.get("金融控股公司及銀行業內部控制及稽核制度實施辦法", {})
    ok1 = {"20210923", "20260506"} <= set(ic.get("dates", [])) and bool(ic.get("pending")) and "44" in (ic.get("pending") or "")
    ok2 = "銀行法" in T and T["銀行法"]["pending"] is None
    late = sorted({d for v in T.values() for d in v["dates"] if d > today})
    print(f"  驗尺：內控辦法版本含 2021-09-23、2026-05-06 且讀到尚未施行（{ic.get('pending')}）→ {'✓' if ok1 else '✗'}；"
          f"銀行法沒有被讀成尚未施行 → {'✓' if ok2 else '✗'}；晚於今天的日期 {late or '無'} → {'✓' if not late else '✗'}")
    return ok1 and ok2 and not late


def main():
    cited = json.loads((LAW / "cited.json").read_text(encoding="utf-8"))
    T = law_table()
    if not ruler(T):
        print("LAW-FLAGS ABORT：驗尺失敗，不寫檔")
        return 2
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    active = [q for q in pack["questions"] if not q.get("dupOf") and q.get("status") != "retired"]
    missing = [q["id"] for q in active if q["id"] not in cited["per_question"]]
    if missing:
        print(f"LAW-FLAGS ABORT：匯入包有 {len(missing)} 題不在 cited.json（先重跑 scripts/law_coverage.py names）：{missing[:5]}")
        return 2
    flags = {}
    for q in active:
        asof = q["law_as_of"].replace("-", "")
        laws = []
        for name in cited["per_question"][q["id"]]:
            t = T.get(name) or {"dates": [], "pending": None}
            e = {"name": name, "known": bool(t["dates"]), "after": [iso(d) for d in t["dates"] if d > asof]}
            if t["pending"] and e["after"]:
                e["pending"] = t["pending"]
            laws.append(e)
        if any(e["after"] for e in laws):
            st = "amended"
        elif laws and all(e["known"] for e in laws):
            st = "unchanged"
        elif any(e["known"] for e in laws):
            st = "partial"
        else:
            st = "none"
        flags[q["id"]] = {"status": st, "laws": laws}
    n = {s: sum(1 for f in flags.values() if f["status"] == s) for s in STATUSES}
    total = sum(n.values())
    print(f"母體核對：考試後修正過 {n['amended']}＋查得到、沒修正 {n['unchanged']}＋只查到一部分、沒看到修正 {n['partial']}＋沒有版本資料 {n['none']}"
          f"＝{total}／匯入包可練 {len(active)} 題 → {'✓' if total == len(active) else '✗'}")
    if total != len(active):
        print("LAW-FLAGS ABORT：母體不符，不寫檔")
        return 1
    named = sum(1 for f in flags.values() if f["laws"])
    has_ver = sum(1 for f in flags.values() if any(e["known"] for e in f["laws"]))
    print(f"  題幹點名法規 {named} 題；其中至少一部查得到版本資料 {has_ver} 題；考試後修正過 {n['amended']} 題")
    by_law = {}
    for f in flags.values():
        for e in f["laws"]:
            r = by_law.setdefault(e["name"], [0, 0])
            r[0] += 1
            r[1] += bool(e["after"])
    for name, (a, b) in sorted(by_law.items(), key=lambda kv: -kv[1][0])[:6]:
        print(f"  {name}：點名 {a} 題，其中考試後修正過 {b} 題{'（整批）' if a == b else ''}")
    checked = datetime.fromtimestamp((LAW / "sources.json").stat().st_mtime).strftime("%Y-%m-%d")
    OUT.write_text(json.dumps({"checked": checked, "counts": n, "flags": flags}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"LAW-FLAGS OK：{total} 題 → {OUT}（法規資料查詢日 {checked}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
