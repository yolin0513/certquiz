// js/logic.js 的測試（node，不需要瀏覽器）。真的匯入包在本機才有；沒有就只跑合成樣本。
// 用法：node scripts/test_logic.mjs   結束碼 0 全部符合、1 有不符
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as L from '../js/logic.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
let fails = 0;
const check = (desc, ok, detail = '') => {
  console.log(`${ok ? '✓' : '✗'} ${desc}${ok ? '' : '：' + detail}`);
  if (!ok) fails++;
};

const q = (id, extra = {}) => ({ id, cert: 'bic', subject: 'law', chapter: 'bic.law', type: 'single',
  stem: '題幹' + id, options: ['甲', '乙', '丙', '丁'], answer: 2, source: 'tabf-official', period: 47, qno: 1, ...extra });
const pack = (qs, extra = {}) => ({ format: L.IMPORT_FORMAT, version: L.IMPORT_VERSION, cert: 'bic', questions: qs, ...extra });

// 匯入包驗證：好的收、壞的整包不收而且點名
check('合格匯入包通過', L.validateImportPack(pack([q('bic-law-t47-001')]), ['bic']).ok);
const bad = [
  ['format 不對', pack([q('bic-law-t47-001')], { format: 'other' }), 'format'],
  ['答案超出 1～4', pack([q('bic-law-t47-001', { answer: 5 })]), 'bic-law-t47-001'],
  ['少一個選項', pack([q('bic-law-t47-001', { options: ['甲', '乙', '丙'] })]), 'bic-law-t47-001'],
  ['id 重複', pack([q('bic-law-t47-001'), q('bic-law-t47-001')]), 'id 重複'],
  ['dupOf 指到不存在的題', pack([q('bic-law-t47-001', { dupOf: 'bic-law-t47-999' })]), 'bic-law-t47-999'],
  ['證照不認得', pack([q('bic-law-t47-001')], { cert: 'xyz' }), 'xyz'],
  ['一題壞、其他都好 → 整包不收', pack([q('bic-law-t47-001'), q('bic-law-t47-002', { stem: '' })]), 'bic-law-t47-002'],
];
for (const [desc, p, token] of bad) {
  const r = L.validateImportPack(p, ['bic']);
  check(`擋下：${desc}（點名 ${token}）`, !r.ok && r.questions.length === 0 && r.errors.some(e => e.includes(token)), JSON.stringify(r.errors));
}

// 選題：重複題不出、科目與來源篩選、題數、未做過優先、同種子可重現
const pool = [q('bic-law-t47-001'), q('bic-law-t47-002', { dupOf: 'bic-law-t47-001' }),
  q('bic-gen-t47-001', { subject: 'gen', chapter: 'bic.gen' }), q('bic-law-u40-001', { source: 'user-import', period: 40 })];
const all = L.pickQuestions(pool, { subject: 'all', source: 'all', count: 99, order: 'random', seed: 1 });
check('重複題（dupOf）不會被選到', !all.some(x => x.id === 'bic-law-t47-002') && all.length === 3, all.map(x => x.id).join(','));
check('科目篩選', L.pickQuestions(pool, { subject: 'gen', count: 9, seed: 1 }).every(x => x.subject === 'gen'));
check('來源篩選：只出官網', L.pickQuestions(pool, { source: 'official', count: 9, seed: 1 }).every(x => x.source === 'tabf-official'));
check('來源篩選：只出使用者提供', L.pickQuestions(pool, { source: 'user', count: 9, seed: 1 }).map(x => x.id).join() === 'bic-law-u40-001');
check('題數上限', L.pickQuestions(pool, { count: 2, seed: 1 }).length === 2);
const prog = new Map([['bic-law-t47-001', { seen: 3 }], ['bic-gen-t47-001', { seen: 1 }]]);
const un = L.pickQuestions(pool, { order: 'unseen', count: 9, seed: 7 }, prog);
check('未做過的題排在前面', un[0].id === 'bic-law-u40-001', un.map(x => x.id).join(','));
const s1 = L.pickQuestions(pool, { count: 9, seed: 42 }).map(x => x.id).join();
const s2 = L.pickQuestions(pool, { count: 9, seed: 42 }).map(x => x.id).join();
check('同一個種子抽到同一組（可重現）', s1 === s2);

// 錯題本規則
check('答錯 → 進錯題本', L.nextMistakeState(null, false, 'practice', 1)?.wrongCount === 1);
check('一般練習答對 → 不移出', L.nextMistakeState({ wrongCount: 1, streak: 0 }, true, 'practice', 2)?.wrongCount === 1);
const m1 = L.nextMistakeState({ wrongCount: 1, streak: 0 }, true, 'mistakes', 3);
check(`錯題模式答對 1 次 → 還在（要連續 ${L.MISTAKE_CLEAR_STREAK} 次）`, m1?.streak === 1);
check('錯題模式連續答對 2 次 → 移出', L.nextMistakeState(m1, true, 'mistakes', 4) === null);
check('錯題模式答對後又答錯 → 連續次數歸零', L.nextMistakeState(m1, false, 'mistakes', 5)?.streak === 0);

// 出處標示：原創題一定寫「不是考題」
check('原創題標「不是考題」', L.sourceLabel({ source: 'original-ai' }).includes('不是考題'));
check('原創題標大綱節次與細項', L.sourceLabel({ source: 'original-ai', objective: 'B.3', skill: 2 }) === '原創練習題，不是考題・官方大綱 B.3（第 2 細項）');
check('依據網址原樣當文字', L.basisText({ basis: 'https://learn.microsoft.com/en-us/x' }) === '依據（官方文件）：https://learn.microsoft.com/en-us/x');
check('沒有依據就不顯示', L.basisText({}) === '');
check('官方題不帶大綱標示', !L.sourceLabel(q('x', { objective: 'B.3' })).includes('大綱'));
check('官方題標期別、題號、法規基準', /第 47 期第 1 題.*法規基準：2025-03-17/.test(L.sourceLabel(q('x', { law_as_of: '2025-03-17' }))));

// 模擬考：出卷
const examPool = [...Array(60)].map((_, i) => q(`bic-law-t47-${String(i + 1).padStart(3, '0')}`))
  .concat([q('bic-law-t47-900', { dupOf: 'bic-law-t47-001' }), q('bic-gen-t47-001', { subject: 'gen', chapter: 'bic.gen' })]);
const ex = L.buildExam(examPool, 'law', 50, 3);
check('出卷：法規 50 題、都是法規、沒有重複題、沒有重號', ex.ok && ex.questions.length === 50 &&
  ex.questions.every(x => x.subject === 'law' && !x.dupOf) && new Set(ex.questions.map(x => x.id)).size === 50);
// 不靠機率的版本：49 題可練＋5 題重複 → 重複題不算，題數不足 50，不能出卷（若把重複題也算進去就會出卷）
const pool49 = [...Array(49)].map((_, i) => q(`bic-law-t48-${String(i + 1).padStart(3, '0')}`))
  .concat([...Array(5)].map((_, i) => q(`bic-law-u40-${String(i + 1).padStart(3, '0')}`, { dupOf: 'bic-law-t48-001' })));
const ex49 = L.buildExam(pool49, 'law', 50, 3);
check('出卷：重複題不算進可出題數（49 題可練＋5 題重複 → 不足 50，不出卷）', !ex49.ok && ex49.available === 49, JSON.stringify({ ok: ex49.ok, available: ex49.available }));
const short = L.buildExam(examPool, 'gen', 80, 3);
check('出卷：題數不夠就不出（不用不足的題數考）', !short.ok && short.available === 1 && short.questions.length === 0);
check('出卷：同一個種子出同一份卷', L.buildExam(examPool, 'law', 50, 9).questions.map(x => x.id).join() ===
  L.buildExam(examPool, 'law', 50, 9).questions.map(x => x.id).join());

// 模擬考：計分（及格線的邊界）
const gen80 = [...Array(80)].map((_, i) => ({ id: `g${i}`, answer: 1 }));
const ans = n => new Map(gen80.slice(0, n).map(x => [x.id, 1]));
const s56 = L.scoreExam(gen80, ans(56), { points: 1.25, pass: 70 });
check('計分：實務 56／80 題 → 70 分，剛好及格', s56.score === 70 && s56.passed, JSON.stringify(s56));
const s55 = L.scoreExam(gen80, ans(55), { points: 1.25, pass: 70 });
check('計分：實務 55／80 題 → 68.75 分，不及格', s55.score === 68.75 && !s55.passed, JSON.stringify(s55));
const mixed = new Map([['g0', 1], ['g1', 2], ['g2', 1]]);
const sm = L.scoreExam(gen80.slice(0, 5), mixed, { points: 2, pass: 70 });
check('計分：答對、答錯、未作答分開算，未作答不給分', sm.correct === 2 && sm.wrong === 1 && sm.unanswered === 2 && sm.score === 4, JSON.stringify(sm));
check('時鐘：60 分鐘 → 1:00:00；90 分鐘 → 1:30:00；59 秒 → 00:59；剩 0.4 秒 → 00:01（無條件進位，不會提早顯示 00:00）',L.formatClock(3600000) === '1:00:00' &&
  L.formatClock(5400000) === '1:30:00' && L.formatClock(400) === '00:01' && L.formatClock(59000) === '00:59');
check('剩餘時間不會是負的', L.remainingMs(1000, 5000) === 0 && L.remainingMs(5000, 1000) === 4000);

// 統計：依科目分組
const byId = new Map([['a', { subject: 'law' }], ['b', { subject: 'gen' }]]);
const gr = L.groupRate([{ qid: 'a', correct: true }, { qid: 'a', correct: false }, { qid: 'b', correct: true }, { qid: 'zz', correct: true }], byId, x => x.subject);
check('統計：依科目分組的答對率（找不到的題不算）', gr.get('law').rate === 0.5 && gr.get('gen').rate === 1 && gr.size === 2);

// 真的匯入包（本機才有）
const real = join(ROOT, 'data', 'local', 'import', 'bic-匯入包.json');
if (existsSync(real)) {
  const r = L.validateImportPack(JSON.parse(readFileSync(real, 'utf-8')), ['bic', 'az900']);
  const active = r.questions.filter(L.isActive).length;
  check(`真的匯入包通過驗證（${r.questions.length} 題、可練 ${active} 題）`, r.ok && r.questions.length === 910 && active === 801, r.errors.slice(0, 3).join('；'));
} else {
  console.log('• 本機沒有匯入包，略過真檔測試');
}

console.log(fails ? `TEST-LOGIC FAILED：${fails} 項不符` : 'TEST-LOGIC OK：全部符合');
process.exit(fails ? 1 : 0);
