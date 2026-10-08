// 瀏覽器實測（隱私三層的第三層）：作答紀錄不得離開手機；App 在真瀏覽器裡能匯入、能練、能離線。
//
// 順序（常設規則 14：量測先驗尺）：
//   一、驗尺：網路監測器必須先抓到刻意造出的 5 種請求（頁面 POST、sendBeacon、被 CSP 擋的外部連線、
//       Service Worker 那一側的 GET、Service Worker 送的 POST）。任何一項抓不到 → 中止、回 2、不下結論。
//   二、實測：乾淨的網站複本（只有要部署的檔）＋真的匯入包；練一輪 10 題；查 IndexedDB；斷網重開；
//       另開隔離環境驗題目文字裡的 HTML 不會被執行。
//   三、端到端突變：把 App 改成每答一題就 sendBeacon，同一套判定必須紅（證明「實測全綠」能變紅）。
//
// puppeteer 借用 JLPT_App 已裝好的（只讀它的 node_modules，不改任何檔）；可用環境變數 PUPPETEER_FROM 指定。
// 用法：node scripts/test_browser.mjs     結束碼：0 全部符合；1 有不符；2 驗尺失敗或前提不成立
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdtempSync, cpSync, rmSync, existsSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PUP_DIR = process.env.PUPPETEER_FROM || join(ROOT, '..', 'JLPT_App');
const puppeteer = createRequire(join(PUP_DIR, 'package.json'))('puppeteer');
const PACK = join(ROOT, 'data', 'local', 'import', 'bic-匯入包.json');
const PUBLIC = ['index.html', 'sw.js', 'manifest.webmanifest', 'css', 'js', 'icons', 'data/manifest.json', 'data/q'];
const AZ = JSON.parse(readFileSync(join(ROOT, 'data', 'q', 'az900.json'), 'utf-8')).questions;

let fails = 0;
const failed = [];   // 總結行要列出是哪幾項不符（2026-10-08：有一次只截到部分輸出，無從得知是哪一項失敗）
const check = (desc, ok, detail = '') => {
  console.log(`${ok ? '✓' : '✗'} ${desc}${ok ? '' : '：' + detail}`);
  if (!ok) { fails++; failed.push(desc); }
  return ok;
};

// ---------------------------------------------------------------- 網站複本與伺服器
function makeSite(patch) {
  const dir = mkdtempSync(join(tmpdir(), `certquiz-site-${process.pid}-`));
  for (const p of PUBLIC) cpSync(join(ROOT, p), join(dir, p), { recursive: true });
  if (patch) patch(dir);
  return dir;
}

function serve(dir) {
  return new Promise((resolve, reject) => {
    const proc = spawn('python', ['-I', join(ROOT, 'scripts', 'serve.py'), dir, '0'], { stdio: ['ignore', 'pipe', 'pipe'] });
    let buf = '';
    const t = setTimeout(() => reject(new Error('伺服器 10 秒內沒有啟動')), 10000);
    proc.stdout.on('data', d => {
      buf += d;
      const m = buf.match(/SERVING (\d+)/);
      if (m) { clearTimeout(t); resolve({ proc, origin: `http://127.0.0.1:${m[1]}` }); }
    });
    proc.on('exit', c => { clearTimeout(t); reject(new Error(`伺服器結束（${c}）`)); });
  });
}

// ---------------------------------------------------------------- 網路監測器
// 用 CDP 直接接每一個 page 與 service_worker 目標的 Network 事件（page.on('request') 看不到 SW 那一側）。
// base＝網站根網址（結尾帶 /）。合格的請求：GET、同一個 origin、而且路徑在 base 底下
// （線上是 yolin0513.github.io/certquiz/，同一個 origin 還有使用者其他 App，要連路徑一起限定）。
class Monitor {
  constructor(browser, base) {
    this.origin = new URL(base).origin;
    this.prefix = new URL(base).pathname;
    this.records = [];
    this.attached = new Set();
    this.onTarget = t => this.attach(t).catch(() => {});
    browser.on('targetcreated', this.onTarget);
    for (const t of browser.targets()) this.onTarget(t);
  }
  async attach(t) {
    const type = t.type();
    if (!['page', 'service_worker'].includes(type) || this.attached.has(t)) return;
    this.attached.add(t);
    const s = await t.createCDPSession();
    s.on('Network.requestWillBeSent', e => this.records.push({ kind: type, method: e.request.method, url: e.request.url, rtype: e.type }));
    await s.send('Network.enable');
  }
  mark() { return this.records.length; }
  since(i) { return this.records.slice(i); }
  bad(recs) {
    return recs.filter(r => !r.url.startsWith('data:') && !r.url.startsWith('blob:') &&
      (r.method !== 'GET' || new URL(r.url).origin !== this.origin || !new URL(r.url).pathname.startsWith(this.prefix)));
  }
}

async function cspLog(page) {
  return page.evaluate(() => (window.__csp || []).slice());
}

// 全畫面掃描：畫面上任何時刻出現 null／undefined／NaN 都是程式錯誤（題庫內容本身沒有這些字，2026-10-08 查過）
const BAD_TEXT = [];
const BAD_RE_SRC = 'null|undefined|NaN';

async function newPage(ctx, errors) {
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  await page.exposeFunction('__reportBadText', (t, where) => { BAD_TEXT.push({ t, where }); });
  await page.evaluateOnNewDocument(src => {
    const re = new RegExp(src);
    const seen = new WeakSet();
    const scanNode = n => {
      if (n.nodeType === 3) {
        const p = n.parentElement;
        if (p && !['SCRIPT', 'STYLE'].includes(p.tagName) && re.test(n.data) && !seen.has(n)) {
          seen.add(n);
          window.__reportBadText(n.data.slice(0, 80), location.hash + ' ' + (p.className || p.tagName));
        }
      } else if (n.nodeType === 1) {
        for (const c of n.childNodes) scanNode(c);
      }
    };
    new MutationObserver(ms => { for (const m of ms) {
      if (m.type === 'characterData') scanNode(m.target);
      for (const n of m.addedNodes || []) scanNode(n);
    } }).observe(document, { childList: true, subtree: true, characterData: true });
  }, BAD_RE_SRC);
  // CSP 違規事件：被擋的外部連線不會出現在網路紀錄裡，要從這裡抓
  await page.evaluateOnNewDocument(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', e => window.__csp.push({ uri: e.blockedURI, dir: e.violatedDirective }));
  });
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  return page;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
// 換頁後要等「新的畫面」畫好才能找元素：只改 # 後面時文件不會重新載入，waitForSelector 會先找到上一頁還留著的同名元素
//（曾在 57 個細項逐一打開時讀到上一個細項的題目，間歇性紅）。先在 #view 放一個記號，換頁後等 render() 把它換掉（或整份文件換了）。
// 同一個網址 goto 什麼都不會發生、記號永遠不會消失，所以那種情況不放記號。
async function gotoView(page, url) {
  const same = page.url() === url;
  if (!same) await page.evaluate(() => { const v = document.getElementById('view'); if (v) v.append(Object.assign(document.createElement('i'), { id: '__stale' })); }).catch(() => {});
  await page.goto(url);
  if (!same) await page.waitForFunction(() => !document.getElementById('__stale'));
}
const text = page => page.evaluate(() => document.getElementById('view').innerText);
async function waitText(page, s) {
  await page.waitForFunction(t => document.getElementById('view').innerText.includes(t), {}, s);
}

// ---------------------------------------------------------------- 一、驗尺
async function ruler(browser, base, mon) {
  console.log('== 一、驗尺（監測器先證明抓得到）');
  const ctx = await browser.createBrowserContext();
  const errors = [];
  const page = await newPage(ctx, errors);
  await gotoView(page, base);
  await waitText(page, '證照題庫練習');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  let ok = true;
  const has = (i, f) => mon.since(i).some(f);
  const nBad = BAD_TEXT.length;
  await page.evaluate(() => { const p = document.createElement('p'); p.textContent = 'nullnull'; document.getElementById('view').append(p); });
  await sleep(200);
  ok &= check('R0 全畫面掃描：畫面上出現 nullnull 被抓到', BAD_TEXT.length > nBad && BAD_TEXT.slice(nBad).some(x => x.t.includes('nullnull')));
  BAD_TEXT.length = nBad;   // 驗尺自己造的，不算

  let i = mon.mark();
  await page.evaluate(() => fetch('data/manifest.json', { method: 'POST' }).catch(() => 0));
  await sleep(300);
  ok &= check('R1 頁面送出的 POST 被抓到', has(i, r => r.kind === 'page' && r.method === 'POST' && r.url.includes('data/manifest.json')));

  i = mon.mark();
  await page.evaluate(() => navigator.sendBeacon('data/ruler-beacon', 'x'));
  await sleep(500);
  ok &= check('R2 sendBeacon 被抓到', has(i, r => r.method === 'POST' && r.url.includes('ruler-beacon')));

  const ext = 'https://' + 'example.invalid/ruler-r3';
  await page.evaluate(u => fetch(u).catch(() => 0), ext);
  await sleep(300);
  ok &= check('R3 外部連線嘗試被抓到（CSP 違規事件）', (await cspLog(page)).some(v => v.uri.includes('example.invalid')));

  i = mon.mark();
  await page.reload();
  await waitText(page, '證照題庫練習');
  await sleep(500);
  ok &= check('R4 Service Worker 那一側的請求看得到', has(i, r => r.kind === 'service_worker'),
    `SW 側 0 筆（全部 ${mon.since(i).length} 筆）`);

  const swTarget = browser.targets().find(t => t.type() === 'service_worker' && t.url().startsWith(base));
  i = mon.mark();
  if (swTarget) {
    const w = await swTarget.worker();
    await w.evaluate(() => fetch('data/ruler-sw-post', { method: 'POST' }).catch(() => 0));
    await sleep(500);
  }
  ok &= check('R5 Service Worker 送出的 POST 被抓到', !!swTarget && has(i, r => r.kind === 'service_worker' && r.method === 'POST'));
  await ctx.close();
  return !!ok;
}

// ---------------------------------------------------------------- 練一輪
async function practiceRound(page, count) {
  await gotoView(page, page.url().split('#')[0] + `#/setup?cert=bic`);
  await page.waitForSelector('select[name=count]');
  // page.select 選不到值時不報錯、照舊用預設值（2026-10-08 踩過：要 2 題卻停在 10 題）→ 核對真的選到了
  const picked = await page.select('select[name=count]', String(count));
  if (picked[0] !== String(count)) throw new Error(`題數選單沒有 ${count} 這個選項`);
  await page.select('select[name=order]', 'random');
  await page.click('form button[type=submit]');
  const stems = [];
  for (let n = 0; n < count; n++) {
    await page.waitForSelector('.opt:not([disabled])');
    stems.push(await page.$eval('.stem', e => e.textContent));
    await page.click('.opt[data-k="1"]');
    await page.waitForSelector('.feedback:not([hidden])');
    await page.click('.q .btn.primary');
  }
  // 結果頁才有的「再練一輪」；不能用「/ 10」——作答中的進度列「3 / 10」也有這個字
  await page.waitForSelector('a.btn.primary::-p-text(再練一輪)');
  return stems;
}

async function idbState(page) {
  return page.evaluate(() => new Promise((resolve, reject) => {
    const req = indexedDB.open('certquiz');
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction(['attempts', 'progress', 'mistakes', 'userQuestions'], 'readonly');
      const out = {};
      const all = s => new Promise(r => { const q = tx.objectStore(s).getAll(); q.onsuccess = () => r(q.result); });
      Promise.all(['attempts', 'progress', 'mistakes', 'userQuestions'].map(all)).then(([a, p, m, u]) => {
        const dup = new Set(u.filter(q => q.dupOf).map(q => q.id));
        Object.assign(out, { attempts: a.length, progress: p.length, mistakes: m.length, user: u.length,
          wrong: a.filter(x => !x.correct).length, dupAnswered: a.filter(x => dup.has(x.qid)).length });
        resolve(out);
      });
    };
    req.onerror = () => reject(req.error);
  }));
}

async function importPack(page, path, expectActive) {
  await gotoView(page, page.url().split('#')[0] + '#/settings');
  const input = await page.waitForSelector('input[type=file]');
  await input.uploadFile(path);
  await waitText(page, `可練 ${expectActive} 題`);
  await page.click('button::-p-text(確定匯入)');
  await waitText(page, '匯入完成');
}

// ---------------------------------------------------------------- 二、實測
async function realTest(browser, base, mon) {
  console.log('== 二、實測（乾淨網站複本＋真的匯入包）');
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const ctx = await browser.createBrowserContext();
  const errors = [];
  const page = await newPage(ctx, errors);
  const i0 = mon.mark();
  await gotoView(page, base);
  await waitText(page, '證照題庫練習');
  check('首頁：沒匯入前內控顯示「還沒有題目」', (await text(page)).includes('還沒有題目'));
  check(`首頁：AZ-900 顯示可練 ${AZ.length} 題（網站附的原創題）`, (await text(page)).includes(`可練 ${AZ.length} 題`), (await text(page)).slice(0, 400));
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));

  await importPack(page, PACK, pack.counts.active);
  await gotoView(page, base + '#/');
  await waitText(page, `可練 ${pack.counts.active} 題`);
  check(`匯入後首頁顯示可練 ${pack.counts.active} 題`, true);

  const stems = await practiceRound(page, 10);
  const summary = await page.$eval('h2', e => e.textContent);
  check(`練完一輪 10 題，出現結果頁（${summary}）`, stems.length === 10 && /銀行內控：\d+ \/ 10（\d+%）/.test(summary), summary);
  const st = await idbState(page);
  check('IndexedDB：作答 10 筆、每題彙總 10 筆（或同題合併）', st.attempts === 10 && st.progress >= 1 && st.progress <= 10, JSON.stringify(st));
  check('IndexedDB：錯題本筆數＝這一輪答錯的題數', st.mistakes === st.wrong, JSON.stringify(st));
  const bicStudied = await page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
    const g = q.result.transaction('attempts').objectStore('attempts').getAll(); g.onsuccess = () => r(g.result.map(x => x.studied)); }; }));
  check('內控題（還沒讀過任何讀書頁就練）：作答紀錄都標 studied=false', bicStudied.length === 10 && bicStudied.every(v => v === false), JSON.stringify(bicStudied));
  check(`IndexedDB：匯入的題目 ${pack.counts.total} 題都在`, st.user === pack.counts.total, JSON.stringify(st));
  check('重複題（dupOf）沒有被出題', st.dupAnswered === 0, JSON.stringify(st));

  // 模擬考：法規 50 題，答 45 題、留 5 題不答，交卷
  await gotoView(page, base + '#/exam?cert=bic&subject=law');
  await (await page.waitForSelector('button::-p-text(開始考試)')).click();
  await page.waitForSelector('.clock');
  const c1 = await page.$eval('.clock', e => e.textContent);
  await sleep(2200);
  const c2 = await page.$eval('.clock', e => e.textContent);
  const secs = t => { const p = t.replace('剩 ', '').split(':').map(Number); return p.reduce((a, b) => a * 60 + b, 0); };
  check(`模擬考：計時器在倒數（${c1} → ${c2}），起點是 60 分鐘`, secs(c1) <= 3600 && secs(c1) > 3590 && secs(c2) < secs(c1), `${c1} → ${c2}`);
  for (let n = 0; n < 45; n++) {
    await page.click('.opt[data-k="1"]');
    if (n === 0) {
      const leaked = await page.$$eval('.opt.right, .opt.wrong, .feedback', els => els.length);
      check('模擬考：作答中不顯示對錯', leaked === 0, `出現 ${leaked} 個對錯標示`);
    }
    await page.click('button::-p-text(下一題)');
  }
  await page.click('.sticky button::-p-text(交卷)');
  await waitText(page, '還有 5 題未作答');
  check('模擬考：還有未答題時要再確認一次', true);
  await page.click('button::-p-text(確定交卷)');
  await page.waitForSelector('a.btn.primary::-p-text(再考一次)').catch(async e => {
    console.log(`  頁面錯誤：${errors.join('；') || '無'}｜畫面：${(await text(page)).slice(0, 200)}`);
    throw e;
  });
  const head = await page.$eval('h2', e => e.textContent);
  const st2 = await idbState(page);
  const hist = await page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
    const g = q.result.transaction('meta').objectStore('meta').get('examHistory'); g.onsuccess = () => r(g.result ? g.result.v : []); }; }));
  const h0 = hist[0] || {};
  check(`模擬考：成績頁（${head}）＝紀錄（${h0.correct} 題對 × 2 分＝${h0.score}）`,
    h0.count === 50 && h0.unanswered === 5 && h0.score === h0.correct * 2 && head.includes(`${h0.score} 分`) && head.includes(h0.passed ? '（及格）' : '（不及格）'),
    `${head}｜${JSON.stringify(h0)}`);
  check('模擬考：未作答的 5 題不寫作答紀錄（作答多 45 筆）', st2.attempts === st.attempts + 45, `${st.attempts} → ${st2.attempts}`);
  await gotoView(page, base + '#/stats?cert=bic');
  await waitText(page, '最近的模擬考');
  const statsText = await text(page);
  check('統計頁：顯示作答次數、依科目與來源分組、這次模擬考', statsText.includes(`作答 ${st2.attempts} 次`) && statsText.includes('依科目') &&
    statsText.includes('依題目來源') && statsText.includes(String(h0.score)), statsText.slice(0, 300));

  // 頁面離線模式＋真的重新載入（只改 hash 不會重載——2026-10-08 發現先前這一項就是這樣）。
  // 注意：puppeteer 的離線模式只管頁面，SW 自己的請求仍可能連網；「真的斷線」在二之四（關掉伺服器）驗。
  await page.evaluate(() => { window.__notReloaded = 1; });
  await page.setOfflineMode(true);
  await gotoView(page, base + '#/');
  await page.reload();
  await waitText(page, `可練 ${pack.counts.active} 題`).then(() => check('頁面離線模式重新載入：首頁照樣顯示內控題數', true),
    e => check('頁面離線模式重新載入：首頁照樣顯示內控題數', false, e.message));
  check('頁面離線模式重新載入：頁面真的重新載入了（記號已消失）', await page.evaluate(() => window.__notReloaded === undefined));
  await page.setOfflineMode(false);
  // AZ-900 練 3 題：作答前有原創標示＋大綱節次、作答後有依據網址（文字）、卡片裡沒有連結
  await gotoView(page, base + '#/practice?cert=az900&mode=practice&count=3');
  await page.waitForSelector('.card.q .stem');
  const azBefore = await page.$eval('.card.q', e => e.innerText);
  check('AZ-900：作答前標「原創練習題，不是考題」＋官方大綱節次與細項', /原創練習題，不是考題・官方大綱 [ABC]\.\d（第 \d 細項）/.test(azBefore), azBefore.slice(0, 120));
  check('AZ-900：作答前不顯示依據', !azBefore.includes('依據'), azBefore.slice(0, 200));
  await page.click('.opt[data-k="1"]');
  await page.waitForSelector('.feedback:not([hidden])');
  const azStem = await page.$eval('.stem', e => e.textContent);
  const azQ = AZ.find(x => x.stem === azStem);
  const azFb = await page.$eval('.feedback', e => e.innerText);
  const azWant = `依據（官方文件）：${azQ.basis}${azQ.basis_anchor !== '#' ? azQ.basis_anchor : ''}`;
  check('AZ-900：作答後顯示這一題的依據網址＋錨點、解析，正解編號與題庫一致', azFb.includes(azWant) && azFb.includes(azQ.explain.slice(0, 20)) &&
    (azFb.includes('答對了') ? azQ.answer === 1 : azFb.includes(`正解是 (${azQ.answer})`)), azFb.slice(0, 300));
  check('AZ-900：題目卡片裡沒有任何連結（依據不是可點的）', (await page.$$eval('.card.q a', a => a.length)) === 0);

  const recs = mon.since(i0);
  const bad = mon.bad(recs);
  const kinds = recs.reduce((m, r) => (m[r.kind] = (m[r.kind] || 0) + 1, m), {});
  check(`網路：全部 ${recs.length} 筆請求都是同網站 GET（頁面 ${kinds.page || 0}、SW ${kinds.service_worker || 0}）`,
    bad.length === 0, bad.slice(0, 5).map(r => `${r.kind} ${r.method} ${r.url}`).join('；'));
  check('沒有 CSP 違規', (await cspLog(page)).length === 0, JSON.stringify(await cspLog(page)));
  check('沒有頁面錯誤或 console error', errors.filter(e => !e.includes('ERR_INTERNET_DISCONNECTED')).length === 0, errors.join('；'));
  await ctx.close();

  // 題目文字裡的 HTML 不得被執行（隔離環境，不影響上面的資料）
  const ctx2 = await browser.createBrowserContext();
  const page2 = await newPage(ctx2, []);
  const evil = '<img src=x onerror="window.__xss=1">';
  const fake = { format: 'certquiz-import', version: 1, cert: 'bic', questions: [{
    id: 'bic-law-t99-001', cert: 'bic', subject: 'law', chapter: 'bic.law', type: 'single', stem: `測試${evil}`,
    options: ['<b>甲</b>', '乙', '丙', '丁'], answer: 1, source: 'tabf-official', period: 99, qno: 1, law_as_of: '2026-01-01' }] };
  const fakePath = join(tmpdir(), `certquiz-xss-${process.pid}.json`);
  writeFileSync(fakePath, JSON.stringify(fake));
  try {
    await page2.goto(base);
    await waitText(page2, '證照題庫練習');
    await importPack(page2, fakePath, 1);
    await page2.goto(base + '#/practice?cert=bic&mode=practice&count=1');
    await page2.waitForSelector('.stem');
    await sleep(300);
    const r = await page2.evaluate(() => ({ xss: window.__xss, img: !!document.querySelector('.stem img, .opt b'), stem: document.querySelector('.stem').textContent }));
    check('題目文字裡的 HTML 沒被執行、原樣顯示成文字', r.xss === undefined && !r.img && r.stem.includes('<img'), JSON.stringify(r));
  } finally {
    rmSync(fakePath, { force: true });
    await ctx2.close();
  }
}

// ---------------------------------------------------------------- 二之二、模擬考完整實跑＋時間到自動交卷
// 頁面載入前把 Date.now 包一層，可以往前撥時間（App 的計時全部用 Date.now），不必真的等 60 分鐘
async function examTest(browser, base) {
  console.log('== 二之二、模擬考完整實跑＋時間到自動交卷');
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const key = (stem, opts) => [stem, ...opts].join('|');
  const ans = new Map(pack.questions.filter(q => !q.dupOf).map(q => [key(q.stem, q.options), q.answer]));
  const ctx = await browser.createBrowserContext();
  const errors = [];
  const page = await newPage(ctx, errors);
  await page.evaluateOnNewDocument(() => {
    const real = Date.now.bind(Date);
    let skew = 0;
    Date.now = () => real() + skew;
    window.__skip = ms => { skew += ms; };
  });
  const secs = t => t.replace('剩 ', '').split(':').map(Number).reduce((a, b) => a * 60 + b, 0);
  const examHist = () => page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
    const g = q.result.transaction('meta').objectStore('meta').get('examHistory'); g.onsuccess = () => r(g.result ? g.result.v : []); }; }));
  try {
    await gotoView(page, base);
    await waitText(page, '證照題庫練習');
    await importPack(page, PACK, pack.counts.active);

    // A. 實務 80 題全部作答：前 56 題答對、後 24 題答錯 → 56 × 1.25 ＝ 70 分，剛好在及格線上
    await gotoView(page, base + '#/exam?cert=bic&subject=gen');
    await (await page.waitForSelector('button::-p-text(開始考試)')).click();
    await page.waitForSelector('.clock');
    const c0 = await page.$eval('.clock', e => e.textContent);
    check(`實務模擬考：起點是 90 分鐘（${c0}）`, secs(c0) <= 5400 && secs(c0) > 5390, c0);
    let unknown = 0;
    for (let n = 0; n < 80; n++) {
      const cur = await page.evaluate(() => ({ stem: document.querySelector('.stem').textContent,
        opts: [...document.querySelectorAll('.opt span:last-child')].map(e => e.textContent) }));
      const a = ans.get(key(cur.stem, cur.opts));
      if (!a) unknown++;
      const pick = n < 56 ? a : (a % 4) + 1;
      await page.click(`.opt[data-k="${pick}"]`);
      if (n < 79) await page.click('button::-p-text(下一題)');
    }
    check('實務模擬考：80 題都在匯入包裡找得到正解（題幹＋選項逐字）', unknown === 0, `${unknown} 題找不到`);
    await page.click('.sticky button::-p-text(交卷)');
    await page.waitForSelector('a.btn.primary::-p-text(再考一次)');
    const headA = await page.$eval('h2', e => e.textContent);
    const hA = (await examHist())[0] || {};
    check(`實務模擬考：全部答完直接交卷、不跳確認；成績 ${hA.score} 分（56 對 × 1.25）＝70，剛好及格`,
      hA.count === 80 && hA.correct === 56 && hA.unanswered === 0 && hA.score === 70 && hA.passed === true && hA.timeUp === false &&
      headA.includes('70 分（及格）'), `${headA}｜${JSON.stringify(hA)}`);

    // B. 法規 50 題：答 10 題（全對）後時間到 → 自動交卷
    await gotoView(page, base + '#/exam?cert=bic&subject=law');
    await (await page.waitForSelector('button::-p-text(開始考試)')).click();
    await page.waitForSelector('.clock');
    for (let n = 0; n < 10; n++) {
      const cur = await page.evaluate(() => ({ stem: document.querySelector('.stem').textContent,
        opts: [...document.querySelectorAll('.opt span:last-child')].map(e => e.textContent) }));
      await page.click(`.opt[data-k="${ans.get(key(cur.stem, cur.opts))}"]`);
      await page.click('button::-p-text(下一題)');
    }
    // 驗尺：撥快 10 分鐘，畫面上的倒數必須跟著少 10 分鐘——證明撥時間真的影響 App 的計時
    const before = secs(await page.$eval('.clock', e => e.textContent));
    await page.evaluate(() => window.__skip(10 * 60 * 1000));
    await sleep(1500);
    const after = secs(await page.$eval('.clock', e => e.textContent));
    const rulerOk = before - after >= 600 && before - after <= 603;
    check(`驗尺：撥快 10 分鐘，倒數從 ${before} 秒變 ${after} 秒`, rulerOk);
    if (!rulerOk) return false;
    await page.evaluate(() => window.__skip(60 * 60 * 1000));
    const done = await page.waitForSelector('a.btn.primary::-p-text(再考一次)', { timeout: 5000 }).then(() => true, () => false);
    check('法規模擬考：時間到之後 5 秒內出現成績頁（自動交卷）', done);
    if (!done) return true;
    const bodyB = await text(page);
    const hB = (await examHist())[0] || {};
    check(`法規模擬考：時間到自動交卷；10 題對 × 2 ＝ ${hB.score} 分、未作答 ${hB.unanswered} 題、用時 ${hB.usedSec} 秒`,
      hB.timeUp === true && hB.count === 50 && hB.correct === 10 && hB.unanswered === 40 && hB.score === 20 && hB.passed === false &&
      hB.usedSec === 3600 && bodyB.includes('時間到自動交卷') && bodyB.includes('20 分（不及格）'), `${JSON.stringify(hB)}｜${bodyB.slice(0, 200)}`);
    // C. 法規 50 題全部答對：成績頁沒有「答錯與未作答」那一塊，畫面上也不能多出任何字
    const nC = BAD_TEXT.length;
    await gotoView(page, base + '#/');   // 上一場也是同一個網址，同網址 goto 不會換頁
    await waitText(page, '證照題庫練習');
    await gotoView(page, base + '#/exam?cert=bic&subject=law');
    await (await page.waitForSelector('button::-p-text(開始考試)')).click();
    await page.waitForSelector('.clock');
    for (let n = 0; n < 50; n++) {
      const cur = await page.evaluate(() => ({ stem: document.querySelector('.stem').textContent,
        opts: [...document.querySelectorAll('.opt span:last-child')].map(e => e.textContent) }));
      await page.click(`.opt[data-k="${ans.get(key(cur.stem, cur.opts))}"]`);
      if (n < 49) await page.click('button::-p-text(下一題)');
    }
    await page.click('.sticky button::-p-text(交卷)');
    await page.waitForSelector('a.btn.primary::-p-text(再考一次)');
    await sleep(200);
    const bodyC = await text(page);
    check('法規模擬考全部答對：100 分及格、沒有「答錯與未作答」區塊、畫面沒有多出 null', bodyC.includes('100 分（及格）') &&
      !bodyC.includes('答錯與未作答') && BAD_TEXT.length === nC, `${bodyC.slice(0, 200)}｜${BAD_TEXT.slice(nC).map(x => x.t).join('；')}`);
    check('模擬考：沒有頁面錯誤', errors.length === 0, errors.join('；'));
    return true;
  } finally {
    await ctx.close();
  }
}

// ---------------------------------------------------------------- 二之四、SW 安裝時就把網站附的題庫存進快取
// 隔離：探針頁只註冊 SW、不跑 App，所以快取裡的題庫只可能是 SW 安裝時自己存的。
// （2026-10-08：原本在實測裡驗「離線時 AZ 可練」，拿掉安裝時快取也照樣綠——App 讀題庫時 SW 多半已接手、順手快取了，量到的是時機不是這個功能。）
async function swInstallTest(browser) {
  console.log('== 二之四、真的斷線（關掉伺服器）：SW 安裝時就存好網站附的題庫，匯入的題目在 IndexedDB');
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const site = makeSite(addProbe);
  const { proc, origin } = await serve(site);
  const base = origin + '/';
  const ctx = await browser.createBrowserContext();
  let alive = true;
  try {
    const page = await newPage(ctx, []);
    await gotoView(page, base + 'sw-probe.html');
    await page.waitForFunction(() => window.__swReady === true, { timeout: 20000 });
    const keys = await page.evaluate(async () => {
      const out = [];
      for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
      return out;
    });
    check('探針頁（不跑 App）之後，SW 快取裡已有 data/q/az900.json', keys.some(k => k.endsWith('/data/q/az900.json')), keys.join('、'));
    // 只用探針頁裝好 SW；App 第一次開就直接匯入內控題，之後斷線
    await gotoView(page, base + '#/settings');
    await importPack(page, PACK, pack.counts.active);
    proc.kill(); alive = false;
    await sleep(300);
    // 驗尺：伺服器真的關了——一個從沒快取過的檔，經過 SW 也必須拿不到
    const probe = await page.evaluate(() => fetch('never-cached-' + Math.random() + '.txt').then(r => 'reached ' + r.status, () => 'offline'));
    const rulerOk = probe === 'offline';
    check(`驗尺：關掉伺服器後，沒快取過的檔拿不到（${probe}）`, rulerOk);
    if (!rulerOk) return;
    // 匯入後頁面停在設定頁（設定頁也有「可練 N 題」字樣），先切回首頁再重新載入，題數只在確認是首頁之後判定
    await gotoView(page, base + '#/');
    await page.evaluate(() => { window.__notReloaded = 1; });
    await page.reload();
    const home = await waitText(page, '證照題庫練習').then(() => true, () => false);
    check('真的斷線重新載入：首頁出來了（外殼來自 SW 快取）', home);
    if (!home) return;
    const t = await text(page);
    check('真的斷線重新載入：畫面是首頁（不是設定頁）', !t.includes('匯入題目') || t.includes('開始練習'), t.slice(0, 120));
    check('真的斷線重新載入：頁面真的重新載入了', await page.evaluate(() => window.__notReloaded === undefined));
    check(`真的斷線：內控照樣可練 ${pack.counts.active} 題（IndexedDB）`, t.includes(`可練 ${pack.counts.active} 題`), t.slice(0, 300));
    check(`真的斷線：AZ-900 照樣可練 ${AZ.length} 題（SW 安裝時存的）`, t.includes(`可練 ${AZ.length} 題`), t.slice(0, 300));
    await gotoView(page, base + '#/practice?cert=az900&mode=practice&count=2');
    const ok = await page.waitForSelector('.card.q .stem', { timeout: 10000 }).then(() => true, () => false);
    check('真的斷線：AZ-900 可以開始練習', ok);
  } finally {
    await ctx.close();
    if (alive) proc.kill();
    rmSync(site, { recursive: true, force: true });
  }
}

function addProbe(dir) {
  // 探針頁只放在測試用的網站複本裡（不入庫、不部署）：只註冊 SW，不跑 App
  writeFileSync(join(dir, 'sw-probe.html'),
    '<!doctype html><meta charset="utf-8"><title>sw probe</title><script>navigator.serviceWorker.register("sw.js")' +
    '.then(() => navigator.serviceWorker.ready).then(() => { window.__swReady = true; });</script>');
}

// ---------------------------------------------------------------- 二之五、缺欄位的題目走完整流程
// 匯入檢查接受的最小題目：只有 id、cert、type、題幹、四個選項、答案、來源（沒有科目、期別、題號、法規基準、解析、依據）
async function minimalTest(browser, base) {
  console.log('== 二之五、最小題目（只有題幹、選項、答案）走完整流程，畫面不得出現 null／undefined／NaN');
  const ctx = await browser.createBrowserContext();
  const errors = [];
  const tmpFiles = [];
  try {
    const page = await newPage(ctx, errors);
    const n0 = BAD_TEXT.length;
    await gotoView(page, base);
    await waitText(page, '證照題庫練習');
    const mk = n => ({ id: `bic-law-t98-00${n}`, cert: 'bic', type: 'single', stem: `最小題目第 ${n} 題`, options: ['甲', '乙', '丙', '丁'], answer: 2, source: 'tabf-official' });
    const minimal = { format: 'certquiz-import', version: 1, cert: 'bic', questions: [1, 2, 3].map(mk) };
    const pMin = join(tmpdir(), `certquiz-min-${process.pid}.json`); tmpFiles.push(pMin);
    writeFileSync(pMin, JSON.stringify(minimal));
    await importPack(page, pMin, 3);
    await gotoView(page, base + '#/');
    await waitText(page, '可練 3 題');
    // 練習：第 1 題答對、第 2 題答錯、第 3 題答對 → 結果頁
    await gotoView(page, base + '#/practice?cert=bic&mode=practice&count=3&order=unseen');
    for (const k of [2, 1, 2]) {
      await page.waitForSelector('.opt:not([disabled])');
      await page.click(`.opt[data-k="${k}"]`);
      await page.waitForSelector('.feedback:not([hidden])');
      await sleep(100);
      await page.click('.q .btn.primary');
    }
    await page.waitForSelector('a.btn.primary::-p-text(再練一輪)');
    await gotoView(page, base + '#/practice?cert=bic&mode=mistakes&count=20');
    await page.waitForSelector('.opt:not([disabled])');
    await page.click('.opt[data-k="2"]');
    await page.waitForSelector('.feedback:not([hidden])');
    await gotoView(page, base + '#/stats?cert=bic');
    await waitText(page, '最近的模擬考');
    const statsText = await text(page);
    const emptyNames = await page.$$eval('table tr td:first-child', tds => tds.filter(td => !td.textContent.trim()).length);
    check('最小題目：統計頁每一列都有分組名稱（沒有空白格）', emptyNames === 0 && statsText.includes('依科目'), `${emptyNames} 格空白｜${statsText.slice(0, 200)}`);
    await gotoView(page, base + '#/');
    await waitText(page, '證照題庫練習');
    // 格式錯誤的匯入包：缺版本、缺證照、缺 id、缺來源——錯誤訊息會顯示在畫面上
    const broken = { format: 'certquiz-import', questions: [{ type: 'single', stem: 'x', options: ['a', 'b', 'c', 'd'], answer: 1 }, null] };
    const pBad = join(tmpdir(), `certquiz-broken-${process.pid}.json`); tmpFiles.push(pBad);
    writeFileSync(pBad, JSON.stringify(broken));
    await gotoView(page, base + '#/settings');
    const input = await page.waitForSelector('input[type=file]');
    await input.uploadFile(pBad);
    await waitText(page, '不能匯入');
    await sleep(200);
    const mine = BAD_TEXT.slice(n0);
    check('最小題目＋格式錯誤的匯入包：整個流程畫面上都沒有出現 null／undefined／NaN', mine.length === 0,
      mine.slice(0, 5).map(x => `「${x.t}」@${x.where}`).join('；'));
    check('最小題目：沒有頁面錯誤', errors.length === 0, errors.join('；'));
  } finally {
    for (const f of tmpFiles) rmSync(f, { force: true });
    await ctx.close();
  }
}

// ---------------------------------------------------------------- 二之六、讀書模式（AZ-900 依官方大綱）
async function studyTest(browser, base) {
  console.log('== 二之六、讀書模式：AZ-900 依官方大綱逐細項讀，再練那一節');
  const ctx = await browser.createBrowserContext();
  const errors = [];
  try {
    const page = await newPage(ctx, errors);
    await gotoView(page, base);
    await waitText(page, '證照題庫練習');
    const attemptsOf = () => page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
      const g = q.result.transaction('attempts').objectStore('attempts').getAll(); g.onsuccess = () => r(g.result); }; }));
    const answerAll = async n => {
      for (let i = 0; i < n; i++) {
        await page.waitForSelector('.opt:not([disabled])');
        await page.click('.opt[data-k="1"]');
        await page.waitForSelector('.feedback:not([hidden])');
        await page.click('.q .btn.primary');
      }
      await page.waitForSelector('a.btn.primary::-p-text(再練一輪)');
    };
    // 還沒讀過就練 A.1 第 1 細項 → 作答紀錄 studied=false
    const a11 = AZ.filter(x => x.objective === 'A.1' && x.skill === 1).length;
    await gotoView(page, base + `#/practice?cert=az900&mode=practice&objective=A.1&skill=1&count=${a11}&order=unseen`);
    await answerAll(a11);
    const at1 = await attemptsOf();
    check(`還沒讀就練：${at1.length} 筆作答紀錄都標「作答前沒讀過」（studied=false）`, at1.length === a11 && at1.every(x => x.studied === false), JSON.stringify(at1.map(x => x.studied)));
    await gotoView(page, base + '#/');
    await waitText(page, '證照題庫練習');
    const btn = await page.$('a.btn[href="#/study?cert=az900"]');
    check('首頁：AZ-900 有「讀書」按鈕', !!btn && (await btn.evaluate(b => b.textContent)) === '讀書');
    await btn.click();
    await waitText(page, '讀書：依官方大綱');
    const links = await page.$$eval('.study-skills a.item', as => as.map(a => ({ href: a.getAttribute('href'), t: a.querySelector('.meta').textContent })));
    const nOf = l => Number((l.t.match(/^(\d+) 題/) || [0, 0])[1]);
    const sum = links.reduce((t, l) => t + nOf(l), 0);
    check(`大綱目錄：57 個細項都有連結、題數加總 ${sum}＝${AZ.length}`, links.length === 57 && sum === AZ.length, `${links.length} 個連結`);
    // 驗尺（換頁競態）：把畫面更新延後 300ms 撐大競態窗口（CPU 放慢沒用：畫面是等 IndexedDB，不吃主執行緒）——
    // 只改 # 的 goto 一回來就讀，要讀得到上一頁（證明這個檢查抓得到）；gotoView 要 0 次
    const slowView = on => page.evaluate(on => { const v = document.getElementById('view');
      if (on) { const o = HTMLElement.prototype.replaceChildren; v.replaceChildren = (...n) => setTimeout(() => o.apply(v, n), 300); } else delete v.replaceChildren; }, on);
    const firstStem = async () => page.$eval('.study-q .stem', e => e.textContent).catch(() => '(沒有題目)');
    const stemsOf = l => { const u = new URLSearchParams(l.href.split('?')[1]); return new Set(AZ.filter(x => x.objective === u.get('objective') && String(x.skill) === u.get('skill')).map(x => x.stem)); };
    let rawStale = 0, viewStale = 0;
    for (let i = 0; i < 10; i++) {
      const [from, to] = i % 2 ? [links[1], links[0]] : [links[0], links[1]];
      await gotoView(page, base + from.href); await page.waitForSelector('.study-q');
      await slowView(true);
      await page.goto(base + to.href); await page.waitForSelector('.study-q');
      if (!stemsOf(to).has(await firstStem())) rawStale++;
      await sleep(400);
      await gotoView(page, base + from.href); await page.waitForSelector('.study-q');
      await gotoView(page, base + to.href); await page.waitForSelector('.study-q');
      if (!stemsOf(to).has(await firstStem())) viewStale++;
      await slowView(false);
    }
    check(`驗尺（換頁競態，畫面更新延後 300ms）：只用 goto 換頁就讀，讀到上一頁 ${rawStale}／10 次（要 > 0，才證明這個檢查抓得到）`, rawStale > 0);
    check(`換頁競態：同樣條件改用 gotoView，讀到上一頁 ${viewStale}／10 次`, viewStale === 0);
    // 逐一打開每個細項
    let cards = 0, badCards = [];
    for (const l of links) {
      const u = new URLSearchParams(l.href.split('?')[1]);
      const want = AZ.filter(x => x.objective === u.get('objective') && String(x.skill) === u.get('skill'));
      await gotoView(page, base + l.href);
      await page.waitForSelector('.study-q');
      const got = await page.$$eval('.study-q', cs => cs.map(c => ({
        stem: c.querySelector('.stem').textContent,
        right: [...c.querySelectorAll('.study-opts li.right')].map(li => li.textContent),
        explain: !!c.querySelector('.explain'), basis: (c.querySelector('.basis') || {}).textContent || '',
        links: c.querySelectorAll('a').length })));
      cards += got.length;
      if (got.length !== want.length) badCards.push(`${l.href}：${got.length} 題，應 ${want.length}`);
      for (const c of got) {
        const qq = want.find(x => x.stem === c.stem);
        if (!qq) { badCards.push(`${l.href}：多出不屬於這個細項的題`); continue; }
        if (c.right.length !== 1 || c.right[0] !== qq.options[qq.answer - 1] + '（正解）') badCards.push(`${qq.id}：正解標示 ${JSON.stringify(c.right)}`);
        if (!c.explain || !c.basis.includes(qq.basis) || c.links) badCards.push(`${qq.id}：解析／依據／連結不對`);
      }
    }
    check(`57 個細項逐一打開：共 ${cards} 題，每題只標一個正解且與題庫一致、有解析與依據、卡片內沒有連結`,
      cards === AZ.length && badCards.length === 0, badCards.slice(0, 5).join('；'));
    // 手機寬度：題數最多的細項
    await page.setViewport({ width: 375, height: 800 });
    await gotoView(page, base + links.reduce((a, b) => (nOf(b) > nOf(a) ? b : a)).href);
    await page.waitForSelector('.study-q');
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check('手機寬度 375px：讀書頁沒有橫向捲動', wide <= 1, `超出 ${wide}px`);
    await page.setViewport({ width: 1200, height: 900 });
    // 讀完練這一節
    const l0 = links[0];
    const u0 = new URLSearchParams(l0.href.split('?')[1]);
    const set = new Set(AZ.filter(x => x.objective === u0.get('objective') && String(x.skill) === u0.get('skill')).map(x => x.stem));
    await gotoView(page, base + l0.href);
    await (await page.waitForSelector('a.btn.primary::-p-text(讀完了，練這)')).click();
    const stems = [];
    for (let n = 0; n < set.size; n++) {
      await page.waitForSelector('.opt:not([disabled])');
      stems.push(await page.$eval('.stem', e => e.textContent));
      await page.click('.opt[data-k="1"]');
      await page.waitForSelector('.feedback:not([hidden])');
      await page.click('.q .btn.primary');
    }
    await page.waitForSelector('a.btn.primary::-p-text(再練一輪)');
    check(`「讀完了，練這 ${set.size} 題」：出的 ${stems.length} 題都屬於這個細項、沒有重複、練完出現結果頁`,
      stems.length === set.size && stems.every(s => set.has(s)) && new Set(stems).size === stems.length);
    const at2 = (await attemptsOf()).slice(a11);
    check(`讀過再練：這 ${at2.length} 筆作答紀錄都標「作答前讀過」（studied=true）`, at2.length === set.size && at2.every(x => x.studied === true), JSON.stringify(at2.map(x => x.studied)));
    check('讀書模式：沒有頁面錯誤', errors.length === 0, errors.join('；'));
  } finally {
    await ctx.close();
  }
}

// ---------------------------------------------------------------- 二之七、內控讀書模式：反覆考點＋依期別瀏覽
async function importStudyTest(browser, base) {
  console.log('== 二之七、內控讀書模式：反覆考點清單（附「不是考試範圍」警示）＋依科目與期別瀏覽');
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const byId = new Map(pack.questions.map(x => [x.id, x]));
  const ctx = await browser.createBrowserContext();
  const errors = [];
  try {
    const page = await newPage(ctx, errors);
    await gotoView(page, base);
    await waitText(page, '證照題庫練習');
    await importPack(page, PACK, pack.counts.active);
    await gotoView(page, base + '#/');
    await (await page.waitForSelector('a.btn[href="#/study?cert=bic"]')).click();
    await waitText(page, '反覆考過的規定');
    await page.waitForSelector('.study-q');
    const warn = await page.$$eval('.card.warn', cs => cs.map(c => c.innerText));
    check('反覆考點頁：上下各一張警示卡，寫明「尚未通過驗證」「一組＝同一條規定」「不是考試範圍」「沒出現在清單上不代表不常考」「量的是寫法重複、不等於規定重要」',
      warn.length === 2 && warn.every(t => t.includes('不是考試範圍') && t.includes('這份分組正在重新核對中，目前的分法尚未通過驗證') && t.includes('一組＝同一條規定在不同期被考過，問法可能不同') && t.includes('沒出現在這份清單上，不代表那條規定不常考') && t.includes(`這 ${pack.points.length} 組量的是「題目寫法重複」，不等於「這條規定重要」`)), JSON.stringify(warn).slice(0, 200));
    const cards = await page.$$eval('.study-q', cs => cs.map(c => ({
      head: c.querySelector('.muted').textContent, stem: c.querySelector('.stem').textContent,
      right: [...c.querySelectorAll(':scope > .study-opts li.right')].map(li => li.textContent) })));
    const bad = [];
    pack.points.forEach((p, i) => {
      const c = cards[i];
      const reps = p.ids.map(x => byId.get(x)).filter(x => !x.dupOf && x.status !== 'retired').sort((a, b) => b.period - a.period);
      const rep = reps[0];
      if (!c) { bad.push(`${p.id}：沒有卡片`); return; }
      if (c.stem !== rep.stem) bad.push(`${p.id}：代表題不是最新一期`);
      if (c.right.length !== 1 || c.right[0] !== rep.options[rep.answer - 1] + '（正解）') bad.push(`${p.id}：正解標示 ${JSON.stringify(c.right)}`);
      if (!c.head.includes(`同一條規定考過 ${p.periods.length} 期（問法可能不同）`)) bad.push(`${p.id}：期數標示 ${c.head}`);
    });
    check(`反覆考點頁：${cards.length} 張卡＝匯入包 ${pack.points.length} 個考點；代表題是最新一期、只標一個正解且與答案卷一致、期數正確`,
      cards.length === pack.points.length && bad.length === 0, bad.slice(0, 5).join('；'));
    // 依科目與期別瀏覽：法規第 47 期
    const want = pack.questions.filter(x => !x.dupOf && x.subject === 'law' && x.period === 47);
    await gotoView(page, base + '#/study?cert=bic&view=browse');
    await waitText(page, '依科目與期別瀏覽');
    await gotoView(page, base + '#/study?cert=bic&view=browse&subject=law&period=47');
    await page.waitForSelector('.study-q');
    const bcards = await page.$$eval('.study-q', cs => cs.map(c => [...c.querySelectorAll('.study-opts li.right')].length));
    check(`依期別瀏覽：法規第 47 期 ${bcards.length} 題＝匯入包可練的 ${want.length} 題，每題只標一個正解`,
      bcards.length === want.length && bcards.every(n => n === 1));
    // 讀過這一期再練：作答紀錄標 studied=true
    await (await page.waitForSelector('a.btn.primary::-p-text(讀完了，練這)')).click();
    for (let n = 0; n < 2; n++) {
      await page.waitForSelector('.opt:not([disabled])');
      await page.click('.opt[data-k="1"]');
      await page.waitForSelector('.feedback:not([hidden])');
      await page.click('.q .btn.primary');
    }
    const at = await page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
      const g = q.result.transaction('attempts').objectStore('attempts').getAll(); g.onsuccess = () => r(g.result); }; }));
    check('讀過這一期再練：這 2 筆作答紀錄都標 studied=true、題目都屬於法規第 47 期',
      at.length === 2 && at.every(x => x.studied === true && byId.get(x.qid).subject === 'law' && byId.get(x.qid).period === 47), JSON.stringify(at.map(x => [x.qid, x.studied])));
    check('內控讀書模式：沒有頁面錯誤', errors.length === 0, errors.join('；'));
  } finally {
    await ctx.close();
  }
}

// ---------------------------------------------------------------- 二之八、外觀：對比度、瀏覽器預設樣式、首頁按鈕格線（深色＋淺色）
// 在頁面裡跑：逐一找「直接含文字」的可見元素，算文字色對實際背景（往上疊到不透明為止）的 WCAG 對比。
// 門檻：一般文字 4.5:1；大字（≥24px，或粗體 ≥18.66px）3:1。停用的控制項（aria-disabled／disabled）依 WCAG 1.4.3 豁免，但另外計數。
// 連結、按鈕、輸入框的文字色必須是主題色之一（不能落回瀏覽器預設：連結 #0000ee、已點過 #551a8b，深色底上只有 1.5～1.7:1）。
// getComputedStyle 看不到 :visited 的樣式，所以另外掃樣式表：不准有 :visited 規則（有的話上面的檢查就看不到）。
const AUDIT = () => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = x => { x /= 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = el => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 };   // 畫布預設白（body 有自己的背景，正常走不到這裡）
    for (const c of layers.reverse()) acc = over(c, acc);
    return acc;
  };
  const root = getComputedStyle(document.documentElement);
  const probe = document.createElement('span'); document.body.appendChild(probe);
  const tokens = ['--fg', '--muted', '--pri', '--pri-fg', '--ok', '--ng'].map(v => { probe.style.color = root.getPropertyValue(v).trim(); return getComputedStyle(probe).color; });
  probe.remove();
  for (const d of document.querySelectorAll('details')) d.open = true;
  const out = { n: 0, exempt: 0, fails: [], minRatio: 99, minAt: '', untoken: [], visitedRules: [], pop: {}, population: 0, missed: [] };
  const measured = new Set();
  const tag = el => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  for (const el of document.querySelectorAll('#view *')) {
    if (!el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible') continue;
    if (/^(A|BUTTON|SELECT|INPUT|SUMMARY)$/.test(el.tagName)) {
      out.pop[tag(el)] = (out.pop[tag(el)] || 0) + 1;
      if (!tokens.includes(cs.color)) out.untoken.push(`${tag(el)}「${el.textContent.trim().slice(0, 12)}」${cs.color}`);
    }
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.data.trim()) || el.tagName === 'SELECT';
    if (!own) continue;
    let op = 1; for (let e = el; e; e = e.parentElement) op *= Number(getComputedStyle(e).opacity);
    if (el.closest('[aria-disabled="true"], :disabled')) { out.exempt++; measured.add(el); continue; }
    out.n++;
    measured.add(el);
    const fg = parse(cs.color), bg = bgOf(el);
    const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
    const r = op < 1 ? 0 : ratio(fg.a < 1 ? over(fg, bg) : fg, bg);
    if (r < out.minRatio) { out.minRatio = r; out.minAt = `${tag(el)}「${el.textContent.trim().slice(0, 12)}」`; }
    if (r < need) out.fails.push(`${tag(el)}「${el.textContent.trim().slice(0, 14)}」${op < 1 ? '半透明' : r.toFixed(2) + ':1 < ' + need}`);
  }
  // 母體：跟上面的選法無關，另外從整個 body 走每個文字節點，畫面上看得到的就算一個「文字元素」（加上 select）。
  // 量到的（算了對比的＋豁免的）必須剛好等於母體；選擇器少抓到一塊區域時，這裡會點名漏掉的元素。
  const popSet = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = tw.nextNode(); t; t = tw.nextNode()) {
    const p = t.parentElement;
    if (!t.data.trim() || !p || /^(SCRIPT|STYLE|NOSCRIPT|OPTION)$/.test(p.tagName)) continue;
    if (!p.getClientRects().length || getComputedStyle(p).visibility !== 'visible') continue;
    popSet.add(p);
  }
  for (const sel of document.querySelectorAll('select')) if (sel.getClientRects().length) popSet.add(sel);
  out.population = popSet.size;
  for (const e of popSet) if (!measured.has(e)) out.missed.push(`${tag(e)}「${e.textContent.trim().slice(0, 12)}」`);
  for (const e of measured) if (!popSet.has(e)) out.missed.push(`（量到但不在母體）${tag(e)}`);
  for (const sh of document.styleSheets) for (const rule of sh.cssRules || []) if ((rule.selectorText || '').includes(':visited')) out.visitedRules.push(rule.selectorText);
  return out;
};
// 驗尺：同一套公式對已知值——#767676／白 4.54（剛好過）、#777777／白 4.48（剛好不過）、黑／白 21
const AUDIT_RULER = () => {
  const lum = h => { const f = x => { x /= 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; const v = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)); return 0.2126 * f(v[0]) + 0.7152 * f(v[1]) + 0.0722 * f(v[2]); };
  const r = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  return [r('#767676', '#ffffff'), r('#777777', '#ffffff'), r('#000000', '#ffffff')];
};

async function homeGrid(page) {
  return page.$$eval('#view .card', cards => cards.filter(c => c.querySelector('.actions')).map(c => {
    const bs = [...c.querySelectorAll('.actions .btn')].map(b => b.getBoundingClientRect());
    return { n: bs.length, w: bs.map(b => Math.round(b.width)), h: bs.map(b => Math.round(b.height)), x: [...new Set(bs.map(b => Math.round(b.left)))].sort((a, b) => a - b) };
  }));
}

async function lookTest(browser, base, shotDir) {
  console.log('== 二之八、外觀：每個畫面逐元素算對比、找瀏覽器預設樣式、首頁按鈕格線（深色＋淺色，iPhone 390×844）');
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const ctx = await browser.createBrowserContext();
  const errors = [];
  try {
    const page = await newPage(ctx, errors);
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    await gotoView(page, base);
    await waitText(page, '證照題庫練習');
    const rr = await page.evaluate(AUDIT_RULER);
    const rulerOk = Math.abs(rr[0] - 4.54) < 0.01 && Math.abs(rr[1] - 4.48) < 0.01 && Math.abs(rr[2] - 21) < 0.01;
    check(`驗尺：對比公式對已知值（#767676／白 ${rr[0].toFixed(2)}、#777777／白 ${rr[1].toFixed(2)}、黑／白 ${rr[2].toFixed(2)}）`, rulerOk);
    if (!rulerOk) return;
    await importPack(page, PACK, pack.counts.active);
    // 練幾題，讓錯題、統計都有內容；讀一個細項，讓「已讀」有東西可標
    await gotoView(page, base + '#/practice?cert=bic&mode=practice&count=3');
    for (let n = 0; n < 3; n++) { await page.waitForSelector('.opt:not([disabled])'); await page.click('.opt[data-k="1"]'); await page.waitForSelector('.feedback:not([hidden])'); await page.click('.q .btn.primary'); }
    await page.waitForSelector('a.btn.primary::-p-text(再練一輪)');
    await gotoView(page, base + '#/study?cert=az900&objective=A.1&skill=1');
    await page.waitForSelector('.study-q');
    const routes = [
      ['首頁', '#/', '.actions'],
      ['AZ 大綱目錄', '#/study?cert=az900', '.item'],
      ['AZ 細項', '#/study?cert=az900&objective=A.1&skill=1', '.study-q'],
      ['內控反覆考點', '#/study?cert=bic', '.study-q'],
      ['內控期別清單', '#/study?cert=bic&view=browse', '.card .btn'],
      ['內控單期', '#/study?cert=bic&view=browse&subject=law&period=47', '.study-q'],
      ['練習設定', '#/setup?cert=bic', 'select'],
      ['練習作答（看解答）', '#/practice?cert=az900&mode=practice&count=2', '.opt', async () => { await page.click('.opt[data-k="1"]'); await page.waitForSelector('.feedback:not([hidden])'); }],
      ['錯題複習', '#/practice?cert=bic&mode=mistakes&count=20', '.opt'],
      ['模擬考作答中', '#/exam?cert=bic&subject=law', 'button', async () => { await (await page.waitForSelector('button::-p-text(開始考試)')).click(); await page.waitForSelector('.grid .cell'); await page.click('.opt[data-k="1"]'); }],
      ['統計', '#/stats?cert=bic', 'table'],
      ['設定', '#/settings', 'input[type=file]'],
    ];
    const pop = {}, shots = [];
    for (const scheme of ['dark', 'light']) {
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }]);
      const fails = [], untoken = [];
      let n = 0, exempt = 0, min = 99, minAt = '', visited = [], population = 0;
      const missed = [];
      for (const [name, hash, sel, prep] of routes) {
        await gotoView(page, base + '?r=' + Date.now() + hash);   // 每頁重新載入，不帶上一頁的狀態
        await page.waitForSelector(sel);
        if (prep) await prep();
        const a = await page.evaluate(AUDIT);
        n += a.n; exempt += a.exempt; visited = a.visitedRules; population += a.population;
        missed.push(...a.missed.map(f => `${name}：${f}`));
        if (a.minRatio < min) { min = a.minRatio; minAt = `${name} ${a.minAt}`; }
        fails.push(...a.fails.map(f => `${name}：${f}`));
        untoken.push(...a.untoken.map(f => `${name}：${f}`));
        if (scheme === 'dark') for (const [k, v] of Object.entries(a.pop)) pop[k] = (pop[k] || 0) + v;
        if (shotDir && ['首頁', 'AZ 大綱目錄', '內控期別清單'].includes(name)) {
          const f = join(shotDir, `${scheme}-${name}.png`); await page.screenshot({ path: f }); shots.push(f);
        }
      }
      if (scheme === 'dark') console.log(`   母體（${routes.length} 個畫面，深色那一輪的連結／按鈕／輸入框，依「標籤.類別」計數）：${Object.entries(pop).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}×${v}`).join('、')}`);
      const nm = scheme === 'dark' ? '深色' : '淺色';
      check(`${nm}：母體——畫面上的文字元素 ${population} 個＝量到的 ${n + exempt} 個（算對比 ${n}＋停用豁免 ${exempt}）`,
        population === n + exempt && missed.length === 0 && population > 500, missed.slice(0, 6).join('；'));
      check(`${nm}：${routes.length} 個畫面 ${n} 個文字元素對比都達 WCAG AA（最低 ${min.toFixed(2)}:1 @ ${minAt}；停用按鈕豁免 ${exempt} 個）`,
        fails.length === 0 && n > 500, fails.slice(0, 6).join('；'));
      check(`${nm}：所有連結、按鈕、輸入框的文字色都是主題色（沒有落回瀏覽器預設）`, untoken.length === 0, untoken.slice(0, 6).join('；'));
      check(`${nm}：樣式表沒有 :visited 規則（有的話上面的計算看不到已點過的顏色）`, visited.length === 0, visited.join('、'));
    }
    // 首頁按鈕：每張卡片兩欄、等寬、等高；兩張卡片的欄位置對齊（iPhone 390 與最窄的 320 各量一次）
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
    // 錯題數放大到三位數，最長的按鈕字也要在最窄的 320px 擠得下一行
    await page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
      const tx = q.result.transaction('mistakes', 'readwrite'); const st = tx.objectStore('mistakes');
      // 要挑內控的錯題來複製：上面的畫面巡覽會答一題 AZ-900，答錯就有 az900 的錯題、而且排在前面（曾因此把 120 筆灌到 AZ，這項靠運氣才綠）
      st.put({ qid: '0-az900-probe', cert: 'az900' });   // 固定造出「排第一的是 AZ 錯題」那個情況，不靠運氣
      st.getAll().onsuccess = e => { const m = e.target.result.find(x => x.cert === 'bic') || { qid: 'bic-x', cert: 'bic' }; for (let i = 0; i < 120; i++) st.put({ ...m, qid: `${m.qid}-x${i}` }); };
      tx.oncomplete = () => r(); }; }));
    const nBic = await page.evaluate(() => new Promise(r => { const q = indexedDB.open('certquiz'); q.onsuccess = () => {
      const g = q.result.transaction('mistakes').objectStore('mistakes').getAll(); g.onsuccess = () => r(g.result.filter(x => x.cert === 'bic').length); }; }));
    check(`準備：內控錯題灌到三位數（${nBic} 筆）`, nBic >= 120);
    for (const [w, hgt] of [[390, 844], [320, 640]]) {
      await page.setViewport({ width: w, height: hgt, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
      await gotoView(page, base + '?r=' + Date.now() + '#/');
      await page.waitForSelector('.actions');
      const g = await homeGrid(page);
      const flat = g.flatMap(c => c.w), hs = g.flatMap(c => c.h);
      const ok = g.length === 2 && g.every(c => c.x.length === 2) && JSON.stringify(g[0].x) === JSON.stringify(g[1].x)
        && Math.max(...flat) - Math.min(...flat) <= 1 && Math.max(...hs) - Math.min(...hs) <= 1;
      check(`首頁 ${w}px：兩張卡片的按鈕都排成兩欄、全部等寬（${Math.min(...flat)}～${Math.max(...flat)}px）、等高（${Math.min(...hs)}～${Math.max(...hs)}px），欄位置對齊`,
        ok, JSON.stringify(g));
      const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(`首頁 ${w}px：沒有橫向捲動`, wide <= 1, `超出 ${wide}px`);
    }
    const order = await page.$$eval('#view .card .actions', as => as.map(a => [...a.querySelectorAll('.btn')].map(b => b.textContent.replace(/ \d+$/, ''))));
    check(`首頁：兩張卡片前四個按鈕順序相同（${order[0] ? order[0].slice(0, 4).join('、') : ''}）`,
      order.length === 2 && JSON.stringify(order[0].slice(0, 4)) === JSON.stringify(order[1].slice(0, 4)), JSON.stringify(order));
    const mk = await page.$eval('#view .card .actions a[href*="cert=bic&mode=mistakes"]', b => b.textContent);
    check(`首頁：錯題數三位數（${mk}）時，上面兩種寬度量到的按鈕仍是一行、等高`, /^錯題複習 1\d\d$/.test(mk), mk);
    check('首頁：模擬考按鈕寫科目名，沒有括號（「模擬考：法規」「模擬考：實務」）',
      order.length === 2 && JSON.stringify(order[0].slice(4)) === JSON.stringify(['模擬考：法規', '模擬考：實務']), JSON.stringify(order[0]));
    // 大綱目錄：讀過的細項用文字標「已讀」，不靠連結顏色
    await gotoView(page, base + '?r=' + Date.now() + '#/study?cert=az900');
    await page.waitForSelector('.item');
    const marks = await page.$$eval('a.item', as => as.map(a => a.querySelector('.meta').textContent));
    check(`大綱目錄：讀過的細項用文字標「已讀」（只讀過 A.1 第 1 項 → 只有第 1 列有；共 ${marks.length} 列）`,
      marks.length === 57 && marks.filter(t => t.includes('已讀')).length === 1 && marks[0].includes('已讀'), JSON.stringify(marks.slice(0, 3)));
    if (shots.length) console.log(`   截圖 ${shots.length} 張 → ${shotDir}`);
    check('外觀測試：沒有頁面錯誤', errors.length === 0, errors.join('；'));
  } finally {
    await ctx.close();
  }
}

// ---------------------------------------------------------------- 二之三、題庫檔讀不到
// 某張證照的題庫檔讀不到時，只有那一張卡片顯示錯誤，首頁其他部分照常（2026-10-08 之前會整頁掛掉）
async function missingBankTest(browser) {
  console.log('== 二之三、網站附的題庫檔讀不到時，首頁不能整頁掛掉');
  const site = makeSite(dir => rmSync(join(dir, 'data', 'q'), { recursive: true, force: true }));
  const { proc, origin } = await serve(site);
  const ctx = await browser.createBrowserContext();
  try {
    const page = await newPage(ctx, []);
    await page.goto(origin + '/');
    await waitText(page, '證照題庫練習').then(() => check('題庫檔不存在時首頁照樣出來', true),
      e => check('題庫檔不存在時首頁照樣出來', false, e.message));
    const t = await text(page);
    check('AZ-900 卡片顯示「題庫暫時讀不到」，內控卡片照常', t.includes('題庫暫時讀不到') && t.includes('還沒有題目'), t.slice(0, 300));
  } finally {
    await ctx.close();
    proc.kill();
    rmSync(site, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------- 三、端到端突變
async function mutationTest(browser) {
  console.log('== 三、端到端突變（App 偷送資料，判定必須紅）');
  const site = makeSite(dir => {
    const p = join(dir, 'js', 'app.js');
    const src = readFileSync(p, 'utf-8');
    const anchor = '      results.push({ item, k, correct });';
    if (!src.includes(anchor)) throw new Error('突變錨點找不到');
    writeFileSync(p, src.replace(anchor, anchor + "\n      navigator.sendBeacon('data/leak', item.id);"));
  });
  const { proc, origin } = await serve(site);
  const mon = new Monitor(browser, origin + '/');
  const ctx = await browser.createBrowserContext();
  try {
    const page = await newPage(ctx, []);
    await page.goto(origin + '/');
    await waitText(page, '證照題庫練習');
    await importPack(page, PACK, JSON.parse(readFileSync(PACK, 'utf-8')).counts.active);
    const i0 = mon.mark();
    await practiceRound(page, 10);
    await sleep(500);
    const bad = mon.bad(mon.since(i0));
    check('App 每答一題偷送一筆 → 實測判定抓到（必須紅）', bad.some(r => r.url.includes('data/leak')) ,
      `抓到 ${bad.length} 筆違規：${bad.map(r => r.url).join('；')}`);
  } finally {
    await ctx.close();
    proc.kill();
    rmSync(site, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------- 線上模式：關掉再開，紀錄還在
// 用保留資料的瀏覽器設定檔（userDataDir），第一次開：匯入＋練一輪；整個瀏覽器關掉；第二次用同一個設定檔開：紀錄必須還在。
async function liveTest(base) {
  console.log(`== 線上實測：${base}`);
  const pack = JSON.parse(readFileSync(PACK, 'utf-8'));
  const profile = mkdtempSync(join(tmpdir(), `certquiz-profile-${process.pid}-`));
  let st1;
  const allRecs = [];
  try {
    // 第一次開
    let browser = await puppeteer.launch({ headless: true, userDataDir: profile, args: ['--no-first-run'] });
    let mon = new Monitor(browser, base);
    try {
      if (!(await ruler(browser, base, mon))) return false;
      const errors = [];
      const i0 = mon.mark();
      const page = await newPage(browser.defaultBrowserContext(), errors);
      await gotoView(page, base);
      await waitText(page, '證照題庫練習');
      await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
      await importPack(page, PACK, pack.counts.active);
      await practiceRound(page, 10);
      st1 = await idbState(page);
      check(`線上第一次：匯入 ${st1.user} 題、作答 ${st1.attempts} 筆`, st1.user === pack.counts.total && st1.attempts === 10, JSON.stringify(st1));
      check('線上第一次：沒有頁面錯誤', errors.length === 0, errors.join('；'));
      allRecs.push(...mon.since(i0));
    } finally {
      await browser.close();
    }
    // 第二次開（同一個設定檔）
    browser = await puppeteer.launch({ headless: true, userDataDir: profile, args: ['--no-first-run'] });
    mon = new Monitor(browser, base);
    try {
      const page = await newPage(browser.defaultBrowserContext(), []);
      const i0 = mon.mark();
      await gotoView(page, base);
      await waitText(page, `可練 ${pack.counts.active} 題`);
      const t = await text(page);
      const st2 = await idbState(page);
      check(`關掉再開：首頁顯示可練 ${pack.counts.active} 題、已作答 10 次`, t.includes('已作答 10 次'), t.slice(0, 200));
      check('關掉再開：IndexedDB 的作答、錯題、匯入題都還在且與關閉前相同',
        st2.attempts === st1.attempts && st2.mistakes === st1.mistakes && st2.user === st1.user, `${JSON.stringify(st1)} → ${JSON.stringify(st2)}`);
      // 線上的外觀：深色＋淺色逐畫面算對比、首頁按鈕格線（請求也算進下面的「只連自己網站」）
      await lookTest(browser, base, process.env.CERTQUIZ_SHOTS || '');
      allRecs.push(...mon.since(i0));
    } finally {
      await browser.close();
    }
    const bad = new Monitor({ on() {}, targets: () => [] }, base).bad(allRecs);
    check(`線上：全部 ${allRecs.length} 筆請求都是 ${base} 底下的 GET`, bad.length === 0, bad.slice(0, 5).map(r => `${r.method} ${r.url}`).join('；'));
    return true;
  } finally {
    rmSync(profile, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------- 主程式
// 這次執行建立的暫存目錄：只看本專案自己命名的前綴（certquiz-…-<pid>-）。
// 不看 puppeteer_dev_*：同一台機器上其他專案也會同時跑 puppeteer（2026-10-08 實測：MealMate 的測試），
// 用「執行期間多出來的 puppeteer_dev 目錄」判斷會把別人的算成自己的，清理時更會刪到別人的。
// 瀏覽器關閉後 Windows 上刪目錄可能慢幾秒：等最多 10 秒，還在的自己刪（都是本次建立、本專案前綴的），刪不掉才回報。
async function leftovers(prefixes) {
  const mine = () => readdirSync(tmpdir()).filter(n => prefixes.some(p => n.startsWith(p)));
  for (let t = 0; t < 20 && mine().length; t++) await sleep(500);
  for (const n of mine()) { try { rmSync(join(tmpdir(), n), { recursive: true, force: true }); } catch { /* 下面會回報 */ } }
  return mine();
}

async function main() {
  if (!existsSync(PACK)) { console.log('TEST-BROWSER ABORT：本機沒有匯入包（先跑 python scripts/build_data.py --local）'); return 2; }
  const liveIdx = process.argv.indexOf('--live');
  let code = 0;
  if (liveIdx > 0) {
    const base = process.argv[liveIdx + 1].replace(/\/?$/, '/');
    try {
      if (!(await liveTest(base))) { console.log('TEST-BROWSER ABORT：驗尺失敗，不下結論'); return 2; }
      code = fails ? 1 : 0;
    } finally {
      const left = await leftovers([`certquiz-profile-${process.pid}-`]);
      if (left.length) { console.log(`✗ 暫存目錄沒清掉：${left.join('、')}`); code = 1; }
    }
    console.log(code ? `TEST-BROWSER FAILED：${fails} 項不符${failed.length ? '（' + failed.join('｜') + '）' : '（暫存目錄沒清掉）'}` : 'TEST-BROWSER OK（線上）：驗尺 5 項＋關掉再開＋外觀（深色／淺色）全部符合');
    return code;
  }
  const site = makeSite();
  const { proc, origin } = await serve(site);
  const base = origin + '/';
  // 用本專案命名的設定檔目錄（不用 puppeteer 預設的 puppeteer_dev_*，見 leftovers 的說明）
  const chromeDir = mkdtempSync(join(tmpdir(), `certquiz-chrome-${process.pid}-`));
  const browser = await puppeteer.launch({ headless: true, userDataDir: chromeDir, args: ['--no-first-run'] });
  try {
    const mon = new Monitor(browser, base);
    if (!(await ruler(browser, base, mon))) {
      console.log('TEST-BROWSER ABORT：驗尺失敗——監測器沒證明抓得到，後面的「沒有外部請求」不能下結論');
      return 2;
    }
    await realTest(browser, base, mon);
    if (!(await examTest(browser, base))) {
      console.log('TEST-BROWSER ABORT：撥時間的驗尺失敗——「時間到自動交卷」不能下結論');
      return 2;
    }
    await swInstallTest(browser);
    await minimalTest(browser, base);
    await studyTest(browser, base);
    await importStudyTest(browser, base);
    await lookTest(browser, base, process.env.CERTQUIZ_SHOTS || '');
    await missingBankTest(browser);
    check(`全畫面掃描：整個測試期間所有頁面都沒有出現 null／undefined／NaN`, BAD_TEXT.length === 0,
      BAD_TEXT.slice(0, 8).map(x => `「${x.t}」@${x.where}`).join('；'));
    await mutationTest(browser);
    code = fails ? 1 : 0;
  } finally {
    await browser.close();
    proc.kill();
    rmSync(site, { recursive: true, force: true });
    const left = await leftovers([`certquiz-site-${process.pid}-`, `certquiz-chrome-${process.pid}-`]);
    if (left.length) { console.log(`✗ 暫存目錄沒清掉：${left.join('、')}`); code = 1; }
  }
  console.log(code ? `TEST-BROWSER FAILED：${fails} 項不符${failed.length ? '（' + failed.join('｜') + '）' : '（暫存目錄沒清掉）'}` : 'TEST-BROWSER OK：驗尺 5 項＋實測＋端到端突變全部符合');
  return code;
}

main().then(c => process.exit(c), e => { console.log(`TEST-BROWSER ERROR：${e.stack || e}`); process.exit(2); });
