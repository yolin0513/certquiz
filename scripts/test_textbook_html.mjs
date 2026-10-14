// 教材 HTML 的驗證（Dispatch 2026-10-13 的設計要求）：
//   一、關掉 JavaScript（像 iPhone「檔案」App 預覽）：每一題的官方正解、說明或留白都看得到；搜尋與按鈕不出現；頁首說明為什麼看不到按鈕。
//   二、打開 JavaScript（電腦瀏覽器）：答案預設收合、點了展開；搜尋、篩選、沒把握標記（重新載入後還在）都會動。
//   三、同一份來源：頁面上的題號＝textbook.json 那一章的題號（不多不少）。
// 用法：node scripts/test_textbook_html.mjs   結論只寫記錄檔（data/local/logs/，正式／非正式自動分開），畫面只印記錄檔路徑。
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { mkdirSync, appendFileSync, readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const puppeteer = createRequire(join(process.env.PUPPETEER_FROM || join(ROOT, '..', 'JLPT_App'), 'package.json'))('puppeteer');
const st = spawnSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: ROOT, encoding: 'utf-8' });
const official = st.status === 0 && !(st.stdout || '').trim();
const LOGDIR = process.env.CERTQUIZ_LOGDIR || join(ROOT, 'data', 'local', 'logs', ...(official ? [] : ['unofficial']));
mkdirSync(LOGDIR, { recursive: true });
const LOG = join(LOGDIR, `test-textbook-${new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)}${official ? '' : '-UNOFFICIAL'}.log`);
const out = (...a) => appendFileSync(LOG, `${new Date().toTimeString().slice(0, 8)} ${a.join(' ')}\n`);
process.stdout.write(`TEST-TEXTBOOK：完整輸出與結論都寫在 ${LOG}（畫面不印結論；結束碼 0＝全部符合、1＝有不符、2＝中止）\n`);
let fails = 0; const failed = [];
const check = (d, ok, detail = '') => { out(`${ok ? '✓' : '✗'} ${d}${ok ? '' : '：' + detail}`); if (!ok) { fails++; failed.push(d); } };

// 參數 ethics：測職業道德那一份（只有兩層，沒有法規重點；docs/M 第十一節）
const CERT = process.argv.includes('ethics') ? 'ethics' : 'bic';
const FILE = join(ROOT, 'data', 'local', '教材', CERT === 'ethics' ? '職業道德教材草稿.html' : '教材草稿.html');
const TB = JSON.parse(readFileSync(join(ROOT, 'data', 'local', '教材', CERT === 'ethics' ? 'textbook-ethics.json' : 'textbook.json'), 'utf-8'));
// 所有已做的章合在一起看（每一章的章首都要有「沒有說明＝純粹要背」那一句）
const filledCh = TB.chapters.filter(c => c.items);
const ch = { items: filledCh.flatMap(c => c.items) };
const want = [...ch.items.map(i => i.id), ...ch.items.flatMap(i => (i.variants || []).filter(v => !v.dup).map(v => v.id))].sort();
const wantExp = new Set([...ch.items, ...ch.items.flatMap(i => i.variants || [])].filter(x => x.explain).map(x => x.id));
const kindOf = x => x.explain ? 'law' : x.plain ? 'plain' : x.ours ? 'ours' : 'blank';
const wantKinds = Object.fromEntries([...ch.items, ...ch.items.flatMap(i => (i.variants || []).filter(v => !v.dup))].map(x => [x.id, kindOf(x)]));

async function main() {
  out(`開始｜${official ? '正式執行' : '非正式執行'}｜${FILE}`);
  const prof = mkdtempSync(join(tmpdir(), `certquiz-textbook-${process.pid}-`));
  const browser = await puppeteer.launch({ headless: true, userDataDir: prof });
  try {
    // 一、關掉 JavaScript
    const p0 = await browser.newPage();
    await p0.setJavaScriptEnabled(false);
    await p0.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true });
    await p0.goto(pathToFileURL(FILE).href);
    const r0 = await p0.evaluate(() => {
      // 「看得到」要同時滿足：沒有任何一層收合的 <details> 包著它、而且有排版的框。
      // 只看排版框不夠：Chrome 對收合的 <details> 裡的內容仍回報框（突變「答案不預設展開」第一次沒紅才發現）
      const vis = e => !!e && !e.parentElement.closest('details:not([open])') && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
      const qs = [...document.querySelectorAll('.q')];
      return { n: qs.length, ids: qs.map(q => q.getAttribute('data-qid')).sort(),
        ans: qs.filter(q => vis(q.querySelector('.right-ans'))).length,
        expOrBlank: qs.filter(q => q.getAttribute('data-kind') === 'plain' ? !q.querySelector('.exp, .ours, .blank') : (vis(q.querySelector('.exp')) || vis(q.querySelector('.ours')))).length,
        fullHidden: qs.filter(q => q.querySelector('.exp')).every(q => q.querySelector('details.full') && !q.querySelector('details.full').open),
        // 條文全文原樣在不在：跟 textbook.json 逐題比對（不用長度門檻——信託業法第31條全文只有 18 字）
        fullText: Object.fromEntries(qs.filter(q => q.querySelector('.exp')).map(q => [q.getAttribute('data-qid'), (q.querySelector('details.full blockquote') || {}).textContent || ''])),
        nolaw: vis(document.getElementById('nolaw-note')) && document.querySelectorAll('.chap-head .nolaw-note').length === document.querySelectorAll('.chap-head').length,
        plainNote: vis(document.getElementById('plain-note')) && document.querySelectorAll('.chap-head .plain-note').length === document.querySelectorAll('.chap-head').length && document.querySelectorAll('.chap-head').length > 0,
        kinds: Object.fromEntries(qs.map(q => [q.getAttribute('data-qid'), q.getAttribute('data-kind')])),
        oursStart: qs.filter(q => q.querySelector('.ours')).every(q => q.querySelector('.ours').textContent.startsWith('我們寫的（未查證）：')),
        lawStart: qs.filter(q => q.querySelector('.exp')).every(q => q.querySelector('.exp').textContent.startsWith('法規重點：第') && !q.querySelector('.exp').textContent.includes('未查證')),
        exp: qs.filter(q => vis(q.querySelector('.exp'))).map(q => q.getAttribute('data-qid')).sort(),
        tools: vis(document.querySelector('.tools')), nojs: vis(document.getElementById('nojs')) };
    });
    check(`關掉 JavaScript：${r0.n} 題每一題的官方正解都看得到（${r0.ans}）；有說明的題說明看得到、純背的題不出現說明（${r0.expOrBlank}）；章首寫明「沒有說明的題＝純粹要背」`, r0.n === want.length && r0.ans === r0.n && r0.expOrBlank === r0.n && r0.plainNote);
    const wantFull = Object.fromEntries(ch.items.flatMap(it => [it, ...(it.variants || []).filter(v => !v.dup)]).filter(q => q.explain).map(q => [q.id, q.explain.text]));
    const fullOk = CERT === 'ethics' ? Object.keys(wantFull).length === 0 && r0.exp.length === 0 : Object.keys(wantFull).length > 0 && Object.entries(wantFull).every(([id, t]) => (r0.fullText[id] || '').replace(/\s+/g, '') === t.replace(/\s+/g, ''));
    check('法規重點：完整條文收在展開裡、預設不展開、內容還在（不刪；跟原文逐題相同）', r0.fullHidden && fullOk);
    check('每一題的說明種類（法規原文／我們寫的／看不出）＝textbook.json；沒有留白', JSON.stringify(r0.kinds) === JSON.stringify(Object.fromEntries(Object.keys(r0.kinds).map(k => [k, wantKinds[k]]))) && !Object.values(r0.kinds).includes('blank'));
    check('中文標示：我們寫的每段以「我們寫的（未查證）：」開頭；法規重點以「法規重點：第…條」開頭、不標未查證', r0.oursStart && r0.lawStart);
    check(`關掉 JavaScript：法規原文的 ${r0.exp.length} 題＝textbook.json 裡有依據的 ${wantExp.size} 題`, JSON.stringify(r0.exp) === JSON.stringify([...wantExp].sort()));
    check('關掉 JavaScript：搜尋與按鈕不出現；頁首寫明為什麼看不到按鈕', !r0.tools && r0.nojs);
    // 兩層的那一科：頁首與每一章章首都要寫明「這一科沒有法規重點」；三層的那一科不能出現這句
    check(CERT === 'ethics' ? '職業道德：頁首與每一章章首都寫明「這一科沒有法規重點」及原因' : '內控：不出現「這一科沒有法規重點」', CERT === 'ethics' ? r0.nolaw : !r0.nolaw);
    check(`同一份來源：頁面上的題號＝textbook.json 那一章的 ${want.length} 題（不多不少）`, JSON.stringify(r0.ids) === JSON.stringify(want));

    // 二、打開 JavaScript
    const p1 = await browser.newPage();
    const errs = []; p1.on('pageerror', e => errs.push(e.message));
    await p1.setViewport({ width: 1280, height: 900 });
    await p1.goto(pathToFileURL(FILE).href);
    const r1 = await p1.evaluate(() => ({ open: [...document.querySelectorAll('details.ans')].filter(d => d.open).length, all: document.querySelectorAll('details.ans').length,
      tools: !document.querySelector('.tools').hidden, nojs: !document.getElementById('nojs').hidden }));
    check(`打開 JavaScript：答案預設收合（${r1.all} 個裡展開的 ${r1.open} 個）、搜尋與按鈕出現、「看不到按鈕」的說明隱藏`, r1.open === 0 && r1.all > 0 && r1.tools && !r1.nojs);
    await p1.click('.item details.ans > summary');
    check('打開 JavaScript：點「答案與說明」會展開', await p1.$eval('.item details.ans', d => d.open));
    const vis = () => p1.$$eval('.item', its => its.filter(i => !i.hidden).length);
    const total = await vis();
    await p1.select('#f-kind', 'plain');
    const unk = await vis();
    const wantUnk = ch.items.filter(i => i.plain).length;
    check(`篩選「沒有說明」：${unk} 張＝代表題是純背的 ${wantUnk} 張`, unk === wantUnk && unk > 0);
    await p1.select('#f-kind', '');
    await p1.type('#q', '絕對不會出現的字串ＸＹＺ');
    check('搜尋找不到時：0 張', (await vis()) === 0);
    await p1.$eval('#q', e => { e.value = ''; e.dispatchEvent(new Event('input')); });
    check(`清掉搜尋：回到 ${total} 張`, (await vis()) === total);
    await p1.click('.item .marks button[data-m="unsure"]');
    await p1.reload();
    await p1.click('#f-unsure');
    check('標「沒把握」：重新載入後還在，篩選「只看沒把握的」剩 1 張', (await vis()) === 1);
    check('打開 JavaScript：沒有頁面錯誤', errs.length === 0, errs.join('；'));
  } finally {
    await browser.close();
    rmSync(prof, { recursive: true, force: true });
  }
  out(fails ? `TEST-TEXTBOOK FAILED：${fails} 項不符（${failed.join('｜')}）` : 'TEST-TEXTBOOK OK：全部符合');
  return fails ? 1 : 0;
}
main().then(c => process.exit(c), e => { out(`TEST-TEXTBOOK ERROR：${e.stack || e}`); process.exit(2); });
