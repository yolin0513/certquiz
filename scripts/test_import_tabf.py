#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_tabf.py 的突變測試：證明每一道檢查真的會紅，而且紅的理由點名正確的題號
------------------------------------------------------------------------------
用真的官方 PDF 抽出的文字（第 49 期一般金融），在記憶體裡故意改壞一處，丟進 convert_period，
要求：有錯誤、而且錯誤訊息裡點名了預期的那一題。另外驗證：有錯的時候 main 一個檔都不寫。
需要 refs/ 底下的 PDF（本機才有，不入庫），所以這支只能在本機跑。

結束碼：0 全部符合；1 有不符；2 前提不成立（PDF 不在、原樣就有錯）。
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_tabf as T  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

P = 49


def names_q(errs, label_part, q):
    """錯誤訊息裡有沒有「這一科」而且點名「第 q 題」或在題號清單裡出現 q。"""
    pat = re.compile(rf"(第 {q} 題|[\[ ,]{q}[\],]|題號 {q}\b)")
    return any(label_part in e and pat.search(e) for e in errs)


def mut_marker(text, q, new):
    """把行首的題號 q. 改成 new（new=None 表示拿掉題號，等於這一題不見）。"""
    pat = re.compile(rf"(?m)^(\f?){q}\.(?=\D)")
    assert len(pat.findall(text)) == 1, f"題號 {q} 不是剛好一個"
    return pat.sub(lambda m: m.group(1) + ("" if new is None else f"{new}."), text, count=1)


def question_span(text, q):
    s = re.search(rf"(?m)^\f?{q}\.(?=\D)", text).start()
    e = re.search(rf"(?m)^\f?{q + 1}\.(?=\D)", text)
    return s, (e.start() if e else len(text))


def set_raw_answer(raw, q, col, value):
    lines = raw.split("\n")
    for i, ln in enumerate(lines):
        t = ln.split()
        if t and t[0] == str(q) and all(x.isdigit() for x in t) and len(t) in (2, 3):
            idx = 1 + col if len(t) == 3 else 1
            t[idx] = str(value)
            lines[i] = " ".join(t)
            return "\n".join(lines)
    raise AssertionError(f"答案 A 找不到第 {q} 列")


def drop_answer_row(text, q):
    out = [ln for ln in text.split("\n") if not (ln.split() and ln.split()[0] == str(q) and all(x.isdigit() for x in ln.split()))]
    assert len(out) == len(text.split("\n")) - 1, f"第 {q} 列不是剛好一列"
    return "\n".join(out)


def main():
    texts, miss = T.read_texts(P)
    if texts is None:
        print(f"TEST-IMPORT ABORT：第{P}期 PDF 不齊（{miss}）")
        return 2
    base_out, base_errs = T.convert_period(P, texts)
    if base_errs or len(base_out.get("law", {}).get("questions", [])) != 50:
        print(f"TEST-IMPORT ABORT：原樣就不過，無法做突變：{base_errs[:3]}")
        return 2
    print(f"✓ 原樣：第{P}期 法規 50＋實務 80 全部通過")
    keyA, _ = T.answers_raw(texts["ans_raw"])
    law_ans = {q: v[0] for q, v in keyA.items() if v[0]}
    gen_ans = {q: v[1] for q, v in keyA.items() if v[1]}
    k_law = next(q for q in range(1, 50) if law_ans[q] != law_ans[q + 1])    # 錯位一格會變的那一題
    k_gen = next(q for q in range(60, 80) if gen_ans[q] != gen_ans[q + 1])

    def shift_col_A(raw, col, n):
        """整欄錯位一列（像 -table 模式實際發生的那樣）：第 q 題拿到第 q+1 題的答案。"""
        for q in range(1, n):
            raw = set_raw_answer(raw, q, col, keyA[q + 1][col])
        return raw

    def law_s(q, k):  # 拿掉第 q 題的選項 (k)
        s, e = question_span(texts["law"], q)
        seg = texts["law"][s:e]
        assert seg.count(f"({k})") == 1
        return texts["law"][:s] + seg.replace(f"({k})", "", 1) + texts["law"][e:]

    def law_stem_inject(q):
        s, e = question_span(texts["law"], q)
        seg = texts["law"][s:e]
        dot = seg.index(".") + 1
        return texts["law"][:s] + seg[:dot] + "依下列(2)款規定，" + seg[dot:] + texts["law"][e:]

    cases = [
        # (說明, 要改的欄位, 改法, 預期點名的科目字樣, 預期題號)
        ("法規第 12 題整題不見（缺號）", "law", lambda: mut_marker(texts["law"], 12, None), "法規 C2", 12),
        ("實務第 31 題的題號被讀成 30（重號）", "gen", lambda: mut_marker(texts["gen"], 31, 30), "實務 C2", 30),
        ("法規第 7 題少了選項 (3)", "law", lambda: law_s(7, 3), "法規 C3", 7),
        ("法規第 9 題題幹裡出現 (2)（選項標記重複）", "law", lambda: law_stem_inject(9), "法規 C3", 9),
        ("答案 A：法規第 15 題的答案變成 5", "ans_raw", lambda: set_raw_answer(texts["ans_raw"], 15, 0, 5), "法規 C4", 15),
        (f"答案 A：法規第 {k_law} 題錯位一格（拿到第 {k_law + 1} 題的答案）", "ans_raw",
         lambda: set_raw_answer(texts["ans_raw"], k_law, 0, law_ans[k_law + 1]), "法規 C6", k_law),
        (f"答案 A：實務第 {k_gen} 題錯位一格", "ans_raw",
         lambda: set_raw_answer(texts["ans_raw"], k_gen, 1, gen_ans[k_gen + 1]), "實務 C6", k_gen),
        ("答案 A：實務整欄錯位一列（-table 模式實際出過的錯）", "ans_raw",
         lambda: shift_col_A(texts["ans_raw"], 1, 80), "實務 C", next(q for q in range(1, 80) if gen_ans[q] != gen_ans[q + 1])),
        ("答案 A 與 B 都少了第 80 列（母體）", None, None, "實務 C4/C7", 80),
        ("答案卷標題是別的期別", "ans_raw", lambda: texts["ans_raw"].replace(f"【第{P}期", "【第48期"), "C8", None),
        ("消費金融答案卷的法規第 30 題跟一般金融不同（C9）", "ans_con_raw",
         lambda: set_raw_answer(texts["ans_con_raw"], 30, 0, law_ans[30] % 4 + 1), "法規 C9", 30),
    ]
    if not texts.get("ans_con_raw"):
        print(f"TEST-IMPORT ABORT：第{P}期沒有消費金融答案卷，驗不了 C9")
        return 2

    fails = 0
    for desc, field, fn, label_part, q in cases:
        t2 = dict(texts)
        if field is None:   # 兩種讀法都少一列
            t2["ans_raw"] = drop_answer_row(texts["ans_raw"], 80)
            t2["ans_simple"] = drop_answer_row(texts["ans_simple"], 80)
        else:
            t2[field] = fn()
            assert t2[field] != texts[field], f"突變沒有生效：{desc}"
        _out, errs = T.convert_period(P, t2)
        ok = bool(errs) and (q is None and any(label_part in e for e in errs) or q is not None and names_q(errs, label_part, q))
        print(f"{'✓' if ok else '✗'} {desc}：{'紅、點名正確' if ok else '沒紅或沒點名'}")
        if not ok:
            fails += 1
            for e in errs[:4]:
                print(f"    {e}")

    # 有錯就一個檔都不寫——包括「同一次執行裡其他期別是好的」：不准只寫好的那幾期（部分寫入）
    good_p = 48
    good_texts, gmiss = T.read_texts(good_p)
    if good_texts is None:
        print(f"TEST-IMPORT ABORT：第{good_p}期 PDF 不齊（{gmiss}），驗不了部分寫入")
        return 2
    with tempfile.TemporaryDirectory(prefix="certquiz-import-") as tmp:
        orig_read, orig_out, orig_rep = T.read_texts, T.OUT, T.REPORT
        try:
            bad = dict(texts)
            bad["ans_raw"] = set_raw_answer(texts["ans_raw"], k_law, 0, law_ans[k_law + 1])
            T.read_texts = lambda p, src="official": ((bad, []) if p == P else ((good_texts, []) if p == good_p else (None, ["x"]))) if src == "official" else (None, ["x"])
            T.OUT = Path(tmp) / "out"
            T.REPORT = Path(tmp) / "report.md"
            rc = T.main(["--periods", str(good_p), str(P)])
            written = [p for p in Path(tmp).rglob("*") if p.is_file()]
            ok = rc == 1 and not written
            print(f"{'✓' if ok else '✗'} 第{good_p}期好、第{P}期壞時一個檔都不寫：回傳 {rc}，寫出 {len(written)} 個檔")
            fails += 0 if ok else 1
        finally:
            T.read_texts, T.OUT, T.REPORT = orig_read, orig_out, orig_rep

    if fails:
        print(f"TEST-IMPORT FAILED：{fails} 項不符")
        return 1
    print(f"TEST-IMPORT OK：{len(cases)} 個突變全部紅且點名正確＋有錯不寫檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
