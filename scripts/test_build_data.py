#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py 的測試：每一條拒絕規則用假樣本證明會擋、而且點名那一題；去重方向；有錯不寫檔。
全部在暫存目錄裡做（把 build_data 的 SRC／OUT／LOCAL_SRC／LOCAL_OUT 指過去），不碰真的 data/。
結束碼：0 全部符合；1 有不符。
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_data as B  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

REAL_CERTS = (B.ROOT / "data" / "src" / "certs.json").read_text(encoding="utf-8")


def block(qid, chapter, stem, opts, ans, source, **extra):
    lines = [f"=== {qid}", "type: single", f"chapter: {chapter}", f"stem: {stem}"]
    lines += [f"{k}: {o}" for k, o in zip("1234", opts)]
    lines += [f"answer: {ans}", f"source: {source}"] + [f"{k}: {v}" for k, v in extra.items()] + [""]
    return "\n".join(lines)


QUOTE = "This is a verbatim sentence copied from the cited page."
# 公開題目檔：只有定位資訊（錨點、章節、雜湊、字數），沒有原文
GOOD_AZ = block("az900-a-o-0001", "az900.all", "Which is a benefit of cloud?", ["High availability", "Lock-in", "CapEx only", "None"], 1, "original-ai",
                objective="A.2", skill="1", basis="https://learn.microsoft.com/en-us/azure/example-page",
                basis_anchor="#overview", basis_section="Overview", basis_hash=B.basis_hash(QUOTE), basis_len=str(len(QUOTE)),
                explain="解析。")
# 草稿：同一題再加原文
GOOD_AZ_DRAFT = GOOD_AZ.replace("explain: ", f"basis_quote: {QUOTE}\nexplain: ")
GOOD_BIC_47 = block("bic-law-t47-001", "bic.law", "同一題", ["甲", "乙", "丙", "丁"], 2, "tabf-official", period=47, law_as_of="2025-03-17")
GOOD_BIC_40 = block("bic-law-u40-007", "bic.law", "同一題", ["甲", "乙", "丙", "丁"], 2, "user-import", period=40, law_as_of="2021-11-22")


def run_case(desc, public_files, local_files, mode, expect_ok, expect_ids=(), check=None):
    tmp = Path(tempfile.mkdtemp(prefix="certquiz-build-"))
    saved = (B.SRC, B.OUT, B.LOCAL_SRC, B.LOCAL_OUT)
    try:
        (tmp / "src").mkdir()
        (tmp / "src" / "certs.json").write_text(REAL_CERTS, encoding="utf-8")
        for rel, text in public_files.items():
            p = tmp / "src" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        for rel, text in local_files.items():
            p = tmp / "lsrc" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        B.SRC, B.OUT, B.LOCAL_SRC, B.LOCAL_OUT = tmp / "src", tmp / "out", tmp / "lsrc", tmp / "lout"
        certs = B.load_certs()
        fn = B.build_public if mode == "public" else B.build_local
        msg, errs = fn(certs, False)
        written = [p for p in list((tmp / "out").rglob("*")) + list((tmp / "lout").rglob("*")) if p.is_file()] \
            if (tmp / "out").exists() or (tmp / "lout").exists() else []
        if expect_ok:
            ok = not errs and bool(written) and (check is None or check(tmp))
        else:
            ok = bool(errs) and not written and all(any(i in e for e in errs) for i in expect_ids)
        print(f"{'✓' if ok else '✗'} {desc}：{'通過' if not errs else '擋下'}，寫出 {len(written)} 個檔")
        if not ok:
            for e in errs[:3]:
                print(f"    {e}")
        return ok
    finally:
        B.SRC, B.OUT, B.LOCAL_SRC, B.LOCAL_OUT = saved
        shutil.rmtree(tmp, ignore_errors=False)


def dedup_check(tmp):
    pack = json.loads((tmp / "lout" / "bic-匯入包.json").read_text(encoding="utf-8"))
    by = {q["id"]: q for q in pack["questions"]}
    return (by["bic-law-u40-007"].get("dupOf") == "bic-law-t47-001" and "dupOf" not in by["bic-law-t47-001"]
            and pack["counts"]["active"] == 1 and pack["counts"]["total"] == 2)


def draft_dir_cases():
    """--draft：給對目錄要讀到題；給錯一層（0 題）不能算通過；草稿要有原文且雜湊對得上。"""
    def run(text, sub=""):
        tmp = Path(tempfile.mkdtemp(prefix="certquiz-draft-"))
        try:
            (tmp / "az900").mkdir()
            (tmp / "az900" / "a.txt").write_text(text, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = B.main(["--draft", str(tmp / sub) if sub else str(tmp)])
            return rc, buf.getvalue()
        finally:
            shutil.rmtree(tmp)
    rows = [
        ("--draft 給對目錄 → 通過", run(GOOD_AZ_DRAFT), 0, "DRAFT OK"),
        ("--draft 給錯一層、0 題 → 不能算通過", run(GOOD_AZ_DRAFT, "az900"), 2, "DRAFT ABORT"),
        ("草稿缺原文 → 擋", run(GOOD_AZ), 1, "草稿必須有 basis_quote"),
        ("草稿原文改了一個字、雜湊沒重算 → 擋", run(GOOD_AZ_DRAFT.replace("verbatim", "verbatum")), 1, "對不上"),
    ]
    ok_all = True
    for desc, (rc, out), want, why in rows:
        ok = rc == want and why in out
        ok_all &= ok
        print(f"{'✓' if ok else '✗'} {desc}：結束碼 {rc}（應 {want}）")
    return ok_all


def main():
    cases = [
        ("原樣：公開 AZ-900 原創題", {"az900/a.txt": GOOD_AZ}, {}, "public", True),
        ("原樣：本機匯入包", {}, {"bic/a.txt": GOOD_BIC_47}, "local", True),
        ("公開題庫混進 tabf-official 的題 → 擋、點名", {"bic/x.txt": GOOD_BIC_47}, {}, "public", False, ["bic-law-t47-001"]),
        ("公開題庫混進 user-import 的題 → 擋、點名", {"bic/x.txt": GOOD_BIC_40}, {}, "public", False, ["bic-law-u40-007"]),
        ("AZ-900 的 source 不是 original-* → 擋", {"az900/a.txt": GOOD_AZ.replace("original-ai", "vendor-dump")}, {}, "public", False, ["az900-a-o-0001"]),
        ("兩個檔有同一個 id → 擋、點名", {"az900/a.txt": GOOD_AZ, "az900/b.txt": GOOD_AZ}, {}, "public", False, ["az900-a-o-0001"]),
        ("答案不在選項裡 → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("answer: 1", "answer: 5")}, {}, "public", False, ["az900-a-o-0001"]),
        ("少一個選項 → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("4: None\n", "")}, {}, "public", False, ["az900-a-o-0001"]),
        ("內控題缺 law_as_of → 擋、點名", {}, {"bic/a.txt": GOOD_BIC_47.replace("law_as_of: 2025-03-17\n", "")}, "local", False, ["bic-law-t47-001"]),
        ("本機匯入包混進原創題 → 擋", {}, {"bic/a.txt": GOOD_BIC_47.replace("tabf-official", "original-ai")}, "local", False, ["bic-law-t47-001"]),
        ("去重：40 期與 47 期同一題 → 保留 47 期、40 期標 dupOf", {}, {"bic/a.txt": GOOD_BIC_40, "bic/b.txt": GOOD_BIC_47}, "local", True, (), dedup_check),
        ("公開題目檔夾帶原文 basis_quote → 擋、點名（原文只留本機）", {"az900/a.txt": GOOD_AZ_DRAFT}, {}, "public", False, ["az900-a-o-0001"]),
        ("AZ-900 缺 basis_hash → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("basis_hash: ", "x_hash: ")}, {}, "public", False, ["az900-a-o-0001"]),
        ("AZ-900 缺 basis_anchor → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("basis_anchor: #overview\n", "")}, {}, "public", False, ["az900-a-o-0001"]),
        ("AZ-900 的 basis 不是 learn.microsoft.com → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("https://learn.microsoft.com/en-us/azure/example-page", "https://example.com/x")}, {}, "public", False, ["az900-a-o-0001"]),
        ("AZ-900 的 objective 不在官方大綱 → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("objective: A.2", "objective: Z.9")}, {}, "public", False, ["az900-a-o-0001"]),
        ("AZ-900 的 skill 超出該節次的官方細項數 → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("skill: 1", "skill: 5")}, {}, "public", False, ["az900-a-o-0001"]),
        ("解析的「選項 N」點到正解 → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("explain: 解析。", "explain: 解析（選項 1、3 錯）。")}, {}, "public", False, ["az900-a-o-0001"]),
        ("解析的「選項 N」只點錯誤選項 → 通過", {"az900/a.txt": GOOD_AZ.replace("explain: 解析。", "explain: 解析（選項 2、3 錯）。")}, {}, "public", True),
        ("AZ-900 缺 skill → 擋、點名", {"az900/a.txt": GOOD_AZ.replace("skill: 1\n", "")}, {}, "public", False, ["az900-a-o-0001"]),
        ("一題有錯、其他題都對 → 一個檔都不寫", {"az900/a.txt": GOOD_AZ, "az900/b.txt": GOOD_AZ.replace("az900-a-o-0001", "az900-a-o-0002").replace("answer: 1", "answer: 9")}, {}, "public", False, ["az900-a-o-0002"]),
    ]
    fails = sum(0 if run_case(*c) else 1 for c in cases)
    fails += 0 if draft_dir_cases() else 1
    if fails:
        print(f"TEST-BUILD FAILED：{fails} 項不符")
        return 1
    print(f"TEST-BUILD OK：{len(cases) + 4} 項全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
