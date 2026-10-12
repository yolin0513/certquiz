// 純邏輯（不碰 DOM、不碰 IndexedDB），可以直接用 node 測：scripts/test_logic.mjs

export const IMPORT_FORMAT = 'certquiz-import';
export const IMPORT_VERSION = 1;
export const MISTAKE_CLEAR_STREAK = 2;   // 錯題在錯題模式連續答對幾次才移出

const ID_RE = /^[a-z0-9]+(?:-[a-z0-9]+)+$/;
const SOURCES = new Set(['tabf-official', 'user-import', 'sfi-official', 'original-ai', 'original-human']);
const CHANGES = new Set(['added', 'modified', 'deleted']);   // 兩版題庫的差異（金融市場常識與職業道德，docs/L）

/**
 * 驗證匯入包。回傳 { ok, errors[], cert, questions[] }。
 * 任何一題不合格就整包不收（不做部分匯入：部分匯入會讓使用者以為題庫是完整的）。
 */
export function validateImportPack(obj, knownCerts) {
  const errors = [];
  if (!obj || typeof obj !== 'object') return { ok: false, errors: ['檔案不是 JSON 物件'], questions: [] };
  if (obj.format !== IMPORT_FORMAT) errors.push(`不是本 App 的匯入包（format 應為 ${IMPORT_FORMAT}）`);
  if (obj.version !== IMPORT_VERSION) errors.push(obj.version === undefined ? `匯入包沒有標示版本（應為 ${IMPORT_VERSION}）` : `匯入包版本 ${obj.version} 不支援（只支援 ${IMPORT_VERSION}）`);
  if (!knownCerts.includes(obj.cert)) errors.push(obj.cert === undefined ? '匯入包沒有標示證照' : `不認得的證照：${obj.cert}`);
  const qs = Array.isArray(obj.questions) ? obj.questions : [];
  if (!qs.length) errors.push('匯入包裡沒有題目');
  const ids = new Set();
  qs.forEach((q, i) => {
    const tag = q && q.id ? `第 ${i + 1} 題（${q.id}）` : `第 ${i + 1} 題`;
    if (!q || typeof q !== 'object') { errors.push(`${tag}：格式不對`); return; }
    if (!ID_RE.test(q.id || '')) errors.push(`${tag}：id 格式不對`);
    if (ids.has(q.id)) errors.push(`${tag}：id 重複`);
    ids.add(q.id);
    if (q.cert !== obj.cert) errors.push(`${tag}：證照跟匯入包不一致`);
    if (q.type !== 'single') errors.push(`${tag}：只支援單選題`);
    if (typeof q.stem !== 'string' || !q.stem) errors.push(`${tag}：題幹是空的`);
    if (!Array.isArray(q.options) || q.options.length !== 4 || q.options.some(o => typeof o !== 'string' || !o))
      errors.push(`${tag}：選項必須剛好四個、不得空白`);
    if (![1, 2, 3, 4].includes(q.answer)) errors.push(`${tag}：答案必須是 1～4`);
    if (!SOURCES.has(q.source)) errors.push(q.source === undefined ? `${tag}：沒有來源欄位` : `${tag}：來源欄位不認得（${q.source}）`);
    if (q.dupOf !== undefined && typeof q.dupOf !== 'string') errors.push(`${tag}：dupOf 格式不對`);
    // 版本與考試範圍（只有分版的題庫有）：scope 只能是 outside（不在目前考試範圍內）；change 只能是新增／改過／刪除
    if (q.version !== undefined && !/^\d{3}$/.test(String(q.version))) errors.push(`${tag}：版本格式不對`);
    if (q.scope !== undefined && q.scope !== 'outside') errors.push(`${tag}：範圍只能是 outside 或不寫`);
    if (q.change !== undefined && !CHANGES.has(q.change)) errors.push(`${tag}：差異類別不認得（${q.change}）`);
    if (q.scope === 'outside' && !['modified', 'deleted'].includes(q.change)) errors.push(`${tag}：不在考試範圍的題要寫明是改過或刪除`);
    if (q.newId !== undefined && typeof q.newId !== 'string') errors.push(`${tag}：newId 格式不對`);
    if (q.answerChanged !== undefined && q.answerChanged !== true) errors.push(`${tag}：answerChanged 只能是 true 或不寫`);
    if (q.prevAnswer !== undefined && !(q.prevAnswer && [1, 2, 3, 4].includes(q.prevAnswer.answer) && typeof q.prevAnswer.text === 'string' && q.prevAnswer.text))
      errors.push(`${tag}：prevAnswer 格式不對（要有舊版正解 1～4 與文字）`);
    if (q.law !== undefined && !validLaw(q.law)) errors.push(`${tag}：法規修正標示（law）格式不對`);
  });
  // dupOf 必須指到包內存在、而且本身不是重複的題；newId（舊版改過的題指到新版那題）也必須在包內、而且在考試範圍內
  const byId = new Map(qs.map(q => [q && q.id, q]));
  qs.forEach(q => {
    if (q && q.newId) {
      const t = byId.get(q.newId);
      if (!t) errors.push(`${q.id}：newId 指到不存在的題 ${q.newId}`);
      else if (t.scope === 'outside') errors.push(`${q.id}：newId 指到的題本身不在考試範圍`);
    }
  });
  qs.forEach(q => {
    if (q && q.dupOf) {
      const t = byId.get(q.dupOf);
      if (!t) errors.push(`${q.id}：dupOf 指到不存在的題 ${q.dupOf}`);
      else if (t.dupOf) errors.push(`${q.id}：dupOf 指到的題本身也是重複題`);
    }
  });
  // 考點清單（只有本機匯入包有）：可省略；有的話每個考點至少兩期、兩題，題號都要在包內，題目標的考點要對得上
  let points = [];
  if (obj.points !== undefined) {
    if (!Array.isArray(obj.points)) errors.push('考點清單格式不對');
    else {
      const codes = new Set();
      obj.points.forEach((p, i) => {
        const tag = p && p.id ? `考點 ${p.id}` : `第 ${i + 1} 個考點`;
        if (!p || typeof p !== 'object' || !/^P\d{3}$/.test(p.id || '')) { errors.push(`${tag}：代號格式不對`); return; }
        if (codes.has(p.id)) errors.push(`${tag}：代號重複`);
        codes.add(p.id);
        if (!Array.isArray(p.ids) || p.ids.length < 2 || p.ids.some(x => !byId.has(x))) errors.push(`${tag}：題號清單不對（至少兩題、都要在包內）`);
        if (p.kind !== undefined && p.kind !== 'list') errors.push(`${tag}：類別只能是 list（教材清單）或不寫（同一條規定）`);
        if (!Array.isArray(p.periods) || p.periods.length < 2) errors.push(`${tag}：期別至少要兩期`);
        else (p.ids || []).forEach(x => { const q = byId.get(x); if (q && q.point !== p.id) errors.push(`${tag}：題目 ${x} 標的考點不是 ${p.id}`); });
      });
      qs.forEach(q => { if (q && q.point && !codes.has(q.point)) errors.push(`${q.id}：標的考點 ${q.point} 不在考點清單裡`); });
      points = obj.points;
    }
  }
  return { ok: errors.length === 0, errors, cert: obj.cert, questions: errors.length ? [] : qs, points: errors.length ? [] : points };
}

// ---------------------------------------------------------------- 法規修正標示（N1，Dispatch 2026-10-12）
// 每題的 law：{ status, checked, laws: [{ name, known, after: [YYYY-MM-DD…], pending? }] }（scripts/law_flags.py）。
// 數字一律從題目數出來，不寫死：法規資料更新、重新匯入後就跟著變。
export const LAW_STATUSES = ['amended', 'unchanged', 'partial', 'none'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function validLaw(x) {
  return !!x && typeof x === 'object' && LAW_STATUSES.includes(x.status) && DATE_RE.test(x.checked || '') && Array.isArray(x.laws)
    && x.laws.every(e => e && typeof e.name === 'string' && e.name && typeof e.known === 'boolean' && Array.isArray(e.after)
      && e.after.every(d => DATE_RE.test(d)) && (e.pending === undefined || (typeof e.pending === 'string' && e.pending)))
    && (x.status === 'amended') === x.laws.some(e => e.after.length > 0);
}

/**
 * 法規修正的統計：{ total, amended, unchanged, partial, none, hasData, checked, batches[] }。
 * total 只算有 law 欄位的可練題；四類相加＝total。
 * batches：「整批依舊版」的法規——題庫裡點名它的題，全部都在考試後修正過，而且至少 minBatch 題（一部常考的法規整批過時，跟零星幾題不同）。
 */
export function lawSummary(questions, minBatch = 10) {
  const qs = questions.filter(q => isActive(q) && q.law);
  const n = Object.fromEntries(LAW_STATUSES.map(s => [s, qs.filter(q => q.law.status === s).length]));
  const by = new Map();
  for (const q of qs) for (const e of q.law.laws) {
    const r = by.get(e.name) || { name: e.name, total: 0, amended: 0, latest: '', pending: null };
    r.total += 1;
    if (e.after.length) { r.amended += 1; r.latest = [r.latest, ...e.after].sort().pop(); }
    if (e.pending) r.pending = e.pending;
    by.set(e.name, r);
  }
  const batches = [...by.values()].filter(r => r.total >= minBatch && r.amended === r.total).sort((a, b) => b.total - a.total);
  return { total: qs.length, ...n, hasData: n.amended + n.unchanged + n.partial, checked: qs[0] ? qs[0].law.checked : null, batches };
}

/** 這題點名的法規裡，屬於「整批依舊版」的那一部（沒有就 null）。 */
export function lawBatchOf(q, batches) {
  if (!q.law) return null;
  return batches.find(b => q.law.laws.some(e => e.name === b.name)) || null;
}

/** 練習時可出的題：不是重複題、沒有標 retired */
/** 在不在目前的考試範圍（分版題庫裡，舊版已刪除或改過的題標 scope: 'outside'；其他題庫沒有這個欄位＝都在範圍內）。 */
export function inScope(q) {
  return q.scope !== 'outside';
}

export function isActive(q) {
  return !q.dupOf && q.status !== 'retired';
}

/** 可重現的亂數（mulberry32），測試時給固定種子 */
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffle(arr, rand) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/**
 * 選題。opts：{ subject: 'law'|'gen'|'all', source: 'all'|'official'|'user', count, order: 'unseen'|'random', seed }
 * progress：Map(qid → { seen })。unseen＝沒做過的優先，其餘隨機補滿。
 */
export function pickQuestions(pool, opts, progress = new Map()) {
  const rand = rng(opts.seed ?? Date.now());
  let qs = pool.filter(isActive);
  // 考試範圍：預設只出範圍內的題；要練範圍外（舊版已刪除或改過）的題要明講 scope: 'outside'，兩種不混在一起出
  qs = opts.scope === 'outside' ? qs.filter(q => !inScope(q)) : qs.filter(inScope);
  if (opts.subject && opts.subject !== 'all') qs = qs.filter(q => q.subject === opts.subject);
  if (opts.source === 'official') qs = qs.filter(q => q.source === 'tabf-official');
  if (opts.source === 'user') qs = qs.filter(q => q.source === 'user-import');
  if (opts.objective) qs = qs.filter(q => q.objective === opts.objective);
  if (opts.ids) qs = qs.filter(q => opts.ids.has(q.id));
  if (opts.period) qs = qs.filter(q => String(q.period) === String(opts.period));
  if (opts.skill) qs = qs.filter(q => String(q.skill) === String(opts.skill));
  let ordered;
  if (opts.order === 'unseen') {
    const unseen = shuffle(qs.filter(q => !(progress.get(q.id)?.seen > 0)), rand);
    const seen = shuffle(qs.filter(q => progress.get(q.id)?.seen > 0), rand);
    ordered = unseen.concat(seen);
  } else {
    ordered = shuffle(qs, rand);
  }
  return ordered.slice(0, Math.max(0, opts.count | 0));
}

// ---------------------------------------------------------------- 錯題本與弱點複習（U5，2026-10-12）
// 錯題要「隔一段時間再答對」才移出：答錯→馬上到期；在複習模式答對一次→隔 MISTAKE_INTERVAL_DAYS 天再到期；
// 到期後再答對一次→移出（共 MISTAKE_CLEAR_STREAK 次）。還沒到期就先答對，不算進度（剛看過答案馬上答對，不代表記住了）。
export const MISTAKE_INTERVAL_DAYS = 2;
const DAY = 86400000;
const REVIEW_MODES = new Set(['mistakes', 'weak']);

/** 錯題什麼時候到期（舊紀錄沒有 due＝已到期）。 */
export function mistakeDue(m) {
  return typeof m.due === 'number' ? m.due : 0;
}

/** 作答後錯題本的新狀態。回傳 null 表示不在錯題本（或該移出）。 */
export function nextMistakeState(prev, correct, mode, now) {
  if (!correct) return { wrongCount: (prev?.wrongCount || 0) + 1, streak: 0, ts: now, due: now };
  if (!prev) return null;                       // 答對、本來就不在錯題本
  if (!REVIEW_MODES.has(mode)) return prev;     // 一般練習、模擬考答對不移出，避免猜對就消失
  if (mistakeDue(prev) > now) return prev;      // 還沒到期就答對：不算進度
  const streak = (prev.streak || 0) + 1;
  return streak >= MISTAKE_CLEAR_STREAK ? null : { ...prev, streak, ts: now, due: now + MISTAKE_INTERVAL_DAYS * DAY };
}

/**
 * 弱點複習要出哪些題（純函式，好測）。
 * 1. 先出到期的錯題。
 * 2. 再出「最弱的範圍」的題：範圍＝AZ-900 依官方大綱節次、其他依科目；作答 ≥ WEAK_MIN_ATTEMPTS 次才比較，
 *    而且答對率要低於整體答對率才算弱（不然就沒有「弱點」可言）。範圍內先出上次答錯的、再出沒做過的、再出其他。
 * 3. 還不夠就補沒做過的題，畫面上照實寫「補的」。
 * 回傳 { items, parts: { due, weak, fill }, group, overall, groups, dueTotal }。
 */
export const WEAK_MIN_ATTEMPTS = 10;
export function weakGroupKey(q) {
  return q.objective || q.subject;
}
export function weakPlan(pool, { attempts, progress, mistakes, count, now, seed }) {
  const rand = rng(seed ?? now);
  const qs = pool.filter(q => isActive(q) && inScope(q));
  const byId = new Map(qs.map(q => [q.id, q]));
  const dueAll = mistakes.filter(m => byId.has(m.qid) && mistakeDue(m) <= now);
  const due = shuffle(dueAll.map(m => byId.get(m.qid)), rand).slice(0, count);
  const used = new Set(due.map(q => q.id));
  const att = attempts.filter(a => byId.has(a.qid));
  const overall = att.length ? att.filter(a => a.correct).length / att.length : null;
  const groups = [...groupRate(att, byId, weakGroupKey)].map(([key, g]) => ({ key, ...g }))
    .filter(g => g.answered >= WEAK_MIN_ATTEMPTS).sort((a, b) => a.rate - b.rate || b.answered - a.answered);
  const weakest = overall !== null && groups.length && groups[0].rate < overall ? groups[0] : null;
  let weak = [];
  if (weakest && due.length < count) {
    const inG = qs.filter(q => weakGroupKey(q) === weakest.key && !used.has(q.id));
    const lastWrong = shuffle(inG.filter(q => progress.get(q.id)?.last === false), rand);
    const unseen = shuffle(inG.filter(q => !(progress.get(q.id)?.seen > 0)), rand);
    const rest = shuffle(inG.filter(q => progress.get(q.id)?.seen > 0 && progress.get(q.id)?.last !== false), rand);
    weak = lastWrong.concat(unseen, rest).slice(0, count - due.length);
    weak.forEach(q => used.add(q.id));
  }
  const fill = shuffle(qs.filter(q => !used.has(q.id) && !(progress.get(q.id)?.seen > 0)), rand).slice(0, count - due.length - weak.length);
  return { items: due.concat(weak, fill), parts: { due: due.length, weak: weak.length, fill: fill.length },
    group: weakest, overall, groups, dueTotal: dueAll.length };
}

/** 依答題記錄算統計：{ answered, correct, rate } */
export function summarize(attempts) {
  const answered = attempts.length;
  const correct = attempts.filter(a => a.correct).length;
  return { answered, correct, rate: answered ? correct / answered : 0 };
}

// ---------------------------------------------------------------- 模擬考
/**
 * 依正式題數出卷：只出可練的題、限定科目、隨機抽 count 題。
 * 題數不夠就不出（ok=false）——用不足的題數考，分數與及格判斷都沒有意義。
 */
export function buildExam(pool, subject, count, seed, mix) {
  const base = pool.filter(isActive).filter(inScope);   // 模擬考只出考試範圍內的題
  if (mix) {
    // 依科目配額（例：金融市場常識 50＋職業道德 50）；照配額順序排，同一科目內隨機
    const rand = rng(seed);
    const parts = Object.entries(mix).map(([sub, n]) => ({ sub, n, qs: base.filter(q => q.subject === sub) }));
    const short = parts.filter(p => p.qs.length < p.n);
    const available = parts.reduce((t, p) => t + p.qs.length, 0);
    if (short.length || Object.values(mix).reduce((a, b) => a + b, 0) !== count) return { ok: false, available, questions: [] };
    return { ok: true, available, questions: parts.flatMap(p => shuffle(p.qs, rand).slice(0, p.n)) };
  }
  const qs = base.filter(q => q.subject === subject);
  if (qs.length < count) return { ok: false, available: qs.length, questions: [] };
  return { ok: true, available: qs.length, questions: shuffle(qs, rng(seed)).slice(0, count) };
}

/**
 * 計分。answers：Map(qid → 選的 1～4)。exam：{ points, pass }（每題分數、及格分數）。
 * 分數四捨五入到小數兩位（實務 1.25 分 × 題數）；及格是「分數 ≥ 及格線」。未作答不給分、不倒扣。
 */
export function scoreExam(questions, answers, exam) {
  let correct = 0, unanswered = 0;
  for (const q of questions) {
    const a = answers.get(q.id);
    if (a === undefined) unanswered++;
    else if (a === q.answer) correct++;
  }
  const score = Math.round(correct * exam.points * 100) / 100;
  return { total: questions.length, correct, wrong: questions.length - correct - unanswered, unanswered,
    score, passed: score >= exam.pass };
}

export function remainingMs(deadline, now) {
  return Math.max(0, deadline - now);
}

/** 毫秒 → 「mm:ss」或「h:mm:ss」 */
export function formatClock(ms) {
  const s = Math.ceil(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const pad = n => String(n).padStart(2, '0');
  return h ? `${h}:${pad(m)}:${pad(r)}` : `${pad(m)}:${pad(r)}`;
}

// ---------------------------------------------------------------- 統計
/** 依科目或來源分組的答對率。attempts：[{qid, correct}]；byId：Map(qid → 題目)；keyOf：題目 → 分組鍵 */
export function groupRate(attempts, byId, keyOf) {
  const out = new Map();
  for (const a of attempts) {
    const q = byId.get(a.qid);
    if (!q) continue;
    const k = keyOf(q);
    const g = out.get(k) || { answered: 0, correct: 0 };
    g.answered++;
    if (a.correct) g.correct++;
    out.set(k, g);
  }
  for (const g of out.values()) g.rate = g.answered ? g.correct / g.answered : 0;
  return out;
}

/** 題目的出處說明（畫面顯示用） */
export function sourceLabel(q) {
  // 每一段都只在欄位存在時才出現；缺欄位就整段不顯示（不顯示「undefined」、空白或「無」）
  const where = [q.period ? `第 ${q.period} 期` : '', q.qno ? `第 ${q.qno} 題` : ''].join('');
  const law = q.law_as_of ? `（法規基準：${q.law_as_of}）` : '';
  const tail = where || law ? `・${where}${law}` : '';
  if (q.source === 'tabf-official') return `官方歷屆試題${tail}`;
  if (q.source === 'sfi-official') {
    const head = `證基會公告題庫${q.version ? ` ${q.version} 年版` : ''}${q.qno ? `・第 ${q.qno} 題` : ''}`;
    if (q.scope === 'outside') return `${head}・不在 116 年考試範圍內（${q.change === 'deleted' ? '116 年版已刪除這題' : q.answerChanged ? '116 年版已改過這題，而且正解換了' : '116 年版已改過這題'}）`;
    return `${head}${q.change === 'added' ? '・116 年版新增' : q.change === 'modified' ? (q.prevAnswer ? '・116 年版改過（正解跟 113 年版不同）' : '・116 年版改過') : ''}`;
  }
  if (q.source === 'user-import') return `使用者提供的官方歷屆試題${tail}`;
  if (q.source && q.source.startsWith('original')) {
    const obj = q.objective ? `・官方大綱 ${q.objective}${q.skill ? `（第 ${q.skill} 細項）` : ''}` : '';
    return `原創練習題，不是考題${obj}`;
  }
  return '';
}

/** 原創題的依據網址：只當文字顯示、不做成連結（做成連結＝新增對外連線，見 docs/I） */
export function basisText(q) {
  if (!q.basis) return '';
  const anchor = q.basis_anchor && q.basis_anchor !== '#' ? q.basis_anchor : '';
  const section = anchor && q.basis_section ? `（章節：${q.basis_section}）` : '';
  return `依據（官方文件）：${q.basis}${anchor}${section}`;
}

/**
 * 這題屬於哪一個「讀書單元」：AZ-900 是 節次#細項；內控之後依主題（topic）。沒有單元回 null。
 * 用來記錄「作答前是否讀過這題所屬的單元」（只存在使用者手機，供將來觀察讀書模式有沒有用）。
 */
export function studyKey(q) {
  if (q.objective && q.skill) return `${q.cert}:${q.objective}#${q.skill}`;
  if (q.topic) return `${q.cert}:topic:${q.topic}`;
  return null;
}

/**
 * 一題屬於哪些讀書單元（作答前讀過其中任一個，就算「作答前讀過」）：
 * AZ-900 的節次#細項；內控的考點（point）與「科目＋期別」瀏覽頁。
 */
export function studyKeys(q) {
  const keys = [];
  const k = studyKey(q);
  if (k) keys.push(k);
  if (q.point) keys.push(`${q.cert}:point:${q.point}`);
  if (q.period && q.subject) keys.push(`${q.cert}:period:${q.subject}:${q.period}`);
  return keys;
}

/**
 * 考點清單：每個考點的代表題（最新一期的可練題）與其他期的不同問法。
 * 代表題不存在（例如被停用）的考點略過。依匯入包的順序（考過期數多的在前）。
 */
export function pointList(points, questions) {
  const byId = new Map(questions.map(q => [q.id, q]));
  const out = [];
  for (const p of points || []) {
    const qs = p.ids.map(i => byId.get(i)).filter(Boolean);
    const active = qs.filter(isActive).sort((a, b) => (b.period || 0) - (a.period || 0));
    if (!active.length) continue;
    const rep = active[0];
    const seen = new Set([rep.stem + '|' + rep.options.join('|')]);
    const variants = [];
    for (const q of qs.sort((a, b) => (b.period || 0) - (a.period || 0))) {
      const key = q.stem + '|' + q.options.join('|');
      if (!seen.has(key)) { seen.add(key); variants.push(q); }
    }
    out.push({ id: p.id, kind: p.kind === 'list' ? 'list' : 'rule', periods: [...p.periods].sort((a, b) => a - b), rep, variants, ids: p.ids });
  }
  return out;
}

/**
 * 讀書模式：依官方大綱分組（節次 → 細項 → 題目）。
 * 回傳 { objectives: [{ id, name, domain, count, skills: [{ n, name, questions }] }], other: [...] }。
 * other 是對不到大綱節次或細項的題目（正常應該是 0 題；不是 0 時畫面要顯示出來，不能默默丟掉）。
 */
export function studyGroups(syllabus, questions) {
  const active = questions.filter(isActive);
  const used = new Set();
  const objectives = (syllabus?.objectives || []).map(o => {
    const skills = (o.skills || []).map((name, i) => {
      const qs = active.filter(q => q.objective === o.id && String(q.skill) === String(i + 1))
        .sort((a, b) => a.id.localeCompare(b.id));
      qs.forEach(q => used.add(q.id));
      return { n: i + 1, name, questions: qs };
    });
    return { id: o.id, name: o.name, domain: o.domain, count: skills.reduce((t, k) => t + k.questions.length, 0), skills };
  });
  return { objectives, other: active.filter(q => !used.has(q.id)) };
}

/**
 * 向瀏覽器要求「持久保存」（不會被自動清掉），回傳三種狀態之一（Dispatch 2026-10-09）：
 *   protected   瀏覽器確實回答 true（已經是持久保存，或這次要求被答應）
 *   denied      瀏覽器回答了、但不是 true——紀錄可能被自動清掉
 *   unsupported 瀏覽器沒有這個功能，或查詢時出錯——狀態不明，不能當成安全
 * 只有嚴格等於 true 才算受保護：回傳 undefined、字串之類的一律當成沒答應，不往好的方向猜。
 * 依據：WebKit〈Updates to Storage Policy〉（2023-08-10）——預設盡量保留、不保證；persist() 依「是否從主畫面開啟」等條件決定給不給。
 */
export async function requestPersistence(storage) {
  if (!storage || typeof storage.persist !== 'function' || typeof storage.persisted !== 'function') return { state: 'unsupported', why: '沒有這個功能' };
  try {
    if ((await storage.persisted()) === true) return { state: 'protected' };
    return (await storage.persist()) === true ? { state: 'protected' } : { state: 'denied' };
  } catch (e) {
    return { state: 'unsupported', why: `查詢時出錯：${e && e.message ? e.message : e}` };
  }
}

// ---------------------------------------------------------------- 備份與還原（U4，2026-10-12）
// 備份的是「使用者自己的紀錄」：每次作答、每題進度、錯題本、讀書紀錄、模擬考紀錄。
// 不含題目（題目另外用匯入包匯入；備份檔裡只有題號，沒有任何題目文字）。
export const BACKUP_FORMAT = 'certquiz-backup';
export const BACKUP_VERSION = 1;
export const BACKUP_META_KEYS = ['studied', 'examHistory', 'doubts'];
const BACKUP_STORES = ['attempts', 'progress', 'mistakes'];

/** 從各 store 的內容組成備份物件；counts 讓還原時核對檔案沒有被截斷。 */
export function makeBackup({ attempts, progress, mistakes, meta }, now, appVersion) {
  const m = {};
  for (const k of BACKUP_META_KEYS) if (meta && meta[k] !== undefined) m[k] = meta[k];
  return { format: BACKUP_FORMAT, version: BACKUP_VERSION, created: new Date(now).toISOString(), app: appVersion || '',
    counts: { attempts: attempts.length, progress: progress.length, mistakes: mistakes.length },
    attempts, progress, mistakes, meta: m };
}

/** 摘要：各類筆數、各證照的作答次數、最新一筆作答的時間（用來警告「這台裝置上有比備份更新的紀錄」）。 */
export function backupSummary({ attempts, progress, mistakes }) {
  const certs = {};
  for (const a of attempts) certs[a.cert] = (certs[a.cert] || 0) + 1;
  return { attempts: attempts.length, progress: progress.length, mistakes: mistakes.length, certs,
    lastTs: attempts.reduce((t, a) => Math.max(t, a.ts || 0), 0) };
}

const isStr = x => typeof x === 'string' && x.length > 0;
const isNum = x => typeof x === 'number' && Number.isFinite(x);

/**
 * 驗證備份檔。回傳 { ok, errors[], data }。任何一筆不合格就整份不收（跟匯入包同一個原則：
 * 部分還原會讓使用者以為紀錄是完整的）。
 */
export function validateBackup(obj) {
  const errors = [];
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return { ok: false, errors: ['檔案不是 JSON 物件'] };
  if (obj.format !== BACKUP_FORMAT) errors.push(obj.format === 'certquiz-import' ? '這是題目的匯入包，不是備份檔（題目請到「匯入題目」匯入）' : `不是本 App 的備份檔（format 應為 ${BACKUP_FORMAT}）`);
  if (obj.version !== BACKUP_VERSION) errors.push(`備份檔版本 ${obj.version} 不支援（只支援 ${BACKUP_VERSION}）`);
  if (!isStr(obj.created) || Number.isNaN(Date.parse(obj.created))) errors.push('備份時間格式不對');
  for (const s of BACKUP_STORES) {
    if (!Array.isArray(obj[s])) { errors.push(`缺少 ${s}`); continue; }
    if (!obj.counts || obj.counts[s] !== obj[s].length) errors.push(`${s} 筆數對不上（檔案寫 ${obj.counts && obj.counts[s]}、實際 ${obj[s].length}）——檔案可能不完整`);
  }
  if (errors.length) return { ok: false, errors };
  const keys = new Set();
  obj.attempts.forEach((a, i) => {
    const tag = `作答紀錄第 ${i + 1} 筆`;
    if (!a || !isStr(a.cert) || !isStr(a.qid) || !isNum(a.ts) || typeof a.correct !== 'boolean' || !isStr(a.mode)) errors.push(`${tag}：格式不對`);
    else if (!(isNum(a.chosen) && [1, 2, 3, 4].includes(a.chosen))) errors.push(`${tag}：選項必須是 1～4`);
    if (a && a.studied !== undefined && typeof a.studied !== 'boolean') errors.push(`${tag}：studied 格式不對`);
    if (a && a.n !== undefined) { if (!isNum(a.n) || keys.has(a.n)) errors.push(`${tag}：編號重複或格式不對`); keys.add(a.n); }
  });
  for (const s of ['progress', 'mistakes']) {
    const seen = new Set();
    obj[s].forEach((r, i) => {
      const tag = `${s === 'progress' ? '每題進度' : '錯題本'}第 ${i + 1} 筆`;
      if (!r || !isStr(r.qid) || !isStr(r.cert)) { errors.push(`${tag}：格式不對`); return; }
      if (seen.has(r.qid)) errors.push(`${tag}：題號 ${r.qid} 重複`);
      seen.add(r.qid);
      if (s === 'progress' && !(isNum(r.seen) && isNum(r.correct) && r.correct <= r.seen)) errors.push(`${tag}：作答次數格式不對`);
    });
  }
  const meta = obj.meta || {};
  if (typeof meta !== 'object' || Array.isArray(meta)) errors.push('meta 格式不對');
  else {
    for (const k of Object.keys(meta)) if (!BACKUP_META_KEYS.includes(k)) errors.push(`meta 有不認得的項目：${k}`);
    if (meta.studied !== undefined && (typeof meta.studied !== 'object' || Array.isArray(meta.studied))) errors.push('讀書紀錄格式不對');
    if (meta.examHistory !== undefined && !Array.isArray(meta.examHistory)) errors.push('模擬考紀錄格式不對');
    if (meta.doubts !== undefined && !validDoubts(meta.doubts)) errors.push('「答案有疑問」標記格式不對');
  }
  return errors.length ? { ok: false, errors } : { ok: true, errors, data: { attempts: obj.attempts, progress: obj.progress, mistakes: obj.mistakes, meta } };
}

// ---------------------------------------------------------------- 「答案有疑問」標記（U6，2026-10-12）
// 使用者覺得官方答案怪的題，標起來之後一起看。App 不改答案、不寫自己的解析；標記只是一份清單。
// 存在 meta 'doubts'：{ 題號: { cert, ts, note? } }，跟著備份走。
function validDoubts(d) {
  return !!d && typeof d === 'object' && !Array.isArray(d)
    && Object.entries(d).every(([k, v]) => isStr(k) && v && isStr(v.cert) && isNum(v.ts) && (v.note === undefined || typeof v.note === 'string'));
}

/** 標或取消標記（回傳新的物件，不改原本的）。 */
export function toggleDoubt(doubts, q, now) {
  const out = { ...(doubts || {}) };
  if (out[q.id]) delete out[q.id];
  else out[q.id] = { cert: q.cert, ts: now };
  return out;
}

/** 某張證照被標記的題，新標的排前面；題目已不在題庫（例如重新匯入後被換掉）的另外列出題號。 */
export function doubtList(doubts, questions, cert) {
  const byId = new Map(questions.map(q => [q.id, q]));
  const mine = Object.entries(doubts || {}).filter(([, v]) => v.cert === cert).sort((a, b) => b[1].ts - a[1].ts);
  return { items: mine.filter(([k]) => byId.has(k)).map(([k, v]) => ({ q: byId.get(k), ...v })), missing: mine.filter(([k]) => !byId.has(k)).map(([k]) => k) };
}
