#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材「乙」的依據：哪些題指得出外部依據（法規條文寫出了正解的關鍵內容），才寫說明；指不出來的留白（使用者 2026-10-13 選乙）
-------------------------------------------------------------------------------
  python -u scripts/textbook_basis.py sheet T08     抓該章候選題考試當時的法規版本（全國法規資料庫，公開頁面），寫判定單
  python -u scripts/textbook_basis.py lock me|agent 鎖定判斷檔（雜湊進 data/local/教材/log.tsv）
  python -u scripts/textbook_basis.py merge T08     兩個判斷者都說「對得上」而且條號相同的，才算有依據 → basis-T08.json

候選題＝題幹點名法規、而且查得到考試當時那一版的題（docs/K 第 3 步的 eligible()）。題幹沒點名法規的題不去猜是哪一部（留白）。
判準同 docs/K 第 3 步：那一版裡有一條的條文寫出了正解的關鍵內容，而且對正解的支持高於對每一個錯誤選項。
依據的條文原文照抄全文檔（每一版的全文檔就是快照，常設規則 21）；說明只多一句把條文接到答案的話，標明是我們寫的。
兩個判斷者都是 Claude（我＋另一個獨立代理），一致不等於對，照實寫。
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
import law_coverage as LC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "local" / "教材"
LOG = D / "log.tsv"
PACK = ROOT / "data" / "local" / "import" / "bic-匯入包.json"
TOPICS = ROOT / "data" / "local" / "study" / "topics.json"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(action, p):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\t{action}\t{p.name}\t{sha(p)}\n")


def logged(action, name):
    if not LOG.exists():
        return []
    return [l.split("\t")[3].strip() for l in LOG.read_text(encoding="utf-8").splitlines() if l.split("\t")[1:3] == [action, name]]


def judges(topic):
    """信用卡章（草稿）是我＋一個代理；全量起（docs/M）兩個判斷者都是獨立代理 a、b。"""
    return ("me", "agent") if topic == "T08" else ("a", "b")


def paths(topic):
    return D / f"basis-{topic}-sheet.md", {w: D / f"basis-{topic}-judge-{w}.tsv" for w in judges(topic)}, D / f"basis-{topic}.json"


def candidates(topic):
    # 章：全量起用逐題歸章的結果（chapters-bic.json）；信用卡章草稿當時用的是關鍵字規則
    chf = D / "chapters-bic.json"
    tp = json.loads(chf.read_text(encoding="utf-8")) if chf.exists() and topic != "T08" else json.loads(TOPICS.read_text(encoding="utf-8"))["topics"]
    qs = {q["id"]: q for q in json.loads(PACK.read_text(encoding="utf-8"))["questions"] if not q.get("dupOf")}
    el = LC.eligible()
    return qs, [i for i in sorted(qs) if tp.get(i) == topic], {i: el[i] for i in qs if tp.get(i) == topic and i in el}


def sheet(topic):
    D.mkdir(parents=True, exist_ok=True)
    sh, judges, _ = paths(topic)
    if sh.exists():
        print("SHEET ABORT：判定單已經產生過")
        return 2
    qs, chap, el = candidates(topic)
    md = [f"# 教材依據判定單（{topic}；候選 {len(el)} 題／本章 {len(chap)} 題）", "",
          "判準：該題考試當天施行的那一版裡，有一條的條文**寫出了正解的關鍵內容**，而且對正解的支持高於對每一個錯誤選項 →「對得上」（記條號）；否則「對不上」。",
          "每題列出字面最接近的 4 條只是幫忙找，判定時請讀整部（全文檔路徑在每題裡）。", ""]
    rows = ["編號\t判定（對得上／對不上）\t條號（對得上才填）\t把條文接到答案的一句話（只有 me 要填）"]
    for n, qid in enumerate(sorted(el), 1):
        q, e = qs[qid], el[qid]
        tag = f"{e['pcode']}-{e['version']}"
        tf = LC.TEXT / f"{tag}.txt"
        if not tf.exists():
            arts = LC.articles(LC.get(e["url"], LC.RAW / f"ver-{tag}.html"))
            if not arts:
                print(f"SHEET ABORT：{tag} 解析不到條文")
                return 2
            LC.TEXT.mkdir(parents=True, exist_ok=True)
            tf.write_text("\n\n".join(f"{no}\n{t}" for no, t in arts), encoding="utf-8")
        arts = [(m.group(1), m.group(2).strip()) for m in re.finditer(r"(?m)^(第[0-9\-]+條)\n(.*?)(?=^第[0-9\-]+條$|\Z)", tf.read_text(encoding="utf-8") + "\n", re.S)]
        key = LC.grams3(q["stem"] + q["options"][q["answer"] - 1] * 2)
        top = sorted(arts, key=lambda x: -len(key & LC.grams3(x[1])))[:4]
        md += [f"## B{n:02d}　{qid}", q["stem"]] + [f"- ({k}) {o}{'　**（正解）**' if k == q['answer'] else ''}" for k, o in enumerate(q["options"], 1)]
        md += ["", f"**法規**：{e['law']}；**考試當天施行的版本**：{e['version']}；全文檔：`{tf}`（共 {len(arts)} 條）", f"網址：{e['url']}", "", "字面最接近的 4 條："]
        md += [f"- **{no}**：{t[:500]}{'…' if len(t) > 500 else ''}" for no, t in top] + [""]
        rows.append(f"B{n:02d}\t\t\t")
    sh.write_text("\n".join(md), encoding="utf-8")
    for j in judges.values():
        j.write_text("\n".join(rows) + "\n", encoding="utf-8")
    key = {f"B{n:02d}": {"id": qid, **el[qid]} for n, qid in enumerate(sorted(el), 1)}
    (D / f"basis-{topic}-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (Path(__file__), sh, D / f"basis-{topic}-key.json"):
        log("basis-sheet", p)
    print(f"SHEET OK：本章 {len(chap)} 題，候選 {len(el)} 題 → {sh}")
    return 0


def rows(p):
    out = {}
    for l in p.read_text(encoding="utf-8").splitlines()[1:]:
        if l.strip():
            c = [x.strip() for x in (l.split("\t") + [""] * 4)[:4]]
            out[c[0]] = c
    return out


def lock(who, topic):
    _, judges, _ = paths(topic)
    j = judges[who]
    bad = [k for k, c in rows(j).items() if c[1] not in ("對得上", "對不上") or (c[1] == "對得上" and not re.fullmatch(r"第[0-9\-]+條", c[2]))
           or (who == "me" and c[1] == "對得上" and not c[3])]
    if bad:
        print(f"LOCK ABORT：{j.name} 有空白或格式不對：{bad}")
        return 2
    if logged("basis-lock", j.name):
        print("LOCK ABORT：已經鎖定過")
        return 2
    log("basis-lock", j)
    print(f"LOCK OK：{j.name} {sha(j)[:12]}…")
    return 0


def merge(topic):
    sh, judges, out = paths(topic)
    for j in judges.values():  # noqa
        lk = logged("basis-lock", j.name)
        if not lk or sha(j) != lk[-1]:
            print(f"MERGE ABORT：{j.name} 還沒鎖定（或鎖定後被改過）")
            return 2
    key = json.loads((D / f"basis-{topic}-key.json").read_text(encoding="utf-8"))
    j1, j2 = judges.values()
    me, ag = rows(j1), rows(j2)
    qs, chap, el = candidates(topic)
    res, agree, disagree = {}, 0, []
    for code, k in key.items():
        a, b = me[code], ag[code]
        same = a[1] == b[1] and (a[1] == "對不上" or a[2] == b[2])
        agree += same
        if not same:
            disagree.append((code, k["id"], a[1], a[2], b[1], b[2]))
        if same and a[1] == "對得上":
            tf = LC.TEXT / f"{k['pcode']}-{k['version']}.txt"
            m = re.search(r"(?m)^%s\n(.*?)(?=^第[0-9\-]+條$|\Z)" % re.escape(a[2]), tf.read_text(encoding="utf-8") + "\n", re.S)
            res[k["id"]] = {"law": k["law"], "pcode": k["pcode"], "version": k["version"], "article": a[2], "text": m.group(1).strip(),
                            "snapshot": str(tf.relative_to(ROOT)).replace("\\", "/"), "url": k["url"], "link": a[3] or ""}
    out.write_text(json.dumps({"topic": topic, "chapter": len(chap), "candidates": len(el), "agree": agree, "disagree": disagree,
                               "basis": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    log("basis-merge", out)
    print(f"MERGE OK：本章 {len(chap)} 題；候選 {len(el)}；兩個判斷者一致 {agree}／{len(key)}；有依據（兩邊都對得上、條號相同）{len(res)} 題 "
          f"→ 有說明 {len(res)}／{len(chap)}（{len(res) / len(chap):.0%}），留白 {len(chap) - len(res)}；不一致 {disagree}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] + ["", ""]
    # lock 的參數：lock <判斷者> <章>（例：lock a T07）
    sys.exit({"sheet": lambda: sheet(a[1]), "lock": lambda: lock(a[1], a[2] or "T08"), "merge": lambda: merge(a[1])}
             .get(a[0], lambda: (print(__doc__), 2)[1])())
