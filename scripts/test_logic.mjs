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
// 錯題要隔一段時間再答對才移出（U5）：答錯→馬上到期；複習模式答對一次→隔 MISTAKE_INTERVAL_DAYS 天到期；到期後再答對→移出
const D = 86400000;
const m0 = L.nextMistakeState(null, false, 'practice', 1000);
check('答錯 → 進錯題本、馬上到期', m0?.due === 1000 && m0.streak === 0);
const m1 = L.nextMistakeState({ wrongCount: 1, streak: 0, due: 3 }, true, 'mistakes', 3);
check(`錯題模式答對 1 次 → 還在、${L.MISTAKE_INTERVAL_DAYS} 天後到期`, m1?.streak === 1 && m1.due === 3 + L.MISTAKE_INTERVAL_DAYS * D);
check('還沒到期就再答對 → 不算進度（狀態不變）', L.nextMistakeState(m1, true, 'mistakes', 4) === m1);
check(`到期後再答對 → 移出（共 ${L.MISTAKE_CLEAR_STREAK} 次）`, L.nextMistakeState(m1, true, 'mistakes', m1.due) === null);
check('弱點複習模式也算複習：到期後答對 → 移出', L.nextMistakeState(m1, true, 'weak', m1.due + 1) === null);
check('模擬考答對 → 不移出、不算進度', L.nextMistakeState(m1, true, 'exam', m1.due + 1) === m1);
check('錯題模式答對後又答錯 → 連續次數歸零、馬上到期', (x => x?.streak === 0 && x.due === 5)(L.nextMistakeState(m1, false, 'mistakes', 5)));
check('舊紀錄沒有到期時間 → 當作已到期', L.mistakeDue({ wrongCount: 1, streak: 1 }) === 0 && L.nextMistakeState({ wrongCount: 1, streak: 1 }, true, 'mistakes', 9) === null);

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

// 分版題庫（金融市場常識與職業道德）：考試範圍、去重、模擬考配額、出處標示
{
  const mk = (id, subject, extra = {}) => ({ id, cert: 'ethics', subject, type: 'single', stem: `題幹 ${id}`, options: ['甲', '乙', '丙', '丁'],
    answer: 1, source: 'sfi-official', version: '116', qno: 1, ...extra });
  const pool = [
    mk('ethics-116-gen-001', 'gen'), mk('ethics-116-gen-002', 'gen', { change: 'added' }), mk('ethics-116-eth-001', 'eth', { change: 'modified' }),
    mk('ethics-113-gen-001', 'gen', { version: '113', dupOf: 'ethics-116-gen-001' }),
    mk('ethics-113-gen-009', 'gen', { version: '113', scope: 'outside', change: 'deleted' }),
    mk('ethics-113-eth-007', 'eth', { version: '113', scope: 'outside', change: 'modified', newId: 'ethics-116-eth-001' }),
  ];
  const base = { format: 'certquiz-import', version: 1, cert: 'ethics' };
  check('分版題庫：合法的匯入包通過', L.validateImportPack({ ...base, questions: pool }, ['ethics']).ok);
  const bad = (desc, mut, want) => {
    const qs = JSON.parse(JSON.stringify(pool)); mut(qs);
    const r = L.validateImportPack({ ...base, questions: qs }, ['ethics']);
    check(`分版題庫：${desc} → 擋`, !r.ok && r.errors.some(e => e.includes(want)), r.errors.join('；'));
  };
  bad('範圍寫成 outside 以外的值', qs => { qs[0].scope = 'old'; }, '範圍只能是 outside');
  bad('不在範圍內卻沒寫是改過或刪除', qs => { delete qs[4].change; }, '要寫明是改過或刪除');
  bad('差異類別不認得', qs => { qs[1].change = 'moved'; }, '差異類別不認得');
  bad('newId 指到不存在的題', qs => { qs[5].newId = 'ethics-116-eth-999'; }, 'newId 指到不存在的題');
  bad('newId 指到範圍外的題', qs => { qs[5].newId = 'ethics-113-gen-009'; }, 'newId 指到的題本身不在考試範圍');
  const ids = list => list.map(x => x.id).sort().join();
  check('分版題庫：預設只出考試範圍內的題（不出範圍外、不出去重掉的 113 版）',
    ids(L.pickQuestions(pool, { count: 99, seed: 1 })) === 'ethics-116-eth-001,ethics-116-gen-001,ethics-116-gen-002');
  check('分版題庫：指定範圍外，只出範圍外的題（兩種不混在一起）',
    ids(L.pickQuestions(pool, { count: 99, seed: 1, scope: 'outside' })) === 'ethics-113-eth-007,ethics-113-gen-009');
  const ex = L.buildExam(pool, 'all', 3, 1, { gen: 2, eth: 1 });
  check('分版題庫：模擬考照配額（常識 2＋道德 1），只出範圍內、照配額順序排',
    ex.ok && ex.questions.length === 3 && ex.questions.slice(0, 2).every(x => x.subject === 'gen') && ex.questions[2].subject === 'eth' && ex.questions.every(L.inScope));
  check('分版題庫：某科題數不夠配額 → 不出卷', !L.buildExam(pool, 'all', 4, 1, { gen: 3, eth: 1 }).ok);
  check('分版題庫：配額加總不等於題數 → 不出卷', !L.buildExam(pool, 'all', 5, 1, { gen: 2, eth: 1 }).ok);
  const lab = id => L.sourceLabel(pool.find(x => x.id === id));
  check('出處：116 年版新增', lab('ethics-116-gen-002') === '證基會公告題庫 116 年版・第 1 題・116 年版新增', lab('ethics-116-gen-002'));
  check('出處：範圍外（已刪除）寫明不在 116 年考試範圍', lab('ethics-113-gen-009') === '證基會公告題庫 113 年版・第 1 題・不在 116 年考試範圍內（116 年版已刪除這題）', lab('ethics-113-gen-009'));
  check('出處：範圍外（改過）寫明不在 116 年考試範圍', lab('ethics-113-eth-007') === '證基會公告題庫 113 年版・第 1 題・不在 116 年考試範圍內（116 年版已改過這題）', lab('ethics-113-eth-007'));
  // 正解換了的題：兩邊的出處都要寫明
  const chg = [mk('ethics-116-eth-214', 'eth', { change: 'modified', answer: 4, prevAnswer: { version: '113', qno: 214, answer: 1, text: '舊正解' } }),
    mk('ethics-113-eth-214', 'eth', { version: '113', scope: 'outside', change: 'modified', newId: 'ethics-116-eth-214', answerChanged: true })];
  check('分版題庫：正解換了的題，格式合法 → 通過', L.validateImportPack({ ...base, questions: chg }, ['ethics']).ok);
  check('分版題庫：prevAnswer 缺舊正解文字 → 擋', !L.validateImportPack({ ...base, questions: [{ ...chg[0], prevAnswer: { answer: 1 } }, chg[1]] }, ['ethics']).ok);
  check('出處：116 年版改過而且正解換了', L.sourceLabel(chg[0]) === '證基會公告題庫 116 年版・第 1 題・116 年版改過（正解跟 113 年版不同）', L.sourceLabel(chg[0]));
  check('出處：113 年版範圍外而且正解換了', L.sourceLabel(chg[1]) === '證基會公告題庫 113 年版・第 1 題・不在 116 年考試範圍內（116 年版已改過這題，而且正解換了）', L.sourceLabel(chg[1]));
  const realEthics = join(dirname(fileURLToPath(import.meta.url)), '..', 'data', 'local', 'import', 'ethics-匯入包.json');
  if (existsSync(realEthics)) {
    const r = L.validateImportPack(JSON.parse(readFileSync(realEthics, 'utf-8')), ['bic', 'az900', 'ethics']);
    const inS = r.questions.filter(x => L.isActive(x) && L.inScope(x));
    const out = r.questions.filter(x => L.isActive(x) && !L.inScope(x));
    const e = L.buildExam(r.questions, 'all', 100, 7, { gen: 50, eth: 50 });
    check(`真的金融常識與道德匯入包：通過檢查；考試範圍內 ${inS.length} 題全是 116 年版、範圍外 ${out.length} 題全是 113 年版；模擬考 100 題＝常識 50＋道德 50、全在範圍內`,
      r.ok && inS.length === 1174 && inS.every(x => x.version === '116') && out.length === 128 && out.every(x => x.version === '113')
      && e.ok && e.questions.filter(x => x.subject === 'gen').length === 50 && e.questions.every(x => L.inScope(x) && x.version === '116'), r.errors.slice(0, 3).join('；'));
    const pc = r.questions.filter(x => x.prevAnswer);
    check(`真的金融常識與道德匯入包：正解換了的題 ${pc.length} 題（應為 1 題：職業道德 116 年版第 214 題，113 年版正解 (1)、116 年版 (4)）`,
      pc.length === 1 && pc[0].id === 'ethics-116-eth-214' && pc[0].prevAnswer.answer === 1 && pc[0].answer === 4
      && r.questions.filter(x => x.answerChanged).map(x => x.id).join() === 'ethics-113-eth-214', JSON.stringify(pc.map(x => [x.id, x.prevAnswer])));
  }
}

// 法規修正標示（N1）：格式檢查兩個方向；統計從題目數出來、四類相加＝總數；「整批依舊版」只認全部都修正過、題數夠的法規
{
  const lw = (status, laws) => ({ status, checked: '2026-10-08', laws });
  const A = { name: '甲辦法', known: true, after: ['2026-05-06'], pending: '第 1 條施行日期由主管機關定' };
  const B = { name: '乙法', known: true, after: [] };
  const C = { name: '丙法', known: false, after: [] };
  const qs = [
    ...Array.from({ length: 10 }, (_, i) => q(`bic-law-t47-${String(i + 1).padStart(3, '0')}`, { law: lw('amended', [A]) })),
    q('bic-law-t47-011', { law: lw('amended', [B, { ...A, name: '丁法', pending: undefined }]) }),
    q('bic-law-t47-012', { law: lw('unchanged', [B]) }),
    q('bic-law-t47-013', { law: lw('partial', [B, C]) }),
    q('bic-law-t47-014', { law: lw('none', []) }),
    q('bic-law-t47-015', { law: lw('none', [C]) }),
    q('bic-law-t47-016', { law: lw('amended', [A]), dupOf: 'bic-law-t47-001' }),
  ].map(x => { if (x.law) x.law.laws = x.law.laws.map(e => Object.fromEntries(Object.entries(e).filter(([, v]) => v !== undefined))); return x; });
  check('法規標示：合格的通過', L.validateImportPack(pack(qs), ['bic']).ok, L.validateImportPack(pack(qs), ['bic']).errors.join('；'));
  const bad = [
    ['狀態不認得', { ...qs[11], law: lw('maybe', [B]) }],
    ['說修正過卻沒有任何修正日期', { ...qs[11], law: lw('amended', [B]) }],
    ['有修正日期卻說沒修正', { ...qs[11], law: lw('unchanged', [A]) }],
    ['日期格式不對', { ...qs[11], law: lw('amended', [{ ...A, after: ['115.05.06'] }]) }],
    ['缺查詢日', { ...qs[11], law: { status: 'none', laws: [] } }],
  ];
  for (const [d, x] of bad) check(`法規標示：${d} → 擋`, !L.validateImportPack(pack([x]), ['bic']).ok);
  const s = L.lawSummary(qs);
  check(`法規統計：重複題不算；四類 ${s.amended}＋${s.unchanged}＋${s.partial}＋${s.none}＝${s.total}（應 11＋1＋1＋2＝15）；有版本資料 ${s.hasData}（應 13）`,
    s.total === 15 && s.amended === 11 && s.unchanged === 1 && s.partial === 1 && s.none === 2 && s.hasData === 13 && s.checked === '2026-10-08');
  check(`法規統計：整批依舊版只有甲辦法（10 題全修正過）；丁法只有 1 題、乙法沒全修正，都不算：${s.batches.map(b => b.name)}`,
    s.batches.length === 1 && s.batches[0].name === '甲辦法' && s.batches[0].total === 10 && s.batches[0].latest === '2026-05-06' && !!s.batches[0].pending);
  check('法規統計：題數門檻改成 11 就沒有整批', L.lawSummary(qs, 11).batches.length === 0);
  check('法規統計：沒有 law 欄位的題庫 → 總數 0', L.lawSummary([q('bic-law-t47-001')]).total === 0);
  const realBic = join(ROOT, 'data', 'local', 'import', 'bic-匯入包.json');
  const flagsF = join(ROOT, 'data', 'local', 'law', 'flags.json');
  if (existsSync(realBic) && existsSync(flagsF)) {
    const r = L.validateImportPack(JSON.parse(readFileSync(realBic, 'utf-8')), ['bic']);
    const f = JSON.parse(readFileSync(flagsF, 'utf-8'));
    const rs = L.lawSummary(r.questions);
    const active = r.questions.filter(L.isActive).length;
    check(`真的內控匯入包：法規統計四類 ${rs.amended}＋${rs.unchanged}＋${rs.partial}＋${rs.none}＝${rs.total}＝可練 ${active} 題，而且跟 law_flags.py 的計數一致`,
      r.ok && rs.total === active && rs.amended + rs.unchanged + rs.partial + rs.none === active
      && rs.amended === f.counts.amended && rs.none === f.counts.none, JSON.stringify(f.counts));
    const ic = rs.batches.find(b => b.name === '金融控股公司及銀行業內部控制及稽核制度實施辦法');
    check(`真的內控匯入包：內控辦法列為整批依舊版（${ic && ic.total} 題、最後修正 ${ic && ic.latest}、有尚未施行的條文）`,
      !!ic && ic.total === ic.amended && !!ic.pending, JSON.stringify(rs.batches.map(b => [b.name, b.total, b.amended])));
  }
}

// 備份與還原（U4）：來回一趟內容不變；壞檔整份不收、點名；只收認得的 meta（考點清單跟著匯入包走，不進備份）
{
  const rec = {
    attempts: [{ n: 1, cert: 'bic', qid: 'bic-law-t47-001', chosen: 2, correct: true, mode: 'practice', ts: 1000, studied: false },
      { n: 2, cert: 'ethics', qid: 'ethics-116-gen-001', chosen: 4, correct: false, mode: 'exam', ts: 3000 }],
    progress: [{ qid: 'bic-law-t47-001', cert: 'bic', seen: 1, correct: 1, last: true, ts: 1000 }],
    mistakes: [{ qid: 'ethics-116-gen-001', cert: 'ethics', streak: 0, ts: 3000 }],
    meta: { studied: { 'bic:point:P001': 1 }, examHistory: [{ cert: 'bic', score: 70 }], 'points:bic': [{ id: 'P001' }] },
  };
  const b = L.makeBackup(rec, Date.UTC(2026, 9, 12), 'CertQuiz');
  const back = L.validateBackup(JSON.parse(JSON.stringify(b)));
  check('備份：來回一趟（轉成文字再讀回來）通過檢查、三類紀錄與讀書／模擬考紀錄一字不差',
    back.ok && JSON.stringify(back.data.attempts) === JSON.stringify(rec.attempts) && JSON.stringify(back.data.progress) === JSON.stringify(rec.progress)
    && JSON.stringify(back.data.mistakes) === JSON.stringify(rec.mistakes) && JSON.stringify(back.data.meta) === JSON.stringify({ studied: rec.meta.studied, examHistory: rec.meta.examHistory }),
    back.errors.join('；'));
  check('備份：考點清單（points:*）不進備份——它跟著匯入包走', !('points:bic' in b.meta));
  const s = L.backupSummary(rec);
  check(`備份摘要：作答 ${s.attempts}、各證照 ${JSON.stringify(s.certs)}、最新一筆 ${s.lastTs}`, s.attempts === 2 && s.certs.bic === 1 && s.certs.ethics === 1 && s.lastTs === 3000);
  const bad = [
    ['拿題目匯入包來還原', { format: 'certquiz-import', version: 1 }, '匯入包，不是備份檔'],
    ['版本不對', { ...b, version: 2 }, '版本'],
    ['檔案被截斷（筆數對不上）', { ...b, attempts: b.attempts.slice(0, 1) }, '筆數對不上'],
    ['作答紀錄的選項不是 1～4', { ...b, attempts: [{ ...b.attempts[0], chosen: 7 }, b.attempts[1]] }, '作答紀錄第 1 筆'],
    ['作答紀錄缺題號', { ...b, attempts: [{ ...b.attempts[0], qid: '' }, b.attempts[1]] }, '作答紀錄第 1 筆'],
    ['作答編號重複', { ...b, attempts: [b.attempts[0], { ...b.attempts[1], n: 1 }] }, '編號重複'],
    ['錯題本同一題出現兩次', { ...b, counts: { ...b.counts, mistakes: 2 }, mistakes: [b.mistakes[0], b.mistakes[0]] }, '重複'],
    ['答對次數比作答次數多', { ...b, progress: [{ ...b.progress[0], correct: 5 }] }, '作答次數'],
    ['meta 有不認得的項目', { ...b, meta: { ...b.meta, 'points:bic': [] } }, '不認得的項目'],
    ['不是物件', [], '不是 JSON 物件'],
  ];
  for (const [d, x, why] of bad) {
    const r = L.validateBackup(JSON.parse(JSON.stringify(x)));
    check(`備份：${d} → 整份不收、訊息點名「${why}」`, !r.ok && !r.data && r.errors.some(e => e.includes(why)), r.errors.join('；'));
  }
}

// 弱點複習（U5）：到期錯題先出；最弱範圍要作答夠多、而且低於整體才算；範圍內先出上次答錯的；不夠就補沒做過的，照實分開計
{
  const mk = (id, subject) => q(id, { subject });
  const pool = [...Array.from({ length: 30 }, (_, i) => mk(`bic-law-t47-${String(i + 1).padStart(3, '0')}`, 'law')),
    ...Array.from({ length: 30 }, (_, i) => mk(`bic-gen-t47-${String(i + 1).padStart(3, '0')}`, 'gen'))];
  const at = (qid, correct) => ({ cert: 'bic', qid, correct, chosen: 1, mode: 'practice', ts: 1 });
  // 法規 12 次答對 3 次（25%）、實務 12 次答對 11 次（92%）；整體 58%
  const attempts = [...Array.from({ length: 12 }, (_, i) => at(`bic-law-t47-${String(i + 1).padStart(3, '0')}`, i < 3)),
    ...Array.from({ length: 12 }, (_, i) => at(`bic-gen-t47-${String(i + 1).padStart(3, '0')}`, i < 11))];
  const progress = new Map(attempts.map(a => [a.qid, { qid: a.qid, seen: 1, correct: a.correct ? 1 : 0, last: a.correct }]));
  const now = 10 * D;
  const mistakes = [{ qid: 'bic-gen-t47-012', cert: 'bic', streak: 0, due: now - 1 }, { qid: 'bic-law-t47-004', cert: 'bic', streak: 1, due: now + D }];
  const p = L.weakPlan(pool, { attempts, progress, mistakes, count: 20, now, seed: 3 });
  const ids = p.items.map(x => x.id);
  check(`弱點複習：到期的錯題 1 題排第一（還沒到期的不出）`, p.parts.due === 1 && ids[0] === 'bic-gen-t47-012' && p.dueTotal === 1);
  check(`弱點複習：最弱範圍是法規（${p.group && p.group.key}、${p.group && Math.round(p.group.rate * 100)}%，整體 ${Math.round(p.overall * 100)}%）`, p.group?.key === 'law' && p.group.answered === 12);
  const weak = p.items.slice(1, 1 + p.parts.weak);
  check(`弱點複習：範圍內先出上次答錯的 9 題，再出沒做過的；共 ${p.parts.weak} 題、全是法規、沒有重複`,
    p.parts.weak === 19 && weak.every(x => x.subject === 'law') && weak.slice(0, 9).every(x => progress.get(x.id)?.last === false) && new Set(ids).size === ids.length);
  const thin = L.weakPlan(pool, { attempts: attempts.slice(0, 9).concat(attempts.slice(12, 21)), progress, mistakes: [], count: 5, now, seed: 3 });
  check(`弱點複習：每個範圍作答不到 ${L.WEAK_MIN_ATTEMPTS} 次 → 不指認弱點，只補沒做過的題（照實計成「補的」）`, thin.group === null && thin.parts.fill === 5 && thin.parts.weak === 0);
  const even = L.weakPlan(pool, { attempts: attempts.map(a => ({ ...a, correct: true })), progress, mistakes: [], count: 5, now, seed: 3 });
  check('弱點複習：各範圍答對率都不低於整體 → 不指認弱點', even.group === null);
}

// 「答案有疑問」標記（U6）：標／取消來回、不改原本的物件；清單只列這張證照、新的在前；不在題庫的題另外列；跟著備份走、壞格式擋
{
  const a = q('bic-law-t47-001'), b = q('bic-law-t47-002');
  const d0 = {};
  const d1 = L.toggleDoubt(d0, a, 100);
  const d2 = L.toggleDoubt(d1, b, 200);
  check('標記：標了兩題、原本的物件沒被改', Object.keys(d2).length === 2 && Object.keys(d0).length === 0 && Object.keys(d1).length === 1);
  check('標記：再按一次取消', !L.toggleDoubt(d2, a, 300)['bic-law-t47-001'] && Object.keys(L.toggleDoubt(d2, a, 300)).length === 1);
  const other = { ...d2, 'ethics-116-gen-001': { cert: 'ethics', ts: 999 }, 'bic-law-t99-001': { cert: 'bic', ts: 50 } };
  const lst = L.doubtList(other, [a, b], 'bic');
  check('標記清單：只列這張證照、新標的在前；題庫裡找不到的另外列題號',
    lst.items.map(x => x.q.id).join() === 'bic-law-t47-002,bic-law-t47-001' && lst.missing.join() === 'bic-law-t99-001');
  const bk = L.makeBackup({ attempts: [], progress: [], mistakes: [], meta: { doubts: other } }, 0, 'x');
  const back = L.validateBackup(JSON.parse(JSON.stringify(bk)));
  check('標記跟著備份走：來回一趟一字不差', back.ok && JSON.stringify(back.data.meta.doubts) === JSON.stringify(other), back.errors.join('；'));
  check('備份裡的標記格式不對（缺證照）→ 整份不收', !L.validateBackup({ ...JSON.parse(JSON.stringify(bk)), meta: { doubts: { x: { ts: 1 } } } }).ok);
}

// 教材（2026-10-13）：題號都要在包內；有說明的要有法規、條號、原文、快照、那一句；沒說明的要寫留白原因
{
  const qs = [q('bic-law-t47-001'), q('bic-law-t47-002'), q('bic-law-t47-003')];
  const ex = { law: '甲辦法', article: '第1條', version: '20211013', text: '條文原文', snapshot: 'data/local/law/text/x.txt', url: 'u', link: '所以是 (2)。', summary: '第1條：重點，所以是 (2)。' };
  const tb = items => ({ version: 1, status: 'draft', chapters: [{ id: 'T08', name: '信用卡', count: 3, explained: 1, items }, { id: 'T01', name: '其他章', count: 9 }] });
  const good = tb([{ id: 'bic-law-t47-001', explain: ex, variants: [{ id: 'bic-law-t47-002', blank: '題目沒有點名法規' }] }, { id: 'bic-law-t47-003', blank: '題目沒有點名法規' }]);
  const r = L.validateImportPack(pack(qs, { textbook: good }), ['bic']);
  check('教材：合格的通過、匯入結果帶著教材', r.ok && r.textbook && r.textbook.chapters.length === 2, r.errors.join('；'));
  const bad = [
    ['題號不在包內', tb([{ id: 'bic-law-t99-001', blank: 'x' }]), '不在包內'],
    ['沒有說明也沒寫留白原因', tb([{ id: 'bic-law-t47-001' }]), '留白原因'],
    ['說明缺原文', tb([{ id: 'bic-law-t47-001', explain: { ...ex, text: '' } }]), '說明缺欄位'],
    ['其他問法的題號不在包內', tb([{ id: 'bic-law-t47-001', blank: 'x', variants: [{ id: 'bic-law-t99-002', blank: 'x' }] }]), '不在包內'],
  ];
  for (const [d, t, why] of bad) {
    const rr = L.validateImportPack(pack(qs, { textbook: t }), ['bic']);
    check(`教材：${d} → 整包不收、點名「${why}」`, !rr.ok && rr.errors.some(e => e.includes(why)), rr.errors.join('；'));
  }
  check('教材：沒有教材的匯入包 → textbook 是 null', L.validateImportPack(pack(qs), ['bic']).textbook === null);
  const mixed = tb([{ id: 'bic-law-t47-001', explain: ex, variants: [{ id: 'bic-law-t47-002', ours: { text: '我們的理解', unknown: false } }] }, { id: 'bic-law-t47-003', ours: { text: '要記的數字', unknown: true } }]);
  check('教材（乙＋丙）：法規原文＋我們寫的（含看不出）通過', L.validateImportPack(pack(qs, { textbook: mixed }), ['bic']).ok);
  check('教材（乙＋丙）：我們寫的缺「看不出」旗標 → 擋', !L.validateImportPack(pack(qs, { textbook: tb([{ id: 'bic-law-t47-001', ours: { text: 'x' } }]) }), ['bic']).ok);
  check('教材（乙＋丙）：我們寫的內容是空的 → 擋', !L.validateImportPack(pack(qs, { textbook: tb([{ id: 'bic-law-t47-001', ours: { text: '', unknown: true } }]) }), ['bic']).ok);
}

console.log(fails ? `TEST-LOGIC FAILED：${fails} 項不符` : 'TEST-LOGIC OK：全部符合');
process.exit(fails ? 1 : 0);
