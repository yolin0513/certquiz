#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
題庫建置
--------
兩條輸出，分開跑、互不混用：

1) 公開（預設）：data/src/ → data/manifest.json、data/q/<證照>.json（入庫、部署到網站）
   - 只收原創題；看到 source: tabf-official／user-import 一律拒絕建置（版權防線，見 docs/STATUS.md）
   - AZ-900 的題目 source 必須是 original-*
2) 本機（--local）：data/local/src/<證照>/*.txt → data/local/import/<證照>-匯入包.json（不入庫、不部署）
   - 給使用者傳到自己手機、在 App「匯入題目」選檔用
   - 去重：題幹＋四個選項逐字相同視為同一題，保留期別最新的那一題，其他標 dupOf（練習時隱藏，紀錄仍解析得到）

題目原始檔格式（一題一區塊）：
    === <id>
    type: single
    chapter: <證照>.<科目>
    stem: 題幹
    1: 選項一        （或 A: …；同一題內要一致）
    2: …
    3: …
    4: …
    answer: 2
    source: original-ai | original-human | tabf-official | user-import
    （其他欄位：period、qno、page、law_as_of、basis、explain、status）

寫檔前全部檢查完：任何一題不過就點名 id、結束碼 1、一個檔都不寫。
用法：
    python scripts/build_data.py            # 公開
    python scripts/build_data.py --local    # 本機匯入包
    python scripts/build_data.py --check    # 兩條都只檢查、不寫檔
"""
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "src"
OUT = ROOT / "data"
LOCAL_SRC = ROOT / "data" / "local" / "src"
LOCAL_OUT = ROOT / "data" / "local" / "import"
IMPORT_FORMAT = "certquiz-import"
IMPORT_VERSION = 1

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
PUBLIC_SOURCES = {"original-ai", "original-human"}
LOCAL_SOURCES = {"tabf-official", "user-import"}
OPTION_KEYS = [("1", "2", "3", "4"), ("A", "B", "C", "D")]


class BuildError(Exception):
    pass


def parse_blocks(path: Path):
    """回傳 [(行號, dict)]。dict 的鍵：id 與各欄位（字串）。"""
    text = path.read_text(encoding="utf-8")
    out, cur, start = [], None, 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("=== "):
            if cur is not None:
                out.append((start, cur))
            cur, start = {"id": line[4:].strip()}, i
        elif cur is not None and ": " in line and not line.startswith("#"):
            k, v = line.split(": ", 1)
            if k in cur:
                cur.setdefault("_dupfields", []).append(k)
            cur[k] = v.strip()
    if cur is not None:
        out.append((start, cur))
    return out


def norm_ws(s):
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ").replace("\u200b", "")).strip()


def basis_hash(quote):
    """與 verify_basis.qhash 相同：空白正規化後的 sha256。"""
    return hashlib.sha256(norm_ws(quote).encode("utf-8")).hexdigest()


def norm_key(q):
    return q["stem"] + "|" + "|".join(q["options"])


def validate(q, where, cert_ids, mode):
    """回傳 (正規化後的題目 dict, [錯誤])。"""
    errs = []
    qid = q.get("id", "")
    tag = f"{where} {qid or '(沒有 id)'}"
    if not ID_RE.match(qid):
        errs.append(f"{tag}：id 格式不對（小寫英數與連字號）")
    if q.get("_dupfields"):
        errs.append(f"{tag}：欄位重複出現 {q['_dupfields']}")
    if q.get("type", "single") != "single":
        errs.append(f"{tag}：M1 只支援 type: single，拿到 {q.get('type')}")
    keys = next((ks for ks in OPTION_KEYS if all(k in q for k in ks)), None)
    if keys is None:
        errs.append(f"{tag}：選項不完整（要 1～4 或 A～D 四個）")
        options = []
    else:
        options = [q[k] for k in keys]
        if any(not o for o in options):
            errs.append(f"{tag}：有空的選項")
        if len(set(options)) != 4:
            errs.append(f"{tag}：選項內容重複")
    stem = q.get("stem", "")
    if not stem:
        errs.append(f"{tag}：題幹是空的")
    ans = q.get("answer", "")
    if keys and ans not in keys:
        errs.append(f"{tag}：答案 {ans!r} 不在選項 {list(keys)} 裡")
    chapter = q.get("chapter", "")
    cert = chapter.split(".")[0] if chapter else ""
    if cert not in cert_ids:
        errs.append(f"{tag}：chapter {chapter!r} 的證照不存在")
    if not qid.startswith(cert + "-"):
        errs.append(f"{tag}：id 開頭跟 chapter 的證照 {cert!r} 不一致")
    src = q.get("source", "")
    if mode in ("public", "draft"):
        if src in LOCAL_SOURCES:
            errs.append(f"{tag}：source {src} 只能留在本機，不得進公開題庫")
        elif src not in PUBLIC_SOURCES:
            errs.append(f"{tag}：公開題庫的 source 必須是 {sorted(PUBLIC_SOURCES)}，拿到 {src!r}")
    else:
        if src not in LOCAL_SOURCES:
            errs.append(f"{tag}：本機匯入包的 source 必須是 {sorted(LOCAL_SOURCES)}，拿到 {src!r}")
    if cert == "bic" and not re.match(r"^\d{4}-\d{2}-\d{2}$", q.get("law_as_of", "")):
        errs.append(f"{tag}：內控題必須有 law_as_of（YYYY-MM-DD）")
    if cert == "az900":
        # 原創題的真值在官方文件上（docs/I_原創題的真值.md）：缺任何一個依據欄位就不收
        n_skills = OBJECTIVES.get("az900", {}).get(q.get("objective", ""))
        if n_skills is None:
            errs.append(f"{tag}：objective {q.get('objective')!r} 不是官方大綱的節次")
        elif not (q.get("skill", "").isdigit() and 1 <= int(q["skill"]) <= n_skills):
            errs.append(f"{tag}：skill {q.get('skill')!r} 必須是 {q.get('objective')} 底下第 1～{n_skills} 個官方細項")
        if not q.get("basis", "").startswith("https://learn.microsoft.com/en-us/"):
            errs.append(f"{tag}：basis 必須是 https://learn.microsoft.com/en-us/ 的官方文件網址")
        # 原文只留本機（Dispatch 2026-10-08）：公開題目檔只存定位資訊；草稿要有原文，而且定位資訊要跟原文對得上
        quote = q.get("basis_quote", "")
        if mode == "public" and quote:
            errs.append(f"{tag}：公開題目檔不得含 basis_quote（原文只留本機，放 data/local/basis/）")
        if mode == "draft":
            if not 20 <= len(quote) <= 400:
                errs.append(f"{tag}：草稿必須有 basis_quote（那頁逐字摘錄的原文，20～400 字元）")
            elif q.get("basis_hash") != basis_hash(quote) or q.get("basis_len") != str(len(norm_ws(quote))):
                errs.append(f"{tag}：basis_hash／basis_len 跟 basis_quote 對不上（改過原文要重跑 verify_basis.py --fill）")
        if not re.fullmatch(r"[0-9a-f]{64}", q.get("basis_hash", "")) or not q.get("basis_len", "").isdigit():
            errs.append(f"{tag}：缺 basis_hash（原文 sha256）或 basis_len（原文字數）")
        anchor = q.get("basis_anchor", "")
        if not anchor.startswith("#") or (anchor != "#" and not q.get("basis_section")):
            errs.append(f"{tag}：缺 basis_anchor（章節錨點，頁首用 #）或 basis_section（章節標題）")
        if not q.get("explain"):
            errs.append(f"{tag}：缺 explain（解析）")
    out = {
        "id": qid, "cert": cert, "subject": chapter.split(".")[1] if "." in chapter else "",
        "chapter": chapter, "type": "single", "stem": stem, "options": options,
        "answer": (keys.index(ans) + 1) if keys and ans in keys else None,
        "source": src,
    }
    for k in ("period", "qno", "page", "skill"):
        if q.get(k, "").isdigit():
            out[k] = int(q[k])
    # basis_quote（原文）與 basis_hash／basis_len 只供核對，不輸出到 App
    for k in ("law_as_of", "basis", "basis_anchor", "basis_section", "objective", "explain", "status"):
        if q.get(k):
            out[k] = q[k]
    return out, errs


OBJECTIVES = {}


def load_certs():
    data = json.loads((SRC / "certs.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in data["certs"]]
    if len(ids) != len(set(ids)):
        raise BuildError(f"certs.json 的證照 id 重複：{ids}")
    OBJECTIVES.clear()
    for c in data["certs"]:
        if c.get("syllabus"):
            OBJECTIVES[c["id"]] = {o["id"]: len(o.get("skills", [])) for o in c["syllabus"]["objectives"]}
    return data["certs"]


def coverage(certs, qs):
    """AZ-900 出題進度：每個節次 已出／配額，以及還沒出過題的官方細項（docs/J_AZ900出題配額.md）。"""
    syl = next((c.get("syllabus") for c in certs if c["id"] == "az900"), None)
    if not syl:
        return []
    az = [q for q in qs if q["cert"] == "az900"]
    lines = [f"AZ-900 進度：{len(az)}／{syl.get('total', '?')} 題"]
    for o in syl["objectives"]:
        mine = [q for q in az if q.get("objective") == o["id"]]
        hit = {q.get("skill") for q in mine}
        empty = [str(i) for i in range(1, len(o.get("skills", [])) + 1) if int(i) not in hit]
        over = "（超過配額）" if len(mine) > o.get("quota", 0) else ""
        lines.append(f"  {o['id']} {len(mine):>3}／{o.get('quota', '?'):<3}{over} 還沒出到的細項：{'、'.join(empty) or '無'}")
    return lines


def check_draft(certs, draft_dir: Path):
    """草稿（還沒進 repo 的題目檔）：用公開題庫的規則檢查，不寫任何檔。"""
    cert_ids = {c["id"] for c in certs}
    files, qs, errs = collect(draft_dir, cert_ids, "draft")
    for q in qs:
        if q["cert"] == "az900" and not q["source"].startswith("original-"):
            errs.append(f"{q['id']}：AZ-900 只能收原創題")
    return files, qs, errs


def collect(root: Path, cert_ids, mode):
    qs, errs, seen = [], [], {}
    files = sorted(root.glob("*/*.txt")) if root.exists() else []
    for f in files:
        rel = (f.relative_to(ROOT) if f.is_relative_to(ROOT) else f.relative_to(root.parent)).as_posix()
        for line, raw in parse_blocks(f):
            q, e = validate(raw, f"{rel}:{line}", cert_ids, mode)
            errs += e
            if q["id"] in seen:
                errs.append(f"{rel}:{line} {q['id']}：id 重複（先前在 {seen[q['id']]}）")
            seen[q["id"]] = f"{rel}:{line}"
            qs.append(q)
    return files, qs, errs


def mark_dups(qs):
    """同一組（題幹＋選項逐字相同）保留期別最新的一題；其他加 dupOf。回傳 (組數, 被標的題數)。"""
    groups = {}
    for q in qs:
        groups.setdefault((q["cert"], norm_key(q)), []).append(q)
    n_groups = n_marked = 0
    for g in groups.values():
        if len(g) < 2:
            continue
        n_groups += 1
        keep = max(g, key=lambda q: (q.get("period", 0), q["id"]))
        for q in g:
            if q is not keep:
                q["dupOf"] = keep["id"]
                n_marked += 1
    return n_groups, n_marked


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def commit(pending):
    """先全部寫 .tmp，全部成功才換上；任何一步失敗就清掉自己寫的暫存檔、不換任何一個。"""
    tmps = []
    try:
        for path, text in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            tmps.append((tmp, path))
    except OSError as e:
        for tmp, _ in tmps:
            tmp.unlink(missing_ok=True)
        raise BuildError(f"寫暫存檔失敗，一個檔都沒換上：{e}")
    for tmp, path in tmps:
        tmp.replace(path)


def build_public(certs, check_only):
    cert_ids = {c["id"] for c in certs}
    files, qs, errs = collect(SRC, cert_ids, "public")
    for q in qs:
        if q["cert"] == "az900" and not q["source"].startswith("original-"):
            errs.append(f"{q['id']}：AZ-900 只能收原創題")
    if errs:
        return None, errs
    by_cert = {}
    for q in qs:
        by_cert.setdefault(q["cert"], []).append(q)
    pending = {}
    for cid, items in by_cert.items():
        pending[OUT / "q" / f"{cid}.json"] = dump({"cert": cid, "questions": items})
    digest = hashlib.sha1("".join(pending[k] for k in sorted(pending)).encode("utf-8")).hexdigest()[:12]
    manifest = {
        "app": "CertQuiz",
        "dataVersion": digest,
        "certs": [dict(c, bundledCount=len(by_cert.get(c["id"], [])),
                       bundledFile=f"data/q/{c['id']}.json" if c["id"] in by_cert else None) for c in certs],
    }
    pending[OUT / "manifest.json"] = dump(manifest)
    summary = "、".join(f"{c['short']} {len(by_cert.get(c['id'], []))} 題" for c in certs)
    if not check_only:
        commit(pending)
    return f"公開題庫：{len(files)} 個原始檔｜{summary}｜dataVersion {digest}", []


def build_local(certs, check_only):
    cert_ids = {c["id"] for c in certs}
    files, qs, errs = collect(LOCAL_SRC, cert_ids, "local")
    if errs:
        return None, errs
    if not qs:
        return "本機匯入包：沒有本機題目（data/local/src/ 是空的），略過", []
    pending, parts = {}, []
    for cid in sorted({q["cert"] for q in qs}):
        items = [q for q in qs if q["cert"] == cid]
        n_groups, n_marked = mark_dups(items)
        active = len(items) - n_marked
        pack = {
            "format": IMPORT_FORMAT, "version": IMPORT_VERSION, "cert": cid,
            "generated": date.today().isoformat(),
            "counts": {"total": len(items), "active": active, "dupGroups": n_groups, "dupMarked": n_marked,
                       "bySource": {s: sum(1 for q in items if q["source"] == s) for s in sorted({q["source"] for q in items})}},
            "notice": "本機自用：題目來自使用者自行取得的官方歷屆試題 PDF。不得上傳、不得散布。",
            "questions": items,
        }
        name = next(c["short"] for c in certs if c["id"] == cid)
        pending[LOCAL_OUT / f"{cid}-匯入包.json"] = dump(pack)
        parts.append(f"{name} 全部 {len(items)} 題、去重後可練 {active} 題（重複 {n_groups} 組、隱藏 {n_marked} 題）")
    if not check_only:
        commit(pending)
    return f"本機匯入包：{len(files)} 個原始檔｜" + "；".join(parts), []


def main(argv):
    check_only = "--check" in argv
    try:
        certs = load_certs()
        if "--draft" in argv:
            d = Path(argv[argv.index("--draft") + 1])
            files, qs, errs = check_draft(certs, d)
            if not qs:
                # 0 題不是「全部符合」：多半是目錄給錯（要給 <cert>/*.txt 的上一層）。常設規則 15。
                print(f"DRAFT ABORT：{d} 底下沒有找到任何題目（應為 {d}/<證照>/*.txt）——0 題不能算通過")
                return 2
            if errs:
                print(f"DRAFT FAILED：{len(errs)} 項")
                for e in errs:
                    print(f"  {e}")
                return 1
            print(f"DRAFT OK：{len(files)} 個檔、{len(qs)} 題，全部符合公開題庫規則（含 AZ-900 依據欄位）")
            _, pub, _ = collect(SRC, {c["id"] for c in certs}, "public")
            ids = {q["id"] for q in pub}
            dup = [q["id"] for q in qs if q["id"] in ids]
            if dup:
                print(f"DRAFT FAILED：草稿的 id 跟已入庫的題目重複：{dup}")
                return 1
            print(f"（進度含已入庫 {len(pub)} 題＋草稿 {len(qs)} 題）")
            for ln in coverage(certs, pub + qs):
                print(ln)
            return 0
        runs = [("public", build_public), ("local", build_local)] if check_only else \
               ([("local", build_local)] if "--local" in argv else [("public", build_public)])
        failed = False
        for name, fn in runs:
            msg, errs = fn(certs, check_only)
            if errs:
                failed = True
                print(f"BUILD FAILED（{'公開' if name == 'public' else '本機'}）：{len(errs)} 項，一個檔都沒寫")
                for e in errs:
                    print(f"  {e}")
            else:
                print(f"BUILD OK{'（只檢查）' if check_only else ''}：{msg}")
        return 1 if failed else 0
    except BuildError as e:
        print(f"BUILD ERROR：{e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
