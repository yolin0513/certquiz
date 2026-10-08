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
const check = (desc, ok, detail = '') => {
  console.log(`${ok ? '✓' : '✗'} ${desc}${ok ? '' : '：' + detail}`);
  if (!ok) fails++;
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

async function newPage(ctx, errors) {
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
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
  await page.goto(base);
  await waitText(page, '證照題庫練習');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  let ok = true;
  const has = (i, f) => mon.since(i).some(f);

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
  await page.goto(page.url().split('#')[0] + `#/setup?cert=bic`);
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
  await page.goto(page.url().split('#')[0] + '#/settings');
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
  await page.goto(base);
  await waitText(page, '證照題庫練習');
  check('首頁：沒匯入前內控顯示「還沒有題目」', (await text(page)).includes('還沒有題目'));
  check(`首頁：AZ-900 顯示可練 ${AZ.length} 題（網站附的原創題）`, (await text(page)).includes(`可練 ${AZ.length} 題`), (await text(page)).slice(0, 400));
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));

  await importPack(page, PACK, pack.counts.active);
  await page.goto(base + '#/');
  await waitText(page, `可練 ${pack.counts.active} 題`);
  check(`匯入後首頁顯示可練 ${pack.counts.active} 題`, true);

  const stems = await practiceRound(page, 10);
  const summary = await page.$eval('h2', e => e.textContent);
  check(`練完一輪 10 題，出現結果頁（${summary}）`, stems.length === 10 && /銀行內控：\d+ \/ 10（\d+%）/.test(summary), summary);
  const st = await idbState(page);
  check('IndexedDB：作答 10 筆、每題彙總 10 筆（或同題合併）', st.attempts === 10 && st.progress >= 1 && st.progress <= 10, JSON.stringify(st));
  check('IndexedDB：錯題本筆數＝這一輪答錯的題數', st.mistakes === st.wrong, JSON.stringify(st));
  check(`IndexedDB：匯入的題目 ${pack.counts.total} 題都在`, st.user === pack.counts.total, JSON.stringify(st));
  check('重複題（dupOf）沒有被出題', st.dupAnswered === 0, JSON.stringify(st));

  // 模擬考：法規 50 題，答 45 題、留 5 題不答，交卷
  await page.goto(base + '#/exam?cert=bic&subject=law');
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
  await page.goto(base + '#/stats?cert=bic');
  await waitText(page, '最近的模擬考');
  const statsText = await text(page);
  check('統計頁：顯示作答次數、依科目與來源分組、這次模擬考', statsText.includes(`作答 ${st2.attempts} 次`) && statsText.includes('依科目') &&
    statsText.includes('依題目來源') && statsText.includes(String(h0.score)), statsText.slice(0, 300));

  // 頁面離線模式＋真的重新載入（只改 hash 不會重載——2026-10-08 發現先前這一項就是這樣）。
  // 注意：puppeteer 的離線模式只管頁面，SW 自己的請求仍可能連網；「真的斷線」在二之四（關掉伺服器）驗。
  await page.evaluate(() => { window.__notReloaded = 1; });
  await page.setOfflineMode(true);
  await page.goto(base + '#/');
  await page.reload();
  await waitText(page, `可練 ${pack.counts.active} 題`).then(() => check('頁面離線模式重新載入：首頁照樣顯示內控題數', true),
    e => check('頁面離線模式重新載入：首頁照樣顯示內控題數', false, e.message));
  check('頁面離線模式重新載入：頁面真的重新載入了（記號已消失）', await page.evaluate(() => window.__notReloaded === undefined));
  await page.setOfflineMode(false);
  // AZ-900 練 3 題：作答前有原創標示＋大綱節次、作答後有依據網址（文字）、卡片裡沒有連結
  await page.goto(base + '#/practice?cert=az900&mode=practice&count=3');
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
    await page.goto(base);
    await waitText(page, '證照題庫練習');
    await importPack(page, PACK, pack.counts.active);

    // A. 實務 80 題全部作答：前 56 題答對、後 24 題答錯 → 56 × 1.25 ＝ 70 分，剛好在及格線上
    await page.goto(base + '#/exam?cert=bic&subject=gen');
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
    await page.goto(base + '#/exam?cert=bic&subject=law');
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
    await page.goto(base + 'sw-probe.html');
    await page.waitForFunction(() => window.__swReady === true, { timeout: 20000 });
    const keys = await page.evaluate(async () => {
      const out = [];
      for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
      return out;
    });
    check('探針頁（不跑 App）之後，SW 快取裡已有 data/q/az900.json', keys.some(k => k.endsWith('/data/q/az900.json')), keys.join('、'));
    // 只用探針頁裝好 SW；App 第一次開就直接匯入內控題，之後斷線
    await page.goto(base + '#/settings');
    await importPack(page, PACK, pack.counts.active);
    proc.kill(); alive = false;
    await sleep(300);
    // 驗尺：伺服器真的關了——一個從沒快取過的檔，經過 SW 也必須拿不到
    const probe = await page.evaluate(() => fetch('never-cached-' + Math.random() + '.txt').then(r => 'reached ' + r.status, () => 'offline'));
    const rulerOk = probe === 'offline';
    check(`驗尺：關掉伺服器後，沒快取過的檔拿不到（${probe}）`, rulerOk);
    if (!rulerOk) return;
    // 匯入後頁面停在設定頁（設定頁也有「可練 N 題」字樣），先切回首頁再重新載入，題數只在確認是首頁之後判定
    await page.goto(base + '#/');
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
    await page.goto(base + '#/practice?cert=az900&mode=practice&count=2');
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
      await page.goto(base);
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
      await page.goto(base);
      await waitText(page, `可練 ${pack.counts.active} 題`);
      const t = await text(page);
      const st2 = await idbState(page);
      check(`關掉再開：首頁顯示可練 ${pack.counts.active} 題、已作答 10 次`, t.includes('已作答 10 次'), t.slice(0, 200));
      check('關掉再開：IndexedDB 的作答、錯題、匯入題都還在且與關閉前相同',
        st2.attempts === st1.attempts && st2.mistakes === st1.mistakes && st2.user === st1.user, `${JSON.stringify(st1)} → ${JSON.stringify(st2)}`);
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
async function main() {
  if (!existsSync(PACK)) { console.log('TEST-BROWSER ABORT：本機沒有匯入包（先跑 python scripts/build_data.py --local）'); return 2; }
  const before = new Set(readdirSync(tmpdir()).filter(n => n.startsWith('puppeteer_dev')));
  const liveIdx = process.argv.indexOf('--live');
  let code = 0;
  if (liveIdx > 0) {
    const base = process.argv[liveIdx + 1].replace(/\/?$/, '/');
    try {
      if (!(await liveTest(base))) { console.log('TEST-BROWSER ABORT：驗尺失敗，不下結論'); return 2; }
      code = fails ? 1 : 0;
    } finally {
      const left = readdirSync(tmpdir()).filter(n => (n.startsWith('puppeteer_dev') && !before.has(n)) || n.startsWith(`certquiz-profile-${process.pid}`));
      if (left.length) { console.log(`✗ 暫存目錄沒清掉：${left.join('、')}`); code = 1; }
    }
    console.log(code ? `TEST-BROWSER FAILED：${fails} 項不符` : 'TEST-BROWSER OK（線上）：驗尺 5 項＋關掉再開全部符合');
    return code;
  }
  const site = makeSite();
  const { proc, origin } = await serve(site);
  const base = origin + '/';
  const browser = await puppeteer.launch({ headless: true, args: ['--no-first-run'] });
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
    await missingBankTest(browser);
    await mutationTest(browser);
    code = fails ? 1 : 0;
  } finally {
    await browser.close();
    proc.kill();
    rmSync(site, { recursive: true, force: true });
    const left = readdirSync(tmpdir()).filter(n => (n.startsWith('puppeteer_dev') && !before.has(n)) || n.startsWith(`certquiz-site-${process.pid}`));
    if (left.length) { console.log(`✗ 暫存目錄沒清掉：${left.join('、')}`); code = 1; }
  }
  console.log(code ? `TEST-BROWSER FAILED：${fails} 項不符` : 'TEST-BROWSER OK：驗尺 5 項＋實測＋端到端突變全部符合');
  return code;
}

main().then(c => process.exit(c), e => { console.log(`TEST-BROWSER ERROR：${e.stack || e}`); process.exit(2); });
