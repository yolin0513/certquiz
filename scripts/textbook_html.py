#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教材草稿 HTML（電腦上看；使用者 2026-10-13：HTML 與 App 都要做，題目與說明同一份來源）
-------------------------------------------------------------------------------
  python -u scripts/textbook_html.py   讀 data/local/教材/textbook.json（唯一來源）＋本機匯入包的題目文字 → data/local/教材/教材草稿.html

設計要求（Dispatch 2026-10-13）：互動失效時內容仍要讀得完整——答案、說明、留白說明都「預設展開、程式執行時才收合」，
不是「點了才產生」。控制項（搜尋、篩選、讀過／沒把握）預設隱藏，程式執行時才顯示；沒有程式時頁首說明為什麼看不到按鈕。
驗證：scripts/test_textbook_html.mjs（關掉 JavaScript 讀得到每一題的正解與說明／留白；打開時預設收合、點了展開）。
"""
import html
import json
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
L = ROOT / "data" / "local"
D = L / "教材"
OUT = D / "教材草稿.html"
esc = html.escape


def main():
    tb = json.loads((D / "textbook.json").read_text(encoding="utf-8"))
    pack = json.loads((L / "import" / "bic-匯入包.json").read_text(encoding="utf-8"))
    Q = {q["id"]: q for q in pack["questions"]}
    # 金融常識「題庫互證」的上限（乙的覆蓋率，草稿要寫）
    ethics = E.load116()
    right = {}
    for q in ethics:
        o = q["options"][q["answer"] - 1]
        if not E.is_generic2(o) and len(E.n1(o)) >= 4:
            right.setdefault(E.n1(o), set()).add(q["id"])
    cross = sum(1 for q in ethics if (lambda o: not E.is_generic2(o) and len(E.n1(o)) >= 4 and len(right.get(E.n1(o), set()) - {q["id"]}) > 0)(q["options"][q["answer"] - 1]))

    def law_note(q):
        x = q.get("law")
        if not x:
            return ""
        if x["status"] == "amended":
            ls = [e for e in x["laws"] if e["after"]]
            return ('<div class="law amended"><b>這題點名的法規，在考試後修正過</b>：'
                    + "；".join(f"「{esc(e['name'])}」{'、'.join(e['after'])} 修正" for e in ls)
                    + '。<span class="muted">有標示不代表答案錯了；正解是官方答案卷的答案。</span></div>')
        tag = {"unchanged": ("ok", "法規：查過，考試後沒修正。"), "partial": ("", "法規：只查到一部分。"), "none": ("", "法規：沒查到，不知道有沒有改。")}[x["status"]]
        return f'<p class="law {x["status"]}"><b class="{tag[0]}">{tag[1]}</b></p>'

    def explain(it):
        if "ours" in it:
            o = it["ours"]
            return (f'<div class="ours{" unknown" if o["unknown"] else ""}"><p><b>{"看不出原因：" if o["unknown"] else "我們寫的（未查證）："}</b>{esc(o["text"])}</p></div>')
        if "explain" in it:
            x = it["explain"]
            v = x["version"]
            return (f'<div class="exp"><p><b>法規原文：</b>「{esc(x["law"])}」{esc(x["article"])}（考試當時 {v[:4]}-{v[4:6]}-{v[6:]} 版）</p>'
                    f'<blockquote>{esc(x["text"])}</blockquote>'
                    f'<p><b>我們寫的（未查證）：</b>{esc(x["link"])}</p>'
                    f'<p class="src">來源：全國法規資料庫（2026-10-08 抓取），快照 <code>{esc(x["snapshot"])}</code></p></div>')
        return (f'<div class="blank"><p class="blank-h">說明：留白</p><p>原因：{esc(it.get("blank", ""))}。</p>'
                '<p class="muted">你選的是「乙」：只有指得出外部依據（法規條文）時才寫說明；指不出來的就不寫，免得把我們沒查證的理解當成答案的理由。</p></div>')

    def qblock(it, cls="q"):
        q = Q[it["id"]]
        opts = "".join(f"<li>{esc(o)}</li>" for o in q["options"])
        has = "explain" in it or "ours" in it
        kind = "law" if "explain" in it else ("unknown" if it.get("ours", {}).get("unknown") else ("ours" if "ours" in it else "blank"))
        return (f'<div class="{cls}" data-qid="{esc(q["id"])}" data-exp="{1 if has else 0}" data-kind="{kind}">'
                f'<p class="stem">{esc(q["stem"])}</p><ol class="opts">{opts}</ol>'
                f'<details class="ans" open><summary>答案與說明</summary>'
                f'<p class="right-ans">官方正解：({q["answer"]}) {esc(q["options"][q["answer"] - 1])}</p>{explain(it)}{law_note(q)}</details></div>')

    cards = []
    ch = next(c for c in tb["chapters"] if "items" in c)
    for it in ch["items"]:
        head = ""
        if it.get("point"):
            head = f'<p class="badge">反覆考過：{it["point"]["times"]} 期都考過（{"同一份清單" if it["point"]["kind"] == "list" else "同一條規定"}）</p>'
        vs = [v for v in it.get("variants", []) if not v.get("dup")]
        var = (f'<details class="var" open><summary>同一條規定的其他問法（{len(vs)}）</summary>' + "".join(qblock(v, "q v") for v in vs) + "</details>") if vs else ""
        cards.append(f'<section class="card item" data-point="{1 if it.get("point") else 0}" data-mark="">{head}{qblock(it)}{var}'
                     f'<div class="marks js-only" hidden><button type="button" data-m="read">讀過</button><button type="button" data-m="unsure">沒把握</button></div></section>')
    allq = ch["items"] + [v for it in ch["items"] for v in it.get("variants", []) if not v.get("dup")]
    n, ne, no, nu = ch["count"], ch["explained"], ch.get("ours", 0), ch.get("unknown", 0)
    chap_rows = "".join(f'<tr><td>{esc(c["name"])}</td><td class=num>{c["count"]}</td><td>{"這份草稿的樣本章" if "items" in c else ""}</td></tr>' for c in tb["chapters"])
    css = """
:root{--bg:#f6f7f9;--paper:#fff;--fg:#1b2430;--muted:#556173;--line:#d8dee6;--pri:#1f5a8a;--pri-fg:#fff;--ok:#1d6b3a;--ok-bg:#e5f3ea;--ng:#a32a20;--ng-bg:#fbe7e5;--warn-bg:#fbf0dc;--f:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--pri-fg:#11161c;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn-bg:#33281a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161c;--paper:#1a2129;--fg:#e6eaef;--muted:#a1adbb;--line:#2e3844;--pri:#8fbbe3;--pri-fg:#11161c;--ok:#7fd29a;--ok-bg:#15301f;--ng:#f0a198;--ng-bg:#3a1f1c;--warn-bg:#33281a;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 var(--f)}
main{max-width:820px;margin:0 auto;padding-inline:16px;padding-block:20px 48px}
h1{font-size:1.4rem;line-height:1.35;margin:0 0 6px;text-wrap:balance}h2{font-size:1.18rem;margin:0 0 10px;text-wrap:balance}h3{font-size:1.04rem;margin:18px 0 8px}
p{margin:6px 0}.muted{color:var(--muted);font-size:.9rem}.src{color:var(--muted);font-size:.85rem;overflow-wrap:anywhere}
.card{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px;min-width:0}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:6px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted)}.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;border:1px solid var(--line);margin:8px 0}.bar .e{background:var(--ok)}.bar .b{background:repeating-linear-gradient(45deg,var(--line),var(--line) 4px,transparent 4px,transparent 8px)}
.stem{margin:0 0 6px;white-space:pre-wrap}.opts{margin:4px 0;padding-left:1.6em}.opts li{margin:2px 0}
details{margin:8px 0}summary{cursor:pointer;color:var(--pri);font-weight:600;padding:4px 0}.right-ans{color:var(--ok);font-weight:700}
.exp{border-left:3px solid var(--ok);padding-left:10px;margin:8px 0}.exp-h{color:var(--ok);font-weight:700;margin:0}
blockquote{margin:6px 0;padding:6px 10px;border-left:3px solid var(--muted);white-space:pre-wrap}
.ours{border:2px dotted var(--fg);border-radius:12px;padding:8px 12px;margin:8px 0}.ours.unknown{background:var(--bg)}
.bar .o{background:radial-gradient(circle,var(--fg) 1.2px,transparent 1.4px) 0 0/6px 6px}
.blank{border:2px dashed var(--muted);border-radius:10px;padding:8px 12px;margin:8px 0}.blank-h{font-weight:700;margin:0}
.badge{display:inline-block;font-size:.85rem;padding:2px 10px;border-radius:999px;background:var(--ok-bg);color:var(--ok);margin:0 0 6px}
.law{font-size:.9rem;color:var(--muted)}.law.amended{color:var(--fg);border:2px solid var(--ng);background:var(--ng-bg);border-radius:8px;padding:6px 10px}.law .ok{color:var(--ok)}
.v{border-top:1px dashed var(--line);padding-top:6px;margin-top:6px}code{font-size:.85rem}
.tools{position:sticky;top:0;z-index:2;background:var(--bg);padding:8px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.tools input[type=search]{flex:1 1 200px;min-width:0;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--paper);color:var(--fg)}
button{font:inherit;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--paper);color:var(--fg);cursor:pointer}
button[aria-pressed="true"]{background:var(--pri);color:var(--pri-fg);border-color:var(--pri)}
.marks{display:flex;gap:8px;margin-top:8px}.item[data-mark~="read"]{opacity:.75}.item[data-mark~="unsure"]{border-color:var(--ng)}
label{font-size:.92rem}input,select{color:var(--fg);accent-color:var(--pri)}select{font:inherit;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:4px}[hidden]{display:none!important}.nojs{border:2px solid var(--pri)}
"""
    js = """
(function(){
  // 程式執行時：收合答案、顯示控制項、隱藏「沒有程式」的說明。沒有程式時這些都不發生，內容全部展開
  document.querySelectorAll('details.ans, details.var').forEach(function(d){ d.open = false; });
  document.querySelectorAll('.js-only').forEach(function(e){ e.hidden = false; });
  var nojs = document.getElementById('nojs'); if (nojs) nojs.hidden = true;
  var store = {}; try { store = JSON.parse(localStorage.getItem('certquiz-textbook-marks') || '{}'); } catch (e) { store = {}; }
  function save(){ try { localStorage.setItem('certquiz-textbook-marks', JSON.stringify(store)); } catch (e) {} }
  var items = Array.prototype.slice.call(document.querySelectorAll('.item'));
  function paint(it){ var id = it.querySelector('.q').getAttribute('data-qid'); var m = store[id] || {};
    it.setAttribute('data-mark', (m.read ? 'read ' : '') + (m.unsure ? 'unsure' : ''));
    it.querySelectorAll('.marks button').forEach(function(b){ b.setAttribute('aria-pressed', m[b.getAttribute('data-m')] ? 'true' : 'false'); }); }
  items.forEach(function(it){ paint(it); it.querySelectorAll('.marks button').forEach(function(b){ b.addEventListener('click', function(){
    var id = it.querySelector('.q').getAttribute('data-qid'); var m = store[id] || {}; var k = b.getAttribute('data-m'); m[k] = !m[k]; store[id] = m; save(); paint(it); apply(); }); }); });
  var q = document.getElementById('q'), fp = document.getElementById('f-point'), fk = document.getElementById('f-kind'), fu = document.getElementById('f-unsure'), cnt = document.getElementById('cnt');
  function apply(){ var s = (q.value || '').trim(); var n = 0;
    items.forEach(function(it){ var t = it.textContent; var k = it.querySelector('.q').getAttribute('data-kind'); var id = it.querySelector('.q').getAttribute('data-qid');
      var kind = fk.value; var kok = !kind || (kind === 'ours' ? (k === 'ours' || k === 'unknown') : k === kind);
      var ok = (!s || t.indexOf(s) >= 0) && (!fp.checked || it.getAttribute('data-point') === '1') && kok && (!fu.checked || (store[id] || {}).unsure);
      it.hidden = !ok; if (ok) n++; });
    cnt.textContent = '顯示 ' + n + '／' + items.length + ' 張'; }
  [q, fp, fk, fu].forEach(function(e){ e.addEventListener('input', apply); e.addEventListener('change', apply); });
  document.getElementById('open-all').addEventListener('click', function(){ document.querySelectorAll('details.ans').forEach(function(d){ d.open = true; }); });
  document.getElementById('close-all').addEventListener('click', function(){ document.querySelectorAll('details.ans, details.var').forEach(function(d){ d.open = false; }); });
  apply();
})();
"""
    pct = lambda a, b: f"{a / b:.0%}" if b else "—"
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><title>內控教材草稿</title><style>{css}</style></head><body><main>
<h1>教材草稿（請你確認再開工）</h1>
<p class="muted">照你的選擇做：解答說明「乙＋丙」——指得出法規條文的放條文原文，其餘寫我們的理解並標「未經查證」；HTML（電腦上看）與 App（手機上看）都做，兩邊用同一份資料產生。產生時間 {esc(datetime.now().strftime("%Y-%m-%d %H:%M"))}。題目原文只放在你自己的裝置，不要轉貼。</p>
<section class="card nojs" id="nojs"><p><b>如果你看不到搜尋框和按鈕</b>：表示這個瀏覽器沒有執行網頁程式（例如 iPhone 的「檔案」App 預覽）。內容仍然全部列出——答案和說明都已經展開，可以直接往下讀。手機上要互動，請用 App 裡的「讀書 → 教材」。</p></section>

<section class="card"><h2>兩種說明怎麼分：信用卡這一章</h2>
<ul>
<li><b>法規原文 {ne} 題</b>：放考試當時那一版的條文原文（兩個判斷者都判條文寫出了正解，才放）。</li>
<li><b>我們寫的（未查證）{no - nu} 題</b>：我們的理解，可能是錯的。</li>
<li><b>看不出原因 {nu} 題</b>：多半是要記的數字或天數，我們說不出理由，就照實寫。</li>
</ul>
<div class="bar" role="img" aria-label="法規原文 {ne} 題、我們寫的 {no - nu} 題、看不出 {nu} 題"><span class="e" style="width:{ne / n * 100:.1f}%"></span><span class="o" style="width:{(no - nu) / n * 100:.1f}%"></span><span class="b" style="width:{nu / n * 100:.1f}%"></span></div>
<p class="muted">每段說明前面都寫明是哪一種：「法規原文」「我們寫的（未查證）」「看不出原因」。</p>
<p><b>「我們寫的」怎麼寫</b>（每一題都照這三條）：只解釋為什麼官方正解是對的，不延伸補充；不寫法規名稱（那會讓它看起來像有依據）；拿不準就寫拿不準。<b>這一層可能是錯的</b>——它是我們的理解，沒有外部依據；跟你自己的理解或課本衝突時，以官方答案與法規為準。</p></section>

<section class="card"><h2>分章方案</h2>
<p><b>分章是為了好讀、好找，不是驗證過的學習單位</b>（量過：同一組讀懂一題對答對另一題有幫助的只有 11%）。章名來自官方簡章的命題範圍、依題庫實際內容拆細；題數是草稿用的關鍵字規則，<b>正式版會逐題歸章，題數會變</b>。</p>
<div class="tw"><table><thead><tr><th>章</th><th>題數</th><th></th></tr></thead><tbody>{chap_rows}</tbody></table></div>
<p class="muted">金融市場常識與職業道德：章名用證基會公告的範圍（常識 6 章、道德 7 章）；題庫 PDF 沒有標章節，每章題數要等正式版逐題歸章。那一科公開的是整份題庫、不是歷屆考卷，所以沒有「最常出現」可以數，會改成把同一概念的題排在一起。</p></section>

<section class="card"><h2>互動設計</h2>
<ul>
<li><b>預設收合、點了展開</b>：答案與說明先收起來，先自己想。網頁程式不能執行時，全部改成展開（上面那段說明）。</li>
<li><b>搜尋</b>、<b>只看反覆考過的</b>、<b>依說明種類篩選</b>（法規原文／我們寫的／看不出）、<b>只看沒把握的</b>。</li>
<li><b>讀過／沒把握</b>：存在這台電腦的瀏覽器裡。手機上的 App 版則跟錯題、弱點複習、「答案有疑問」接在一起，也會跟著備份走。</li>
<li><b>App 版樣本</b>：匯入新版的內控匯入包後，App 的「讀書」多一個「教材（草稿）」，內容與這一頁同一份資料。</li>
</ul>
<p class="muted">不列年份：畫面上不寫哪一期；每題的出處（期別、題號、頁碼）我們內部仍保留在題號裡與對照檔，之後複查、處理你回報的「答案有疑問」時要用。</p></section>

<div class="tools js-only" hidden><input type="search" id="q" placeholder="搜尋（例如：循環信用）" aria-label="搜尋">
<label><input type="checkbox" id="f-point"> 只看反覆考過的</label><label>說明種類 <select id="f-kind"><option value="">全部</option><option value="law">法規原文</option><option value="ours">我們寫的（未查證，含看不出原因）</option><option value="unknown">看不出原因</option></select></label><label><input type="checkbox" id="f-unsure"> 只看沒把握的</label>
<button type="button" id="open-all">全部展開</button><button type="button" id="close-all">全部收起</button><span class="muted" id="cnt"></span></div>
<h2>信用卡（{n} 題）</h2>
{''.join(cards)}
</main><script>{js}</script></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(f"TEXTBOOK-HTML OK：{ch['name']} {n} 題、{len(cards)} 張卡；法規原文 {ne}、我們寫的 {no}（看不出 {nu}）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
