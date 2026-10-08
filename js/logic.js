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
  if (opts.objective) qs = qs.filter(q => q.objective === opts.objective);
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

// ---------------------------------------------------------------- 模擬考
/**
 * 依正式題數出卷：只出可練的題、限定科目、隨機抽 count 題。
 * 題數不夠就不出（ok=false）——用不足的題數考，分數與及格判斷都沒有意義。
 */
export function buildExam(pool, subject, count, seed) {
  const qs = pool.filter(isActive).filter(q => q.subject === subject);
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
