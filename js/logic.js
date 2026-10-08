// 純邏輯（不碰 DOM、不碰 IndexedDB），可以直接用 node 測：scripts/test_logic.mjs

export const IMPORT_FORMAT = 'certquiz-import';
export const IMPORT_VERSION = 1;
export const MISTAKE_CLEAR_STREAK = 2;   // 錯題在錯題模式連續答對幾次才移出

const ID_RE = /^[a-z0-9]+(?:-[a-z0-9]+)+$/;
const SOURCES = new Set(['tabf-official', 'user-import', 'original-ai', 'original-human']);

/**
 * 驗證匯入包。回傳 { ok, errors[], cert, questions[] }。
 * 任何一題不合格就整包不收（不做部分匯入：部分匯入會讓使用者以為題庫是完整的）。
 */
export function validateImportPack(obj, knownCerts) {
  const errors = [];
  if (!obj || typeof obj !== 'object') return { ok: false, errors: ['檔案不是 JSON 物件'], questions: [] };
  if (obj.format !== IMPORT_FORMAT) errors.push(`不是本 App 的匯入包（format 應為 ${IMPORT_FORMAT}）`);
  if (obj.version !== IMPORT_VERSION) errors.push(`匯入包版本 ${obj.version} 不支援（只支援 ${IMPORT_VERSION}）`);
  if (!knownCerts.includes(obj.cert)) errors.push(`不認得的證照：${obj.cert}`);
  const qs = Array.isArray(obj.questions) ? obj.questions : [];
  if (!qs.length) errors.push('匯入包裡沒有題目');
  const ids = new Set();
  qs.forEach((q, i) => {
    const tag = `第 ${i + 1} 題（${q && q.id}）`;
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
    if (!SOURCES.has(q.source)) errors.push(`${tag}：來源欄位不認得（${q.source}）`);
    if (q.dupOf !== undefined && typeof q.dupOf !== 'string') errors.push(`${tag}：dupOf 格式不對`);
  });
  // dupOf 必須指到包內存在、而且本身不是重複的題
  const byId = new Map(qs.map(q => [q && q.id, q]));
  qs.forEach(q => {
    if (q && q.dupOf) {
      const t = byId.get(q.dupOf);
      if (!t) errors.push(`${q.id}：dupOf 指到不存在的題 ${q.dupOf}`);
      else if (t.dupOf) errors.push(`${q.id}：dupOf 指到的題本身也是重複題`);
    }
  });
  return { ok: errors.length === 0, errors, cert: obj.cert, questions: errors.length ? [] : qs };
}

/** 練習時可出的題：不是重複題、沒有標 retired */
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
  if (opts.subject && opts.subject !== 'all') qs = qs.filter(q => q.subject === opts.subject);
  if (opts.source === 'official') qs = qs.filter(q => q.source === 'tabf-official');
  if (opts.source === 'user') qs = qs.filter(q => q.source === 'user-import');
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

/** 作答後錯題本的新狀態。回傳 null 表示不在錯題本（或該移出）。 */
export function nextMistakeState(prev, correct, mode, now) {
  if (!correct) return { wrongCount: (prev?.wrongCount || 0) + 1, streak: 0, ts: now };
  if (!prev) return null;                       // 答對、本來就不在錯題本
  if (mode !== 'mistakes') return prev;         // 一般練習答對不移出，避免猜對就消失
  const streak = (prev.streak || 0) + 1;
  return streak >= MISTAKE_CLEAR_STREAK ? null : { ...prev, streak, ts: now };
}

/** 依答題記錄算統計：{ answered, correct, rate } */
export function summarize(attempts) {
  const answered = attempts.length;
  const correct = attempts.filter(a => a.correct).length;
  return { answered, correct, rate: answered ? correct / answered : 0 };
}

/** 題目的出處說明（畫面顯示用） */
export function sourceLabel(q) {
  const where = q.period ? `第 ${q.period} 期第 ${q.qno} 題` : '';
  const law = q.law_as_of ? `（法規基準：${q.law_as_of}）` : '';
  if (q.source === 'tabf-official') return `官方歷屆試題・${where}${law}`;
  if (q.source === 'user-import') return `使用者提供的官方歷屆試題・${where}${law}`;
  if (q.source && q.source.startsWith('original')) return '原創練習題，不是考題';
  return '';
}
