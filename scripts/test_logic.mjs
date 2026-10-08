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
check('依據帶章節錨點與標題', L.basisText({ basis: 'https://learn.microsoft.com/en-us/x', basis_anchor: '#lock-inheritance', basis_section: 'Lock inheritance' }) === '依據（官方文件）：https://learn.microsoft.com/en-us/x#lock-inheritance（章節：Lock inheritance）');
check('錨點是頁首（#）就只顯示網址', L.basisText({ basis: 'https://learn.microsoft.com/en-us/x', basis_anchor: '#' }) === '依據（官方文件）：https://learn.microsoft.com/en-us/x');
check('官方題不帶大綱標示', !L.sourceLabel(q('x', { objective: 'B.3' })).includes('大綱'));
check('官方題標期別、題號、法規基準', /第 47 期第 1 題.*法規基準：2025-03-17/.test(L.sourceLabel(q('x', { law_as_of: '2025-03-17' }))));

// 缺欄位：畫面文字不得出現 null／undefined／NaN，也不得留下孤立的分隔符號（2026-10-08 使用者回報 nullnull 之後補）
const BAD = /null|undefined|NaN/;
check('出處：只有來源、沒有期別題號法規基準 → 只顯示來源名稱', L.sourceLabel({ source: 'tabf-official' }) === '官方歷屆試題');
check('出處：有期別、沒有題號 → 不出現 undefined', L.sourceLabel({ source: 'tabf-official', period: 47 }) === '官方歷屆試題・第 47 期');
check('出處：只有法規基準', L.sourceLabel({ source: 'user-import', law_as_of: '2025-03-17' }) === '使用者提供的官方歷屆試題・（法規基準：2025-03-17）');
check('出處：原創題沒有大綱節次 → 只有標示', L.sourceLabel({ source: 'original-ai' }) === '原創練習題，不是考題');
const brokenMsgs = L.validateImportPack({ format: 'certquiz-import', questions: [{ type: 'single', stem: 'x', options: ['a', 'b', 'c', 'd'], answer: 1 }, null] }, ['bic']).errors;
check('匯入檢查：缺版本、缺證照、缺 id、缺來源、null 題目時，錯誤訊息裡沒有 null／undefined',
  brokenMsgs.length >= 4 && !brokenMsgs.some(m => BAD.test(m)), brokenMsgs.join('；'));
// 讀書單元代號（記錄「作答前是否讀過」用）
check('讀書單元：AZ-900 是 證照:節次#細項', L.studyKey({ cert: 'az900', objective: 'B.3', skill: 2 }) === 'az900:B.3#2');
check('讀書單元：有主題的題目用主題', L.studyKey({ cert: 'bic', topic: '自行查核' }) === 'bic:topic:自行查核');
check('讀書單元：沒有單元的題目回 null（不記）', L.studyKey({ cert: 'bic', subject: 'law' }) === null);

// 內控讀書模式：考點清單與讀書單元
{
  const mk = (id, period, extra = {}) => ({ id, cert: 'bic', subject: 'law', type: 'single', stem: `題幹${id}`, options: ['甲', '乙', '丙', '丁'],
    answer: 2, source: 'tabf-official', period, ...extra });
  const base = { format: 'certquiz-import', version: 1, cert: 'bic' };
  const okPack = { ...base, questions: [mk('bic-law-t47-001', 47, { point: 'P001' }), mk('bic-law-u40-001', 40, { point: 'P001' }), mk('bic-law-t48-002', 48)],
    points: [{ id: 'P001', periods: [40, 47], ids: ['bic-law-t47-001', 'bic-law-u40-001'] }] };
  const r1 = L.validateImportPack(okPack, ['bic']);
  check('匯入檢查：合法的考點清單通過，並回傳考點', r1.ok && r1.points.length === 1, r1.errors.join('；'));
  const bad = (desc, mut, want) => {
    const p = JSON.parse(JSON.stringify(okPack)); mut(p);
    const r = L.validateImportPack(p, ['bic']);
    check(`匯入檢查：${desc} → 擋`, !r.ok && r.errors.some(e => e.includes(want)), r.errors.join('；'));
  };
  bad('考點代號格式不對', p => { p.points[0].id = 'X1'; }, '代號格式不對');
  bad('考點的題號不在包內', p => { p.points[0].ids[1] = 'bic-law-t99-001'; }, '題號清單不對');
  bad('考點只有一期', p => { p.points[0].periods = [47]; }, '期別至少要兩期');
  bad('題目標的考點跟清單不一致', p => { p.questions[1].point = 'P002'; }, '不在考點清單裡');
  bad('考點類別不是 list', p => { p.points[0].kind = 'topic'; }, '類別只能是 list');
  check('匯入檢查：類別 list（教材清單）通過', (() => { const p = JSON.parse(JSON.stringify(okPack)); p.points[0].kind = 'list'; return L.validateImportPack(p, ['bic']).ok; })());
  check('考點清單：教材清單類帶出 kind=list、沒寫類別的是 rule（同一條規定）',
    L.pointList([{ id: 'P001', kind: 'list', periods: [40, 47], ids: ['a', 'b'] }, { id: 'P002', periods: [40, 47], ids: ['c', 'd'] }],
      [mk('a', 40), mk('b', 47), mk('c', 40), mk('d', 47)]).map(x => x.kind).join() === 'list,rule');
  check('匯入檢查：舊版匯入包沒有考點 → 照樣通過、考點為空', (() => { const r = L.validateImportPack({ ...base, questions: [mk('bic-law-t48-002', 48)] }, ['bic']); return r.ok && r.points.length === 0; })());
  const pl = L.pointList([{ id: 'P001', periods: [47, 40], ids: ['bic-law-u40-001', 'bic-law-t47-001'] }],
    [mk('bic-law-u40-001', 40, { stem: '舊問法' }), mk('bic-law-t47-001', 47, { stem: '新問法' })]);
  check('考點清單：代表題是最新一期、其他期不同問法列在 variants、期別由小到大',
    pl.length === 1 && pl[0].rep.id === 'bic-law-t47-001' && pl[0].variants.length === 1 && pl[0].variants[0].stem === '舊問法' && pl[0].periods.join() === '40,47');
  check('考點清單：逐字相同的問法不重複列', L.pointList([{ id: 'P001', periods: [40, 47], ids: ['a', 'b'] }],
    [mk('a', 40, { stem: '同' }), mk('b', 47, { stem: '同' })])[0].variants.length === 0);
  check('考點清單：題目全被停用的考點略過', L.pointList([{ id: 'P001', periods: [40, 47], ids: ['a', 'b'] }],
    [mk('a', 40, { status: 'retired' }), mk('b', 47, { status: 'retired' })]).length === 0);
  check('讀書單元：內控題＝所屬考點＋科目期別頁', L.studyKeys(mk('bic-law-t47-001', 47, { point: 'P001' })).join() === 'bic:point:P001,bic:period:law:47');
  check('讀書單元：AZ-900 照舊只有節次#細項', L.studyKeys({ cert: 'az900', objective: 'B.3', skill: 2 }).join() === 'az900:B.3#2');
  const pool = [mk('bic-law-t47-001', 47), mk('bic-law-u40-001', 40), mk('bic-law-t48-002', 48)];
  check('選題：限定題號', L.pickQuestions(pool, { count: 10, ids: new Set(['bic-law-u40-001']), seed: 1 }).map(x => x.id).join() === 'bic-law-u40-001');
  check('選題：限定期別', L.pickQuestions(pool, { count: 10, period: '48', seed: 1 }).map(x => x.id).join() === 'bic-law-t48-002');
  const realPack = join(dirname(fileURLToPath(import.meta.url)), '..', 'data', 'local', 'import', 'bic-匯入包.json');
  if (existsSync(realPack)) {
    const rp = JSON.parse(readFileSync(realPack, 'utf-8'));
    const rr = L.validateImportPack(rp, ['bic', 'az900']);
    const rl = L.pointList(rr.points, rr.questions);
    check(`真的匯入包：考點 ${rr.points.length} 個全部通過檢查、每個考點都有可練的代表題`, rr.ok && rr.points.length > 0 && rl.length === rr.points.length, rr.errors.slice(0, 3).join('；'));
  }
}

// 讀書模式：依官方大綱分組
{
  const syl = { objectives: [{ id: 'A.1', name: 'n1', domain: 'D', skills: ['s1', 's2'] }, { id: 'B.1', name: 'n2', domain: 'E', skills: ['t1'] }] };
  const mk = (id, objective, skill, extra = {}) => ({ id, objective, skill, source: 'original-ai', ...extra });
  const g = L.studyGroups(syl, [mk('az900-a1-002', 'A.1', 1), mk('az900-a1-001', 'A.1', 1), mk('az900-a1-003', 'A.1', 2),
    mk('az900-b1-001', 'B.1', 1), mk('az900-z9-001', 'Z.9', 1), mk('az900-a1-004', 'A.1', 1, { status: 'retired' })]);
  check('讀書分組：題目歸到對的節次與細項、細項內依 id 排序', g.objectives[0].skills[0].questions.map(q => q.id).join() === 'az900-a1-001,az900-a1-002' &&
    g.objectives[0].skills[1].questions.length === 1 && g.objectives[0].count === 3 && g.objectives[1].count === 1);
  check('讀書分組：對不到大綱的題目放進 other（不默默丟掉）', g.other.length === 1 && g.other[0].id === 'az900-z9-001');
  check('讀書分組：停用（retired）的題目不出現', !JSON.stringify(g).includes('az900-a1-004'));
  const pool = [mk('az900-a1-001', 'A.1', 1), mk('az900-a1-003', 'A.1', 2), mk('az900-b1-001', 'B.1', 1)];
  const p1 = L.pickQuestions(pool, { count: 10, objective: 'A.1', skill: '2', seed: 1 });
  check('選題：只出指定節次與細項', p1.length === 1 && p1[0].id === 'az900-a1-003');
  check('選題：沒指定節次時照舊全部', L.pickQuestions(pool, { count: 10, seed: 1 }).length === 3);
  const root = join(dirname(fileURLToPath(import.meta.url)), '..');
  const man = JSON.parse(readFileSync(join(root, 'data', 'manifest.json'), 'utf-8'));
  const az = man.certs.find(c => c.id === 'az900');
  const real = JSON.parse(readFileSync(join(root, 'data', 'q', 'az900.json'), 'utf-8')).questions;
  const rg = L.studyGroups(az.syllabus, real);
  const total = rg.objectives.reduce((t, o) => t + o.count, 0);
  check(`讀書分組（真題庫）：${real.length} 題全部歸進大綱、沒有對不到的`, total === real.length && rg.other.length === 0, `歸進 ${total}、對不到 ${rg.other.length}`);
  check('讀書分組（真題庫）：每個節次題數＝配額、57 個細項都至少 1 題',
    rg.objectives.every((o, i) => o.count === az.syllabus.objectives[i].quota) && rg.objectives.flatMap(o => o.skills).every(k => k.questions.length > 0) &&
    rg.objectives.flatMap(o => o.skills).length === 57);
}

// 靜態檢查：app.js 只有 fill() 與 render() 兩處直接呼叫原生 replaceChildren（其他地方傳 null 會被印成 "null"）
const appSrc = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'js', 'app.js'), 'utf-8');
const rc = appSrc.split('\n').filter(l => /\.replaceChildren\(/.test(l) && !l.trim().startsWith('//'));
check('app.js 直接呼叫 replaceChildren 的只有 fill() 與 render() 兩處，而且都先經過 clean()',
  rc.length === 2 && rc.every(l => l.includes('...clean(nodes)')), rc.join(' ｜ '));

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

// 持久保存：三種狀態分開；只有嚴格的 true 才算受保護
{
  const fake = (persisted, persist) => ({ persisted: async () => { if (persisted instanceof Error) throw persisted; return persisted; },
    persist: async () => { fake.calls++; return persist; } });
  fake.calls = 0;
  const cases = [
    ['沒有 navigator.storage', undefined, 'unsupported'],
    ['有 storage 但沒有 persist()', { persisted: async () => false }, 'unsupported'],
    ['已經是持久保存（不必再要求）', fake(true, false), 'protected'],
    ['這次要求被答應', fake(false, true), 'protected'],
    ['要求被拒絕（false）', fake(false, false), 'denied'],
    ['回傳不是 true（undefined）→ 當成被拒絕，不往好的方向猜', fake(false, undefined), 'denied'],
    ['回傳字串 "true" → 也不算', fake(false, 'true'), 'denied'],
    ['查詢時出錯 → 狀態不明', fake(new Error('boom'), true), 'unsupported'],
  ];
  for (const [desc, storage, want] of cases) {
    const r = await L.requestPersistence(storage);
    check(`持久保存：${desc} → ${want}`, r.state === want, JSON.stringify(r));
  }
  fake.calls = 0;
  const already = fake(true, true);
  await L.requestPersistence(already);
  check('持久保存：已經受保護時不再呼叫 persist()', fake.calls === 0, `呼叫了 ${fake.calls} 次`);
}

console.log(fails ? `TEST-LOGIC FAILED：${fails} 項不符` : 'TEST-LOGIC OK：全部符合');
process.exit(fails ? 1 : 0);
