// 本機 HTML（例：金融市場常識與職業道德重點整理）的外觀檢查：iPhone 寬度、深色與淺色各一輪，
// 用 App 同一套逐元素對比檢查（scripts/audit_lib.mjs，含母體核對）、主題色、沒有橫向捲動；各截一張圖。
// 用法：node scripts/check_html.mjs <HTML 檔> [截圖目錄]
// 結論只寫進記錄檔（data/local/logs/，正式／非正式自動分開，跟 verify_live、test_browser 同一套規矩）；畫面只印記錄檔路徑。
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { mkdirSync, appendFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { AUDIT, AUDIT_RULER } from './audit_lib.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const puppeteer = createRequire(join(process.env.PUPPETEER_FROM || join(ROOT, '..', 'JLPT_App'), 'package.json'))('puppeteer');
const st = spawnSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: ROOT, encoding: 'utf-8' });
const official = st.status === 0 && !(st.stdout || '').trim();
const LOGDIR = process.env.CERTQUIZ_LOGDIR || join(ROOT, 'data', 'local', 'logs', ...(official ? [] : ['unofficial']));
mkdirSync(LOGDIR, { recursive: true });
const LOG = join(LOGDIR, `check-html-${new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)}${official ? '' : '-UNOFFICIAL'}.log`);
const out = (...a) => appendFileSync(LOG, `${new Date().toTimeString().slice(0, 8)} ${a.join(' ')}\n`);
process.stdout.write(`CHECK-HTML：完整輸出與結論都寫在 ${LOG}（畫面不印結論；結束碼 0＝全部符合、1＝有不符、2＝中止）\n`);

let fails = 0;
const failed = [];
const check = (desc, ok, detail = '') => { out(`${ok ? '✓' : '✗'} ${desc}${ok ? '' : '：' + detail}`); if (!ok) { fails++; failed.push(desc); } };

async function main() {
  const file = process.argv[2];
  const shots = process.argv[3];
  if (!file || !existsSync(file)) { out(`CHECK-HTML ABORT：找不到檔案 ${file}`); return 2; }
  out(`開始｜${official ? '正式執行' : '非正式執行'}｜${resolve(file)}`);
  const prof = mkdtempSync(join(tmpdir(), `certquiz-chrome-${process.pid}-`));
  const browser = await puppeteer.launch({ headless: true, userDataDir: prof, args: ['--no-first-run'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    await page.goto(pathToFileURL(resolve(file)).href);
    const rr = await page.evaluate(AUDIT_RULER);
    const rulerOk = Math.abs(rr[0] - 4.54) < 0.01 && Math.abs(rr[1] - 4.48) < 0.01 && Math.abs(rr[2] - 21) < 0.01;
    check(`驗尺：對比公式對已知值（${rr.map(x => x.toFixed(2)).join('、')}）`, rulerOk);
    if (!rulerOk) return 2;
    for (const scheme of ['dark', 'light']) {
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }]);
      await page.reload();
      const a = await page.evaluate(AUDIT, 'body');
      const nm = scheme === 'dark' ? '深色' : '淺色';
      check(`${nm}：母體——畫面上的文字元素 ${a.population} 個＝量到的 ${a.n + a.exempt} 個`, a.population === a.n + a.exempt && a.missed.length === 0 && a.population > 50, a.missed.slice(0, 5).join('；'));
      check(`${nm}：${a.n} 個文字元素對比都達 WCAG AA（最低 ${a.minRatio.toFixed(2)}:1 @ ${a.minAt}）`, a.fails.length === 0, a.fails.slice(0, 6).join('；'));
      check(`${nm}：連結、摺疊標題等的文字色都是主題色（沒有落回瀏覽器預設）`, a.untoken.length === 0, a.untoken.slice(0, 6).join('；'));
      const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(`${nm}：390px 沒有橫向捲動`, wide <= 1, `超出 ${wide}px`);
      if (shots) { mkdirSync(shots, { recursive: true }); await page.screenshot({ path: join(shots, `${scheme}-top.png`) });
        await page.evaluate(() => document.getElementById('eth')?.scrollIntoView()); await page.screenshot({ path: join(shots, `${scheme}-eth.png`) }); }
    }
    check('沒有頁面錯誤', errors.length === 0, errors.join('；'));
  } finally {
    await browser.close();
    rmSync(prof, { recursive: true, force: true });
  }
  out(fails ? `CHECK-HTML FAILED：${fails} 項不符（${failed.join('｜')}）` : 'CHECK-HTML OK：全部符合');
  return fails ? 1 : 0;
}
main().then(c => process.exit(c), e => { out(`CHECK-HTML ERROR：${e.stack || e}`); process.exit(2); });
