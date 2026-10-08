#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TABF 官方試卷 PDF → 本機題庫原始檔（不入庫）
--------------------------------------------
輸入：refs/ 底下使用者自己取得的 TABF 試卷與答案 PDF（.gitignore 擋）
輸出：data/local/src/bic/tabf-p<期>-<科>.txt（.gitignore 擋；commit 前自查 R1／R3 也擋）
這支腳本只有程式、不含任何題目內容，可以入庫；換電腦後放好 PDF 重跑即可。

用法：
    python scripts/import_tabf.py                 # 轉所有「試卷＋答案」齊全的期別
    python scripts/import_tabf.py --check-only    # 只檢查、不寫檔
    python scripts/import_tabf.py --periods 47 49 # 只轉指定期別

**答案錯位是本專案最可能的致命錯誤**，所以寫檔前一定先過完下面全部檢查；任何一項不過：
點名是哪一期、哪一科、哪幾題，結束碼 1，**一個檔都不寫**。
    C1 試卷上的「共 N 題」讀得到
    C2 題號母體：試卷裡行首的題號依序剛好是 1..N（缺號、重號、亂序都點名）
    C3 每一題：題幹不空；選項 (1)(2)(3)(4) 依序各出現一次、內容不空、沒有 (5)
    C4 答案 A（pdftotext -raw，逐列「題號 法規 實務」）：題號 1..N 各一次、值在 1..4
    C5 答案 B（pdftotext -simple，依欄位的水平位置判斷是法規還是實務）：同 C4
    C6 A 與 B 逐題相同（兩條獨立的讀法；不同就點名題號）
    C7 母體：答案題數＝試卷題數＝試卷標示題數
    C8 答案卷標題的期別、組別跟試卷一致
證明這些檢查真的會紅：scripts/test_import_tabf.py（突變測試）。

需要本機的 pdftotext（Git for Windows 內附的 xpdf 4.00）。
"""
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
REFS = [ROOT / "refs" / "tabf" / "past", ROOT / "refs" / "user" / "tabf"]
OUT = ROOT / "data" / "local" / "src" / "bic"
SUBJECTS = {"law": "法規", "gen": "實務"}           # 本 App 範圍：一般金融組
ANSWER_COL = {"law": 0, "gen": 1}                   # 答案卷第一節＝法規、第二節＝實務

HEADER_RE = re.compile(
    r"^(台灣金融研訓院第|科目[：:]|注意[：:]|本試卷之試題|者，該題不予計分|答案卡請務必|【請接續背面】|入場通知書)")


class ConvertError(Exception):
    pass


# ------------------------------------------------------------------ 取文字
def pdftext(pdf: Path, mode: str) -> str:
    r = subprocess.run(["pdftotext", mode, "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
    if r.returncode != 0:
        raise ConvertError(f"pdftotext {mode} 讀不了 {pdf.name}：{r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8", "replace")


def find_file(name: str):
    for d in REFS:
        p = d / name
        if p.exists():
            return p
    return None


def files_for(period: int):
    law = find_file(f"第{period}期_一般金融_法規.pdf") or find_file(f"第{period}期_法規(一般消費共用).pdf")
    gen = find_file(f"第{period}期_一般金融_實務.pdf")
    ans = find_file(f"第{period}期_一般金融_答案.pdf")
    return {"law": law, "gen": gen, "ans": ans}


def available_periods():
    ps = set()
    for d in REFS:
        if d.exists():
            for p in d.glob("第*期_*.pdf"):
                m = re.match(r"第(\d+)期_", p.name)
                if m:
                    ps.add(int(m.group(1)))
    return sorted(ps)


# ------------------------------------------------------------------ 試卷
def parse_paper(raw: str, label: str):
    """回傳 (宣告題數, [題目 dict], [錯誤字串])。題目 dict：qno, page, stem, options[4]。"""
    errs = []
    m = re.search(r"共\s*(\d+)\s*題", raw)
    if not m:
        return None, [], [f"{label} C1 讀不到試卷標示的題數"]
    declared = int(m.group(1))

    # 去掉每頁的頁首說明；保留換頁符號以算頁碼
    lines = []
    for ln in raw.split("\n"):
        core = ln.lstrip("\f")
        if HEADER_RE.match(core.strip()):
            if ln.startswith("\f"):
                lines.append("\f")
            continue
        lines.append(ln)
    text = "\n".join(lines)

    marks = [(int(mm.group(1)), mm.start(), mm.end()) for mm in re.finditer(r"(?m)^\f?(\d{1,3})\.(?=\D)", text)]
    seq = [n for n, _s, _e in marks]
    expect = list(range(1, declared + 1))
    if seq != expect:
        missing = sorted(set(expect) - set(seq))
        dup = sorted({n for n in seq if seq.count(n) > 1})
        extra = sorted(set(seq) - set(expect))
        order = [] if (missing or dup or extra) else [seq[i] for i in range(len(seq)) if seq[i] != i + 1][:5]
        parts = []
        if missing:
            parts.append(f"缺題號 {missing}")
        if dup:
            parts.append(f"重號 {dup}")
        if extra:
            parts.append(f"超出範圍 {extra}")
        if order:
            parts.append(f"順序不對（從 {order} 開始）")
        errs.append(f"{label} C2 題號母體不符（標示 {declared} 題，抓到 {len(seq)} 個）：{'；'.join(parts)}")
        return declared, [], errs

    qs = []
    for i, (n, s, e) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        body = text[e:end]
        page = text[:s].count("\f") + 1
        body_flat = re.sub(r"\s*\n\s*", "", body.replace("\f", ""))
        pos, opts, stem = 0, [], None
        bad = None
        for k in range(1, 5):
            j = body_flat.find(f"({k})", pos)
            if j < 0:
                bad = f"找不到選項 ({k})"
                break
            if k == 1:
                stem = body_flat[:j].strip()
            else:
                opts.append(body_flat[pos:j].strip())
            pos = j + len(f"({k})")
        if bad is None:
            opts.append(body_flat[pos:].strip())
            if "(5)" in body_flat:
                bad = "出現 (5)，不是四選一"
            elif any(body_flat.count(f"({k})") != 1 for k in range(1, 5)):
                bad = "選項標記出現不只一次（題幹或選項內文裡有 (1)～(4)）"
            elif not stem:
                bad = "題幹是空的"
            elif any(not o for o in opts):
                bad = f"選項 ({[k + 1 for k, o in enumerate(opts) if not o]}) 是空的"
        if bad:
            errs.append(f"{label} C3 第 {n} 題：{bad}")
            continue
        qs.append({"qno": n, "page": page, "stem": stem, "options": opts})
    return declared, qs, errs


# ------------------------------------------------------------------ 答案（兩條獨立讀法）
def answers_raw(raw: str):
    """A：-raw 每列「題號 第一節 第二節」或「題號 第二節」（51 題以後只有第二節）。"""
    rows = {}
    errs = []
    for ln in raw.splitlines():
        t = ln.split()
        if not t or not all(x.isdigit() for x in t) or len(t) not in (2, 3):
            continue
        q = int(t[0])
        vals = [int(x) for x in t[1:]]
        if len(vals) == 1:
            vals = [None, vals[0]]
        if q in rows:
            errs.append(f"A 讀法：題號 {q} 出現兩次")
        rows[q] = vals
    return rows, errs


def answers_simple(simple: str):
    """B：-simple 版面，依數字的水平位置分到「第一節」或「第二節」欄（跟 A 用不同的判斷方式）。"""
    lines = simple.splitlines()
    # 用 1～50 題那幾列（三個數字）量出兩欄答案的平均位置
    col_pos = [[], []]
    parsed = []
    for ln in lines:
        toks = [(m.start(), m.group()) for m in re.finditer(r"\d+", ln)]
        if not toks or re.search(r"[^\d\s　]", ln):
            continue
        parsed.append(toks)
        if len(toks) == 3:
            col_pos[0].append(toks[1][0])
            col_pos[1].append(toks[2][0])
    if not col_pos[0]:
        return {}, ["B 讀法：量不到答案欄位置"]
    c0 = sum(col_pos[0]) / len(col_pos[0])
    c1 = sum(col_pos[1]) / len(col_pos[1])
    rows, errs = {}, []
    for toks in parsed:
        q = int(toks[0][1])
        vals = [None, None]
        for x, v in toks[1:]:
            col = 0 if abs(x - c0) < abs(x - c1) else 1
            if vals[col] is not None:
                errs.append(f"B 讀法：題號 {q} 同一欄有兩個值")
            vals[col] = int(v)
        if q in rows:
            errs.append(f"B 讀法：題號 {q} 出現兩次")
        rows[q] = vals
    return rows, errs


def answer_meta(raw: str):
    # 標題那一行（-raw 模式下排在表格之後）：台灣金融研訓院【第N期…（一般金融類）】試題正確答案
    title = next((ln for ln in raw.splitlines() if "正確答案" in ln), "")
    m = re.search(r"第\s*(\d+)\s*期", title)
    period = int(m.group(1)) if m else None
    group = "消費金融" if "消費金融類" in title else ("一般金融" if "一般金融類" in title else None)
    d = re.search(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", raw)
    published = f"{int(d.group(1)) + 1911:04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else None
    return period, group, published


def check_answers(a_rows, b_rows, col, n, label):
    """C4～C7：回傳 ({題號: 答案}, [錯誤])。"""
    errs = []
    keyA = {q: v[col] for q, v in a_rows.items() if v[col] is not None}
    keyB = {q: v[col] for q, v in b_rows.items() if v[col] is not None}
    for name, key in (("A", keyA), ("B", keyB)):
        missing = [q for q in range(1, n + 1) if q not in key]
        extra = sorted(q for q in key if q > n or q < 1)
        bad = sorted(q for q, v in key.items() if v not in (1, 2, 3, 4))
        if missing:
            errs.append(f"{label} C4/C7 答案{name}缺題號 {missing}")
        if extra:
            errs.append(f"{label} C7 答案{name}多出題號 {extra}（試卷只有 {n} 題）")
        if bad:
            errs.append(f"{label} C4 答案{name}超出 1～4：" + "、".join(f"第 {q} 題＝{key[q]}" for q in bad))
    diff = [q for q in range(1, n + 1) if q in keyA and q in keyB and keyA[q] != keyB[q]]
    if diff:
        errs.append(f"{label} C6 兩種讀法答案不同：" + "、".join(f"第 {q} 題 A={keyA[q]} B={keyB[q]}" for q in diff))
    return keyA, errs


# ------------------------------------------------------------------ 轉一期
def convert_period(period, texts):
    """texts：{'law': raw, 'gen': raw, 'ans_raw': raw, 'ans_simple': simple}。回傳 ({科: [題]}, [錯誤])。"""
    errs = []
    ap, ag, published = answer_meta(texts["ans_raw"])
    if ap != period:
        errs.append(f"第{period}期 C8 答案卷標題的期別是 {ap}，跟試卷不符")
    if ag != "一般金融":
        errs.append(f"第{period}期 C8 答案卷的組別是 {ag}，不是一般金融")
    a_rows, ea = answers_raw(texts["ans_raw"])
    b_rows, eb = answers_simple(texts["ans_simple"])
    errs += [f"第{period}期 {e}" for e in ea + eb]
    out = {}
    for subj, zh in SUBJECTS.items():
        label = f"第{period}期{zh}"
        declared, qs, e = parse_paper(texts[subj], label)
        errs += e
        if declared is None or e:
            continue
        if len(qs) != declared:
            errs.append(f"{label} C7 轉出 {len(qs)} 題，試卷標示 {declared} 題")
            continue
        key, e2 = check_answers(a_rows, b_rows, ANSWER_COL[subj], declared, label)
        errs += e2
        if e2:
            continue
        for q in qs:
            q["answer"] = key[q["qno"]]
        out[subj] = {"questions": qs, "published": published}
    return out, errs


def read_texts(period):
    f = files_for(period)
    miss = [k for k, v in f.items() if v is None]
    if miss:
        return None, miss
    return {"law": pdftext(f["law"], "-raw"), "gen": pdftext(f["gen"], "-raw"),
            "ans_raw": pdftext(f["ans"], "-raw"), "ans_simple": pdftext(f["ans"], "-simple")}, []


# ------------------------------------------------------------------ 輸出
def render(period, subj, block):
    zh = SUBJECTS[subj]
    lines = [f"# TABF 第{period}期 銀行內部控制與內部稽核測驗（一般金融）— {zh}",
             "# 由 scripts/import_tabf.py 從官方 PDF 轉出；本機自用，不得入庫或公開。",
             f"# 答案以測驗當時法規為準；law_as_of 取答案卷的疑義申請起日（測驗後約兩天）。", ""]
    for q in block["questions"]:
        lines += [f"=== bic-{subj}-t{period}-{q['qno']:03d}",
                  "type: single",
                  f"chapter: bic.{subj}",
                  f"stem: {q['stem']}"]
        lines += [f"{k}: {o}" for k, o in zip("1234", q["options"])]
        lines += [f"answer: {q['answer']}",
                  "source: tabf-official",
                  f"period: {period}",
                  f"qno: {q['qno']}",
                  f"page: {q['page']}",
                  f"law_as_of: {block['published'] or '?'}",
                  ""]
    return "\n".join(lines)


def main(argv):
    check_only = "--check-only" in argv
    periods = None
    if "--periods" in argv:
        periods = [int(x) for x in argv[argv.index("--periods") + 1:] if x.isdigit()]
    todo = periods or available_periods()
    all_out, all_errs, skipped = {}, [], []
    for p in todo:
        texts, miss = read_texts(p)
        if texts is None:
            skipped.append(f"第{p}期（缺 {'、'.join({'law': '法規卷', 'gen': '一般金融實務卷', 'ans': '一般金融答案'}[m] for m in miss)}）")
            continue
        out, errs = convert_period(p, texts)
        all_errs += errs
        if not errs:
            all_out[p] = out
    for s in skipped:
        print(f"• 略過 {s}")
    if all_errs:
        print(f"IMPORT-TABF FAILED：{len(all_errs)} 項不符，一個檔都沒寫")
        for e in all_errs:
            print(f"  {e}")
        return 1
    if not all_out:
        print("IMPORT-TABF FAILED：沒有任何一期的試卷與答案齊全")
        return 1
    total = sum(len(b["questions"]) for o in all_out.values() for b in o.values())
    summary = "、".join(f"第{p}期 法規 {len(o['law']['questions'])}＋實務 {len(o['gen']['questions'])}" for p, o in sorted(all_out.items()))
    if check_only:
        print(f"IMPORT-TABF OK（只檢查）：{total} 題全部通過 C1～C8｜{summary}")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    pending = {OUT / f"tabf-p{p}-{s}.txt": render(p, s, b) for p, o in all_out.items() for s, b in o.items()}
    tmps = []
    for path, text in pending.items():
        tmp = path.with_suffix(".txt.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmps.append((tmp, path))
    for tmp, path in tmps:
        tmp.replace(path)
    print(f"IMPORT-TABF OK：{total} 題通過 C1～C8，寫出 {len(pending)} 個檔到 data/local/src/bic/｜{summary}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ConvertError as e:
        print(f"IMPORT-TABF ERROR：{e}")
        sys.exit(2)
