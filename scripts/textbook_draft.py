#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材草稿（使用者 2026-10-13 的請求：歷屆最常出現的題目與觀念、依主題分章、互動式、含解答說明、不列年份；先給草稿確認再開工）
-------------------------------------------------------------------------------
  python -u scripts/textbook_draft.py   → data/local/教材/教材草稿.html（含官方題目原文，只放本機）＋ 教材草稿-出處.json（每題的出處，內部複查用）

草稿要讓使用者決定三件事：形式（做進 App／本機 HTML）、解答說明的層級（甲乙丙）、分章方案。
數字都從本機資料算：章節題數（先前主題分組實驗凍結的規則）、乙的覆蓋率（條文抽樣量測、題庫互證的上限）。
本程式不含任何題目文字；題目從本機匯入包讀。
"""
import html
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ethics_stats as E  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "data" / "local"
OUTDIR = LOCAL / "教材"
OUT = OUTDIR / "教材草稿.html"
SRC_OUT = OUTDIR / "教材草稿-出處.json"
SAMPLE_TOPIC = "T08"                      # 信用卡（使用者自己舉的例子）
DEMO_QID = "bic-law-u39-019"              # 甲乙丙同一題示範：章內、條文對得上（兩個判斷者一致）、有 N1 法規修正標示
DEMO_LAW = ("信用卡業務機構管理辦法", "G0380055", "20150629", 47, "20211013")
esc = html.escape


def article(pcode, ver, n):
    p = LOCAL / "law" / "text" / f"{pcode}-{ver}.txt"
    t = p.read_text(encoding="utf-8")
    m = re.search(r"(?m)^第\s*%d\s*條\s*\n(.*?)(?=^第\s*\d+(?:-\d+)?\s*條\s*$|\Z)" % n, t, re.S)
    return (m.group(1).strip() if m else None), p


def main():
    pack = json.loads((LOCAL / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))
    topics = json.loads((LOCAL / "study" / "topics.json").read_text(encoding="utf-8"))
    names, tp = topics["names"], topics["topics"]
    act = {q["id"]: q for q in pack["questions"] if not q.get("dupOf")}
    allq = {q["id"]: q for q in pack["questions"]}
    # 母體核對：每一題剛好歸一章
    if set(act) - set(tp):
        print(f"DRAFT ABORT：{len(set(act) - set(tp))} 題沒有歸章")
        return 1
    count = {}
    for i in act:
        count[tp[i]] = count.get(tp[i], 0) + 1
    # 乙的覆蓋率：內控＝條文對得上的抽樣量測（docs/K 第 3 步）；金融常識＝「題庫裡另一題把同一句話當正解」的上限
    ethics = E.load116()
    right = {}
    for q in ethics:
        for k, o in enumerate(q["options"], 1):
            if k == q["answer"] and not E.is_generic2(o) and len(E.n1(o)) >= 4:
                right.setdefault(E.n1(o), set()).add(q["id"])
    cross = sum(1 for q in ethics if (lambda o: not E.is_generic2(o) and len(E.n1(o)) >= 4 and len(right.get(E.n1(o), set()) - {q["id"]}) > 0)(q["options"][q["answer"] - 1]))
    # 樣本章：信用卡
    chap = sorted([q for q in act.values() if tp[q["id"]] == SAMPLE_TOPIC], key=lambda q: q["id"])
    pts = [p for p in pack["points"] if any(tp.get(i) == SAMPLE_TOPIC for i in p["ids"] if i in act)]
    in_pts = {i for p in pts for i in p["ids"]}
    others = [q for q in chap if q["id"] not in in_pts]
    st = {s: sum(1 for q in chap if q.get("law", {}).get("status") == s) for s in ("amended", "unchanged", "partial", "none")}
    if st["amended"] == 0:
        print("DRAFT ABORT：樣本章沒有任何一題有法規修正標示——換一章（樣本要讓他看到完整的樣子）")
        return 1
    demo = act[DEMO_QID]
    assert tp[DEMO_QID] == SAMPLE_TOPIC and demo.get("law", {}).get("status") == "amended"
    law_name, pcode, ver, artno, newver = DEMO_LAW
    art_old, art_path = article(pcode, ver, artno)
    art_new, _ = article(pcode, newver, artno)
    srcmap = {}

    def law_line(q):
        x = q.get("law")
        if not x:
            return ""
        if x["status"] == "amended":
            ls = [e for e in x["laws"] if e["after"]]
            return ('<div class="law amended"><b>這題點名的法規，在考試後修正過</b><br>'
                    + "；".join(f"「{esc(e['name'])}」在 {'、'.join(e['after'])} 修正過" for e in ls)
                    + '。<span class="muted">有標示不代表答案錯了：只知道整部法規改過，不知道這題問的那一條有沒有改。正解是官方答案卷的答案。</span></div>')
        tag = {"unchanged": ("ok", "查過：考試後沒修正。"), "partial": ("unk", "只查到一部分。"), "none": ("unk", "沒查到：不知道有沒有改。")}[x["status"]]
        return f'<p class="law {x["status"]}"><b class="{tag[0]}">{tag[1]}</b></p>'

    def opts(q, show_answer):
        return '<ol class="opts">' + "".join(
            f'<li{" class=right" if show_answer and k == q["answer"] else ""}>{esc(o)}{"　<b>← 官方正解</b>" if show_answer and k == q["answer"] else ""}</li>'
            for k, o in enumerate(q["options"], 1)) + "</ol>"

    def card(q, extra_head="", variants=()):
        srcmap[q["id"]] = {"period": q.get("period"), "qno": q.get("qno"), "subject": q.get("subject"), "page": q.get("page")}
        for v in variants:
            srcmap[v["id"]] = {"period": v.get("period"), "qno": v.get("qno"), "subject": v.get("subject"), "page": v.get("page")}
        var = ""
        if variants:
            var = (f'<details class="var"><summary>同一條規定的其他問法（{len(variants)}）</summary>'
                   + "".join(f'<div class="v" data-qid="{esc(v["id"])}"><p class="stem">{esc(v["stem"])}</p>{opts(v, True)}</div>' for v in variants) + "</details>")
        return (f'<section class="q" data-qid="{esc(q["id"])}">{extra_head}<p class="stem">{esc(q["stem"])}</p>{opts(q, False)}'
                f'<details class="ans"><summary>先想一想，再點這裡看答案</summary><p class="right-ans">官方正解：({q["answer"]}) {esc(q["options"][q["answer"] - 1])}</p>'
                f'{law_line(q)}<p class="muted">（解答說明照你選的層級寫；這一章的草稿先只放官方正解，示範請看上面「解答說明的三種寫法」。）</p></details>{var}</section>')

    point_cards = []
    for p in sorted(pts, key=lambda p: (-len(p["periods"]), p["id"])):
        ids = [i for i in p["ids"] if i in allq]
        reps = sorted((allq[i] for i in ids if i in act), key=lambda q: -int(q["period"])) or [allq[ids[0]]]
        rep = reps[0]
        vs = [allq[i] for i in ids if i != rep["id"]]
        point_cards.append(card(rep, f'<p class="badge">反覆考過：{len(p["periods"])} 期都考過（{"同一份清單" if p.get("kind") == "list" else "同一條規定"}）</p>', vs))
    other_cards = [card(q) for q in others]

    demo_q = (f'<p class="stem">{esc(demo["stem"])}</p>{opts(demo, False)}')
    ans = f'<p class="right-ans">官方正解：({demo["answer"]}) {esc(demo["options"][demo["answer"] - 1])}</p>'
    same = art_old == art_new
    tiers = f"""
<div class="tiers">
<div class="tier"><h4>甲：只放官方正解</h4>{ans}
<p class="cost"><b>代價</b>：零風險（只有官方答案），但你看不到為什麼。</p></div>
<div class="tier"><h4>乙：指得出外部依據才寫</h4>{ans}
<p><b>依據</b>：「{esc(law_name)}」第 {artno} 條（這題考試當時的版本：{ver[:4]}-{ver[4:6]}-{ver[6:]} 版）</p>
<blockquote>{esc(art_old)}</blockquote>
<p class="muted">原文。來源：全國法規資料庫該版全文，2026-10-08 抓取，快照 <code>{esc(str(art_path.relative_to(ROOT)))}</code>。</p>
<p>條文寫「對<b>消費者</b>權益之保障，不得低於……範本內容」，所以答案是 (3)。</p>
<p class="muted">這部法規在 2021-10-13 修正過（所以這題有法規修正標示）；程式比對第 {artno} 條在修正前後{'<b>文字完全相同</b>' if same else '<b>文字不同</b>'}——{'這題的答案不受那次修正影響' if same else '請看修正後的條文'}。</p>
<p class="cost"><b>代價</b>：說明有出處、可以查，但很多題沒有說明（覆蓋率見下表）。</p></div>
<div class="tier"><h4>丙：全部都寫，指不出依據的標「未經查證」</h4>{ans}
<p class="ours"><b>我們的理解，未經查證</b>：定型化契約範本是主管機關為了保護持卡人訂的最低標準；銀行自己訂的信用卡契約，對持卡人（消費者）的保障不能比範本差。發卡機構、收單機構、特約商店都是業者這一方，不是這條要保護的對象。</p>
<p class="cost"><b>代價</b>：每題都有說明，但標「未經查證」的那些可能是錯的，而且錯的說明讀起來跟對的一樣——要你自己承擔。</p></div>
</div>"""
    chapters = "".join(f'<tr><td>{esc(names[k])}</td><td class=num>{count.get(k, 0)}</td></tr>' for k in sorted(count, key=lambda k: -count[k]) if k != "T99") \
        + f'<tr><td>其他（對不到任何一章）</td><td class=num>{count.get("T99", 0)}</td></tr>'
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    css = """
:root{--bg:#f6f7f9;--paper:#fff;--fg:#1b2430;--muted:#556173;--line:#d8dee6;--pri:#1f5a8a;--ok:#1d6b3a;--ok-bg:#e5f3ea;--ng:#a32a20;--ng-bg:#fbe7e5;--warn-bg:#fbf0dc;--warn:#7a4b00;--f:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn-bg:#33281a;--warn:#f0c779;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn-bg:#33281a;--warn:#f0c779;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 var(--f)}
main{max-width:760px;margin:0 auto;padding-inline:16px;padding-block:20px 48px}
h1{font-size:1.4rem;line-height:1.35;margin:0 0 6px;text-wrap:balance}h2{font-size:1.18rem;margin:0 0 10px;text-wrap:balance}h3{font-size:1.04rem;margin:18px 0 8px}h4{margin:0 0 6px;font-size:1rem;color:var(--pri)}
p{margin:6px 0}.muted{color:var(--muted);font-size:.9rem}section,.card{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px;min-width:0}
.first{border:2px solid var(--ng)}.decide{border:2px solid var(--pri)}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:6px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted)}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tiers{display:grid;gap:12px}.tier{border:1px solid var(--line);border-radius:10px;padding:12px}.cost{background:var(--warn-bg);color:var(--fg);border-radius:8px;padding:6px 10px}
.ours{border:1px dashed var(--muted);border-radius:8px;padding:6px 10px}
blockquote{margin:6px 0;padding:6px 10px;border-left:3px solid var(--muted);white-space:pre-wrap}
.q{padding:14px}.stem{margin:0 0 6px;white-space:pre-wrap}.opts{margin:4px 0;padding-left:1.6em}.opts li{margin:3px 0;padding:2px 6px;border-radius:6px}.opts li.right{background:var(--ok-bg);border:1px solid var(--ok)}
details{margin:8px 0}summary{cursor:pointer;color:var(--pri);font-weight:600;padding:6px 0}.right-ans{color:var(--ok);font-weight:700}
.badge{display:inline-block;font-size:.85rem;padding:2px 10px;border-radius:999px;background:var(--ok-bg);color:var(--ok);margin:0 0 6px}
.law{font-size:.92rem}.law.amended{border:2px solid var(--ng);background:var(--ng-bg);border-radius:8px;padding:8px 10px}.law .ok{color:var(--ok)}.law.partial,.law.none{border:1px dashed var(--muted);border-radius:8px;padding:4px 10px}
.v{border-top:1px dashed var(--line);padding-top:6px;margin-top:6px}code{font-size:.85rem;overflow-wrap:anywhere}
nav{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.92rem;margin:8px 0 16px}nav a{color:var(--pri)}
ul.opt{padding-left:1.2em}ul.opt li{margin:6px 0}
"""
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><title>教材草稿</title><style>{css}</style></head><body><main>
<h1>教材草稿：請你確認再開工</h1>
<p class="muted">內控與金融市場常識與職業道德的讀書教材。這份是草稿：先請你決定幾件事，正式版才動工。產生時間 {esc(now)}。題目原文只放在你自己的裝置，不要轉貼。</p>
<nav><a href="#form">先決定：做成什麼形式</a><a href="#decide">要你決定的事</a><a href="#tiers">解答說明的三種寫法</a><a href="#chapters">分章方案</a><a href="#often">「最常出現」</a><a href="#sample">樣本章：信用卡</a><a href="#ux">互動設計</a><a href="#src">出處</a></nav>

<section id="form" class="first"><h2>最先要決定的：做成什麼形式</h2>
<p><b>你要的是「互動式 HTML」。但有一件你提需求時可能不知道的事：iPhone 用「檔案」App 打開 HTML 檔時，常常不會執行網頁裡的程式（JavaScript）</b>——那樣的話，點了沒反應、搜尋不能用、讀過的標記存不起來，看起來就像我們做壞了。</p>
<div class="tw"><table><thead><tr><th>做法</th><th>現況</th><th>代價</th></tr></thead><tbody>
<tr><td><b>做進 App 的「讀書」</b></td><td><b>已驗證可行</b>：你手機上從主畫面開的 App 一切正常，備份與還原也在你的 iPhone 上試成功了。題目照舊跟著匯入包走，只在你的手機上。</td><td>要重新匯入一次匯入包；只能在 App 裡讀。</td></tr>
<tr><td>本機 HTML 檔</td><td><b>有已知風險</b>：在 iPhone「檔案」App 裡互動功能可能全部失效；用電腦瀏覽器開沒問題。</td><td>手機上可能只剩「純閱讀」。</td></tr>
</tbody></table></div>
<p><b>我們的建議：做進 App。</b>但這由你決定。</p>
<p class="muted">這份草稿本身只用了「點標題展開」這種不需要程式的寫法，所以就算在「檔案」App 裡也看得到答案。</p></section>

<section id="decide" class="decide"><h2>要你決定的三件事</h2>
<ol>
<li><b>形式</b>：做進 App，或本機 HTML（見上面）。</li>
<li><b>解答說明寫到什麼程度</b>：甲、乙、丙三選一（見下一節，同一題三種寫法並排）。</li>
<li><b>分章方案</b>：下面的章節清單可以嗎？想合併、拆開或改名的直接說。</li>
</ol>
<p class="muted">回覆一行就好，例如「App、乙、章節照這樣」。</p></section>

<section id="tiers"><h2>解答說明的三種寫法（同一題寫三次）</h2>
<p class="lead">為了讓你只看到「寫法」的差別，下面三種都用同一題：</p>
<div class="card">{demo_q}</div>
{tiers}
<h3>每一種能寫到多少題</h3>
<div class="tw"><table><thead><tr><th></th><th>甲</th><th>乙（有依據才寫）</th><th>丙</th></tr></thead><tbody>
<tr><td>內控</td><td>全部只有正解，0 題有說明</td><td>約 <b>13%</b> 的題有說明（法規科約 24%、實務科約 6%）；其餘約 87% 只有正解</td><td>全部有說明；其中約 87% 標「未經查證」</td></tr>
<tr><td>金融常識與道德</td><td>全部只有正解</td><td><b>最多約 {cross / len(ethics):.0%}</b>（{cross}／{len(ethics)} 題），而且這是上限，見下面說明</td><td>全部有說明；其中至少約 {1 - cross / len(ethics):.0%} 標「未經查證」</td></tr>
</tbody></table></div>
<ul class="muted">
<li>內控的 13%：先前量過——題目點名法規、查得到考試當時的版本、而且條文真的寫出正解的，抽 30 題有 26 題對得上，推估全部約 13%（95% 區間約 10%～14%）。兩個判斷者都是 Claude。</li>
<li>金融常識沒有可以對的法規版本資料，能當依據的只有「題庫裡另一題，把同一句話當成正解」。但這要先知道那一題問的是「哪個對」還是「哪個錯」——問「哪個錯」的題，正解是一句錯的話——而這正是先前重點整理試了四次都分不出來的事。所以 {cross / len(ethics):.0%} 只是上限：正解那句話在別題也是正解的題數，實際能當依據的更少。</li>
<li>也就是說：<b>選乙，大部分的題會只有正解、沒有說明。</b>我們原本建議乙；量出來的覆蓋率比預期低，請把這個數字一起考慮。</li>
</ul></section>

<section id="chapters"><h2>分章方案</h2>
<p><b>先講清楚：分章是為了好讀、好找，不是我們驗證過的學習單位。</b>先前量過「同一組裡讀懂一題，對答對另一題有沒有幫助」，只有 11%——所以不要把「讀完這一章」當成「這一章的題都會了」。</p>
<h3>內控（可練 {len(act)} 題）</h3>
<p class="muted">章名來自官方簡章的命題範圍（出納、存匯、授信、外匯、信託、財富管理、票券證券、消費金融、資訊、衍生性商品……）再依題庫實際內容拆細；每題只歸一章。下面的題數是用先前凍結的關鍵字規則算的，<b>正式版會逐題歸類，題數會變</b>。</p>
<div class="tw"><table><thead><tr><th>章</th><th>題數（粗估）</th></tr></thead><tbody>{chapters}</tbody></table></div>
<h3>金融市場常識與職業道德（116 年版 1,174 題）</h3>
<p>章名用證基會公告的各科範圍：</p>
<p><b>金融市場常識（558 題）</b>：金融體系、證券期貨市場、銀行實務、信託實務、貨幣市場實務、保險實務。</p>
<p><b>職業道德（616 題）</b>：業務推廣與招攬、受託執行業務、告知義務與通知、誠實信用原則、有關利益衝突、保密原則、遵守法律規範與自律。</p>
<p class="muted">題庫 PDF 沒有標每題屬於哪一章。常識用關鍵字很粗地試過：一章一題算下來，證券期貨市場約 216、保險約 120、銀行實務約 50、信託約 46、貨幣市場約 37、金融體系約 17，另有 72 題對不到、157 題同時對到兩章以上——太粗，只能當參考。道德的七章用關鍵字分不出來。<b>兩科的每章題數要等正式版逐題歸類才有。</b></p></section>

<section id="often"><h2>「最常出現」：兩張證照意思不一樣</h2>
<p><b>內控</b>：有歷屆考卷，「反覆考過」是真的可以數的——已經有 138 組「同一條規定在不同期被考過」的清單。每一章會先放這些，再放其他題。</p>
<p><b>金融市場常識與職業道德</b>：證基會公開的是<b>整份題庫</b>，不是歷屆考卷，<b>所以沒有「最常出現」這回事</b>——題庫裡每一題地位相同，考試從裡面出。這不是我們漏做了。這一科能做的是：依章節整理，並把「同一個概念反覆出現的題」排在一起。</p></section>

<section id="sample"><h2>樣本章：信用卡（{len(chap)} 題）</h2>
<p class="muted">這一章完整列出，讓你看實際長什麼樣：先放反覆考過的規定（{len(pts)} 組），再放其他題。每題先自己想，再點「看答案」。法規修正的標示照 App 的寫法放在答案裡：這一章有 {st['amended']} 題「考試後修正過」、{st['unchanged']} 題「查過、沒修正」、{st['none'] + st['partial']} 題「沒查到」。不列年份。</p>
<h3>反覆考過的規定</h3>
{''.join(point_cards)}
<h3>這一章的其他題</h3>
{''.join(other_cards)}</section>

<section id="ux"><h2>互動設計（提案）</h2>
<ul class="opt">
<li><b>章節目錄</b>：點了跳到那一章；每章顯示題數與你讀過幾題。</li>
<li><b>先想再看</b>：答案與說明預設收起來，點了才打開。</li>
<li><b>只看反覆考過的</b>（內控）：時間不夠時先讀這些。</li>
<li><b>搜尋</b>：輸入關鍵字（例如「循環信用」）找題。</li>
<li><b>標記</b>：「讀過」「沒把握」；沒把握的可以一鍵拿去練習。做進 App 的話，跟現有的錯題、弱點複習、「答案有疑問」接在一起，也會跟著備份走。</li>
</ul></section>

<section id="src"><h2>不列年份，但出處我們會留著</h2>
<p>畫面上不列「哪一年、第幾期」。<b>但每題的出處（期別、題號、頁碼）我們內部會保留</b>：之後要複查題目有沒有轉錯、法規有沒有修正、你回報「答案有疑問」時，都要靠它找回原題。這份草稿的出處另存在同一個資料夾的 <code>教材草稿-出處.json</code>，你不用看。</p></section>

<section><h2>接下來</h2>
<p>你選好形式、說明層級與章節後，我們會先給正式版的工作量估計（逐題歸章 1,975 題、寫說明，屬於重負載），再開工。</p></section>
</main></body></html>"""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    SRC_OUT.write_text(json.dumps(srcmap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DRAFT OK：樣本章 {len(chap)} 題（反覆考過 {len(pts)} 組、其他 {len(others)} 題；法規修正 {st}）；"
          f"甲乙丙示範 {DEMO_QID}（第 {artno} 條修正前後{'相同' if same else '不同'}）；金融常識互證上限 {cross}／{len(ethics)} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
