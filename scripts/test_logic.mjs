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
check('官方題標期別、題號、法規基準', /第 47 期第 1 題.*法規基準：2025-03-17/.test(L.sourceLabel(q('x', { law_as_of: '2025-03-17' }))));

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
