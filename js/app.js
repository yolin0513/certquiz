// 證照題庫練習 — 畫面與流程
// 原則：題目文字一律用 textContent 放進畫面，不用 innerHTML（匯入檔來自外部，不能讓它被當成程式碼）。
import * as L from './logic.js';
import * as DB from './db.js';
import { loadManifest, loadPool } from './data.js';

const view = document.getElementById('view');
let generation = 0;   // 路由世代碼：快速切頁時，晚到的舊畫面不准蓋掉新畫面

// ---------------------------------------------------------------- 小工具
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// 條件式的區塊（cond ? 區塊 : null）在 h() 裡會被略過，但瀏覽器原生的 replaceChildren 會把 null 印成字串 "null"
// （2026-10-08 使用者回報：答題後出現 nullnull）。所以放進畫面一律經過 fill()／render()，不直接呼叫 replaceChildren。
function clean(nodes) {
  return nodes.flat().filter(n => n !== null && n !== undefined && n !== false);
}

function fill(el, ...nodes) {
  el.replaceChildren(...clean(nodes));
}

function render(gen, ...nodes) {
  if (gen !== generation) return false;
  view.replaceChildren(...clean(nodes));
  window.scrollTo(0, 0);
  return true;
}

function pct(x) { return `${Math.round(x * 100)}%`; }

function params() {
  const [path, qs] = location.hash.replace(/^#/, '').split('?');
  return { path: path || '/', q: new URLSearchParams(qs || '') };
}

function go(hash) { location.hash = hash; }

// ---------------------------------------------------------------- 首頁
async function homeView(gen) {
  const m = await loadManifest();
  const cards = [];
  for (const c of m.certs) {
    // 一張證照的題庫讀不到（例如離線且還沒快取過），只影響那一張卡片，不能讓整個首頁掛掉
    let questions;
    try {
      ({ questions } = await loadPool(c.id));
    } catch (e) {
      cards.push(h('section', { class: 'card' }, h('h2', { text: c.name }),
        h('p', { class: 'ng', text: `題庫暫時讀不到：${e.message}` }),
        h('p', { class: 'muted', text: '連上網路後重新開啟一次，題庫就會存到這台裝置。' })));
      continue;
    }
    const active = questions.filter(L.isActive);
    const attempts = await DB.getAll('attempts', c.id);
    const mistakes = await DB.getAll('mistakes', c.id);
    const s = L.summarize(attempts);
    const body = [];
    if (c.status !== 'active') {
      body.push(h('p', { class: 'muted', text: '準備中' }));
    } else if (!active.length) {
      body.push(h('p', { text: '還沒有題目。' }),
        h('p', { class: 'muted', text: c.questionSource === 'import' ? '這張證照的題目要從「設定 → 匯入題目」放進來（本網站不提供題目）。' : '' }),
        h('a', { class: 'btn', href: '#/settings', text: '去匯入題目' }));
    } else {
      body.push(
        (() => {   // 分版題庫：考試範圍內與範圍外分開寫，不讓範圍外的題算進「可練」
          const out = active.filter(x => !L.inScope(x)).length;
          const dup = questions.length - active.length ? `（重複題 ${questions.length - active.length} 題已隱藏）` : '';
          return out ? h('p', { class: 'stat' }, `考試範圍內 ${active.length - out} 題；另有不在範圍內的 ${out} 題，要另外選才會出${dup}`)
            : h('p', { class: 'stat' }, `可練 ${active.length} 題`, dup ? `（另有${dup.slice(1)}` : '');
        })(),
        h('p', { class: 'stat' }, `已作答 ${s.answered} 次，答對率 ${s.answered ? pct(s.rate) : '—'}，錯題 ${mistakes.length} 題`),
        // 按鈕一律兩欄等寬的格子、順序固定（讀書、練習、錯題、統計，再接模擬考），兩張卡片才排得齊
        h('div', { class: 'actions' },
          h('a', { class: 'btn primary', href: `#/study?cert=${c.id}`, text: '讀書' }),
          h('a', { class: 'btn', href: `#/setup?cert=${c.id}`, text: '開始練習' }),
          h('a', { class: 'btn', href: `#/practice?cert=${c.id}&mode=mistakes&count=20`, 'aria-disabled': mistakes.length ? null : 'true', text: `錯題複習 ${mistakes.length}` }),
          h('a', { class: 'btn', href: `#/stats?cert=${c.id}`, text: '統計' }),
          c.subjects.filter(s => s.exam).map(s => h('a', { class: 'btn', href: `#/exam?cert=${c.id}&subject=${s.id}`,
            text: `模擬考：${s.short || s.name}` })),
          c.exam ? h('a', { class: 'btn', href: `#/exam?cert=${c.id}&subject=all`, text: `模擬考：${c.exam.name}` }) : null));
    }
    cards.push(h('section', { class: 'card' }, h('h2', { text: c.name }), h('p', { class: 'notice', text: c.notice }), ...body));
  }
  render(gen, h('h1', { text: '證照題庫練習' }), ...cards);
}

// ---------------------------------------------------------------- 練習設定
async function setupView(gen, q) {
  const certId = q.get('cert');
  const { cert, questions } = await loadPool(certId);
  const subjects = [{ id: 'all', name: '全部科目' }, ...cert.subjects];
  const hasOutside = questions.some(x => x.scope === 'outside');
  const form = h('form', { class: 'card', onsubmit: e => {
    e.preventDefault();
    const f = new FormData(e.target);
    go(`#/practice?cert=${certId}&mode=practice&subject=${f.get('subject')}&source=${f.get('source')}&count=${f.get('count')}&order=${f.get('order')}${f.get('scope') === 'outside' ? '&scope=outside' : ''}`);
  } },
  h('h2', { text: cert.short }),
  h('label', { text: '科目' }), h('select', { name: 'subject' }, subjects.map(s => h('option', { value: s.id, text: s.name }))),
  hasOutside ? [h('label', { text: '題目範圍' }), h('select', { name: 'scope', id: 'scope' },
    h('option', { value: '', text: '116 年版（考試範圍）' }),
    h('option', { value: 'outside', text: '113 年版裡已刪除或改過的題（不在 116 年考試範圍內）' }))] : null,
  cert.sourceFilter ? [h('label', { text: '來源' }), h('select', { name: 'source' },
    h('option', { value: 'all', text: '全部' }), h('option', { value: 'official', text: '只出從官網下載的' }),
    h('option', { value: 'user', text: '只出我自己提供的' }))] : h('input', { type: 'hidden', name: 'source', value: 'all' }),
  h('label', { text: '題數' }), h('select', { name: 'count' }, [10, 20, 50].map(n => h('option', { value: n, text: `${n} 題` }))),
  h('label', { text: '出題順序' }), h('select', { name: 'order' },
    h('option', { value: 'unseen', text: '沒做過的優先' }), h('option', { value: 'random', text: '完全隨機' })),
  h('button', { class: 'btn primary', type: 'submit', text: '開始' }));
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }), form, lawSummaryCard(L.lawSummary(questions)));
}

// ---------------------------------------------------------------- 練習
async function practiceView(gen, q) {
  const certId = q.get('cert');
  const mode = q.get('mode') === 'mistakes' ? 'mistakes' : 'practice';
  const { cert, questions } = await loadPool(certId);
  let picked;
  if (mode === 'mistakes') {
    const ms = new Map((await DB.getAll('mistakes', certId)).map(m => [m.qid, m]));
    picked = L.shuffle(questions.filter(x => ms.has(x.id)), L.rng(Date.now())).slice(0, Number(q.get('count')) || 20);
  } else {
    const prog = new Map((await DB.getAll('progress', certId)).map(p => [p.qid, p]));
    picked = L.pickQuestions(questions, { subject: q.get('subject') || 'all', source: q.get('source') || 'all',
      count: Number(q.get('count')) || 10, order: q.get('order') || 'unseen',
      objective: q.get('objective') || '', skill: q.get('skill') || '', period: q.get('period') || '', scope: q.get('scope') || '',
      ids: q.get('set') === 'points' ? new Set(L.pointList(await DB.getMeta(`points:${certId}`, []), questions).map(x => x.rep.id)) : null }, prog);
  }
  if (!picked.length) {
    render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
      h('section', { class: 'card' }, h('p', { text: mode === 'mistakes' ? '錯題本是空的。' : '這個條件下沒有題目。' })));
    return;
  }
  const studiedMap = await DB.getMeta('studied', {});
  const lawSum = L.lawSummary(questions);
  const results = [];
  let i = 0;

  const showQuestion = () => {
    const item = picked[i];
    const opts = item.options.map((text, k) => h('button', { class: 'opt', type: 'button', 'data-k': k + 1, onclick: () => answer(k + 1) },
      h('span', { class: 'k', text: `(${k + 1})` }), h('span', { text })));
    const feedback = h('div', { class: 'feedback', hidden: true });
    const next = h('button', { class: 'btn primary', type: 'button', hidden: true, text: i + 1 < picked.length ? '下一題' : '看結果',
      onclick: () => { i += 1; i < picked.length ? showQuestion() : showSummary(); } });

    async function answer(k) {
      if (!next.hidden) return;
      const correct = k === item.answer;
      for (const b of opts) {
        const bk = Number(b.dataset.k);
        b.disabled = true;
        if (bk === item.answer) b.classList.add('right');
        else if (bk === k) b.classList.add('wrong');
      }
      fill(feedback, h('p', { class: correct ? 'ok' : 'ng', text: correct ? '答對了' : `答錯了，正解是 (${item.answer})` }),
        h('p', { class: 'src', text: L.sourceLabel(item) }),
        item.explain ? h('p', { class: 'explain', text: item.explain }) : null,
        item.basis ? h('p', { class: 'src basis', text: L.basisText(item) }) : null,
        answerChangeNote(item, questions),
        lawNote(item, lawSum));
      feedback.hidden = false;
      next.hidden = false;
      results.push({ item, k, correct });
      const prev = await DB.get('mistakes', item.id);
      await DB.recordAnswer({ q: item, chosen: k, correct, mode, mistakeState: L.nextMistakeState(prev, correct, mode, Date.now()),
        studied: studiedBefore(studiedMap, item) });
    }

    render(gen,
      h('div', { class: 'bar' }, h('a', { class: 'back', href: '#/', text: '← 結束' }), h('span', { text: `${i + 1} / ${picked.length}` })),
      h('section', { class: 'card q' },
        item.source && item.source.startsWith('original') ? h('p', { class: 'src', text: L.sourceLabel(item) }) : null,
        item.scope === 'outside' ? h('p', { class: 'ng scope-out', text: `不在 116 年考試範圍內：${item.change === 'deleted' ? '116 年版已刪除這題' : item.answerChanged ? '116 年版已改過這題，而且正解換了（作答後會列出新舊正解）' : '116 年版已改過這題'}。練這題可能學到過時的內容。` }) : null,
        item.law && item.law.status === 'amended' ? (b => h('p', { class: 'ng law-pre', text: b
          ? `這題點名的「${b.name}」在考試後修正過；題庫裡點名它的 ${b.total} 題整批依舊版出題。作答後會列出修正日期。`
          : '這題點名的法規在考試後修正過，作答後會列出修正日期。' }))(L.lawBatchOf(item, lawSum.batches)) : null,
        h('p', { class: 'stem', text: item.stem }), h('div', { class: 'opts' }, opts), feedback, next));
  };

  const showSummary = () => {
    const ok = results.filter(r => r.correct).length;
    const wrong = results.filter(r => !r.correct);
    render(gen,
      h('section', { class: 'card' }, h('h2', { text: `${cert.short}：${ok} / ${results.length}（${pct(ok / results.length)}）` }),
        wrong.length ? h('h3', { text: '這一輪答錯的題' }) : h('p', { text: '全部答對。' }),
        h('ol', { class: 'wronglist' }, wrong.map(r => h('li', {},
          h('p', { text: r.item.stem }),
          h('p', { class: 'muted', text: `你選 (${r.k})，正解 (${r.item.answer}) ${r.item.options[r.item.answer - 1]}` }),
          h('p', { class: 'src', text: L.sourceLabel(r.item) }),
          r.item.basis ? h('p', { class: 'src basis', text: L.basisText(r.item) }) : null))),
        h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/setup?cert=${certId}`, text: '再練一輪' }),
          h('a', { class: 'btn', href: '#/', text: '回首頁' }))));
  };

  showQuestion();
}

// ---------------------------------------------------------------- 模擬考
// 照正式規格：題數、時間、每題分數、及格線都讀 certs.json 的 exam 設定。作答中不顯示對錯；時間到自動交卷。
// 未作答的題不寫作答紀錄（JLPT 的決定：沒作答不代表不會）。進行中的考試離開頁面就作廢（M2 第一版的限制）。
async function examView(gen, q) {
  const certId = q.get('cert');
  const subjectId = q.get('subject');
  const { cert, questions } = await loadPool(certId);
  const studiedMap = await DB.getMeta('studied', {});
  const subject = subjectId === 'all' && cert.exam ? { id: 'all', name: cert.exam.name, exam: cert.exam } : cert.subjects.find(s => s.id === subjectId);
  if (!subject || !subject.exam) { render(gen, h('p', { text: '這個科目沒有模擬考設定。' })); return; }
  const ex = subject.exam;
  const built = L.buildExam(questions, subjectId, ex.count, Date.now(), ex.mix);
  const back = h('a', { class: 'back', href: '#/', text: '← 回首頁' });
  if (!built.ok) {
    render(gen, back, h('section', { class: 'card' }, h('h2', { text: `模擬考：${subject.name}` }),
      h('p', { text: `可出的題目只有 ${built.available} 題，不足正式的 ${ex.count} 題，無法出卷。` })));
    return;
  }
  render(gen, back, h('section', { class: 'card' }, h('h2', { text: `模擬考：${subject.name}` }),
    h('ul', {}, h('li', { text: `${ex.count} 題四選一，${ex.minutes} 分鐘` }), h('li', { text: `每題 ${ex.points} 分，${ex.pass} 分及格；答錯不倒扣` }),
      h('li', { text: '作答中不顯示對錯；可以改答案、跳題' }), h('li', { text: '時間到自動交卷；中途離開這一頁，這次考試就作廢' })),
    h('button', { class: 'btn primary', type: 'button', text: '開始考試', onclick: () => start() })));

  function start() {
    const qs = built.questions;
    const answers = new Map();
    const startAt = Date.now();
    const deadline = startAt + ex.minutes * 60000;
    let i = 0, finished = false;
    const clock = h('span', { class: 'clock' });
    const counter = h('span', { class: 'muted' });
    const body = h('section', { class: 'card q' });
    const grid = h('div', { class: 'grid' });
    const confirmBox = h('div', { class: 'confirm', hidden: true });
    const tick = () => {
      if (gen !== generation) { clearInterval(timer); return; }   // 已經離開這一頁：停表，這次作廢
      const left = L.remainingMs(deadline, Date.now());
      clock.textContent = `剩 ${L.formatClock(left)}`;
      if (left === 0) finish(true);
    };
    const timer = setInterval(tick, 1000);

    const drawGrid = () => fill(grid, ...qs.map((x, n) => h('button', {
      type: 'button', class: `cell${answers.has(x.id) ? ' done' : ''}${n === i ? ' cur' : ''}`, text: String(n + 1),
      onclick: () => { i = n; show(); } })));

    function show() {
      const item = qs[i];
      counter.textContent = `已答 ${answers.size}／${qs.length}`;
      fill(body, 
        h('p', { class: 'muted', text: `第 ${i + 1} 題` }), h('p', { class: 'stem', text: item.stem }),
        h('div', { class: 'opts' }, item.options.map((t, k) => h('button', {
          type: 'button', class: `opt${answers.get(item.id) === k + 1 ? ' picked' : ''}`, 'data-k': k + 1,
          onclick: () => { answers.set(item.id, k + 1); show(); } }, h('span', { class: 'k', text: `(${k + 1})` }), h('span', { text: t })))),
        h('div', { class: 'row' },
          h('button', { class: 'btn', type: 'button', text: '上一題', disabled: i === 0, onclick: () => { i--; show(); } }),
          h('button', { class: 'btn', type: 'button', text: '下一題', disabled: i === qs.length - 1, onclick: () => { i++; show(); } })));
      drawGrid();
    }

    function askSubmit() {
      const left = qs.length - answers.size;
      if (left === 0) { finish(false); return; }
      fill(confirmBox, h('p', { text: `還有 ${left} 題未作答，未作答不給分。確定交卷？` }),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'button', text: '確定交卷', onclick: () => finish(false) }),
          h('button', { class: 'btn', type: 'button', text: '繼續作答', onclick: () => { confirmBox.hidden = true; } })));
      confirmBox.hidden = false;
    }

    async function finish(timeUp) {
      if (finished) return;
      finished = true;
      clearInterval(timer);
      const r = L.scoreExam(qs, answers, ex);
      const usedSec = Math.round((Math.min(Date.now(), deadline) - startAt) / 1000);
      for (const item of qs) {
        const k = answers.get(item.id);
        if (k === undefined) continue;
        const prev = await DB.get('mistakes', item.id);
        await DB.recordAnswer({ q: item, chosen: k, correct: k === item.answer, mode: 'exam', studied: studiedBefore(studiedMap, item),
          mistakeState: L.nextMistakeState(prev, k === item.answer, 'exam', Date.now()) });
      }
      const hist = await DB.getMeta('examHistory', []);
      hist.unshift({ cert: certId, subject: subjectId, ts: Date.now(), count: qs.length, correct: r.correct,
        unanswered: r.unanswered, score: r.score, passed: r.passed, usedSec, timeUp });
      await DB.setMeta('examHistory', hist.slice(0, 30));
      const missed = qs.filter(x => answers.get(x.id) !== x.answer);
      render(gen,
        h('section', { class: 'card' },
          h('h2', { class: r.passed ? 'ok' : 'ng', text: `${subject.name}：${r.score} 分（${r.passed ? '及格' : '不及格'}）` }),
          h('p', { text: `答對 ${r.correct}、答錯 ${r.wrong}、未作答 ${r.unanswered}／${r.total} 題；及格線 ${ex.pass} 分` }),
          h('p', { class: 'muted', text: `${timeUp ? '時間到自動交卷' : '交卷'}，用時 ${L.formatClock(usedSec * 1000)}` }),
          h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/exam?cert=${certId}&subject=${subjectId}`, text: '再考一次' }),
            h('a', { class: 'btn', href: '#/', text: '回首頁' }))),
        missed.length ? h('section', { class: 'card' }, h('h3', { text: `答錯與未作答（${missed.length} 題）` }),
          h('ol', { class: 'wronglist' }, missed.map(x => h('li', {},
            h('p', { text: x.stem }),
            h('p', { class: 'muted', text: `${answers.has(x.id) ? `你選 (${answers.get(x.id)})` : '未作答'}，正解 (${x.answer}) ${x.options[x.answer - 1]}` }),
            h('p', { class: 'src', text: L.sourceLabel(x) }),
            x.basis ? h('p', { class: 'src basis', text: L.basisText(x) }) : null)))) : null);
    }

    // 確認框放在固定於頂端的那一塊裡：捲到下面按「交卷」時，確認框才看得到（放在頁首會被固定列蓋住、看不到）
    render(gen,
      h('div', { class: 'sticky' },
        h('div', { class: 'bar' }, clock, counter, h('button', { class: 'btn primary', type: 'button', text: '交卷', onclick: askSubmit })),
        confirmBox),
      body, h('section', { class: 'card' }, h('p', { class: 'muted', text: '題號（深色＝已作答）' }), grid));
    tick();
    show();
  }
}

// ---------------------------------------------------------------- 讀書模式
/** 作答前是否讀過這題所屬的讀書單元；題目沒有讀書單元時回 undefined（不記） */
function studiedBefore(map, q) {
  const keys = L.studyKeys(q);
  return keys.length ? keys.some(k => Boolean(map[k])) : undefined;
}

async function markStudied(keys) {
  const map = await DB.getMeta('studied', {});
  const now = Date.now();
  for (const k of keys) map[k] = { first: map[k]?.first ?? now, last: now };
  await DB.setMeta('studied', map);
}

// 先讀再練：依官方大綱（節次 → 細項）列出題目、正解、解析與依據，不必作答。
async function studyView(gen, q) {
  const certId = q.get('cert');
  const { cert, questions } = await loadPool(certId);
  const back = h('a', { class: 'back', href: '#/', text: '← 回首頁' });
  if (!cert.syllabus) {
    if (questions.some(x => x.version)) await versionedStudyView(gen, q, cert, questions);
    else await importStudyView(gen, q, cert, questions);
    return;
  }
  const g = L.studyGroups(cert.syllabus, questions);
  const objId = q.get('objective');
  const skillN = Number(q.get('skill'));
  const obj = g.objectives.find(o => o.id === objId);
  const skill = obj && obj.skills.find(k => k.n === skillN);

  if (!skill) {
    // 大綱目錄：依領域分段，每個細項一個連結，附題數
    const domains = [...new Set(g.objectives.map(o => o.domain))];
    const studied = await DB.getMeta('studied', {});
    render(gen, back,
      h('section', { class: 'card' }, h('h2', { text: `${cert.short} 讀書：依官方大綱` }),
        h('p', { class: 'muted', text: `${cert.syllabus.version}。細項名稱是官方原文；點進去可以看題目、正解、解析與依據，看完再練那一節。` })),
      domains.map(d => h('section', { class: 'card' }, h('h3', { text: d }),
        g.objectives.filter(o => o.domain === d).map(o => h('div', { class: 'study-obj' },
          h('p', { class: 'stat' }, h('b', { text: `${o.id} ${o.name}` }), `（${o.count} 題）`),
          // 細項是可點的列（不是裸連結）；「讀過」用文字標，不靠連結的已點／未點顏色
          h('div', { class: 'study-skills' }, o.skills.map(k => k.questions.length
            ? h('a', { class: 'item', href: `#/study?cert=${certId}&objective=${o.id}&skill=${k.n}` },
              h('span', { class: 'n', text: `${k.n}.` }), h('span', { class: 'name', text: k.name }),
              h('span', { class: 'meta', text: `${k.questions.length} 題${studied[L.studyKey(k.questions[0])] ? '・✓ 已讀' : ''}` }))
            : h('div', { class: 'item none' }, h('span', { class: 'n', text: `${k.n}.` }), h('span', { class: 'name', text: k.name }),
              h('span', { class: 'meta', text: '沒有題目' })))))))),
      g.other.length ? h('section', { class: 'card' }, h('p', { class: 'ng', text: `有 ${g.other.length} 題對不到大綱節次，請回報。` })) : null);
    return;
  }

  // 一個細項：逐題列出；記下「讀過這個單元」（第一次與最近一次的時間），作答時用來標示「作答前是否讀過」
  const key = L.studyKey(skill.questions[0]);
  if (key) await markStudied([key]);
  const all = g.objectives.flatMap(o => o.skills.filter(k => k.questions.length).map(k => ({ o, k })));
  const at = all.findIndex(x => x.o.id === obj.id && x.k.n === skill.n);
  const link = x => x && h('a', { class: 'btn', href: `#/study?cert=${certId}&objective=${x.o.id}&skill=${x.k.n}`,
    text: at > all.indexOf(x) ? '← 上一個細項' : '下一個細項 →' });
  const n = skill.questions.length;
  render(gen,
    h('a', { class: 'back', href: `#/study?cert=${certId}`, text: '← 回大綱' }),
    h('section', { class: 'card' },
      h('p', { class: 'muted', text: `${obj.id} ${obj.name}` }),
      h('h2', { text: `第 ${skill.n} 細項：${skill.name}` }),
      h('p', { class: 'muted', text: `${n} 題。正解以綠色標出；解析指回官方文件。` })),
    skill.questions.map((x, i) => h('section', { class: 'card study-q' },
      h('p', { class: 'muted', text: `${i + 1}／${n}` }),
      h('p', { class: 'stem', text: x.stem }),
      h('ol', { class: 'study-opts' }, x.options.map((t, k) => h('li', { class: k + 1 === x.answer ? 'right' : null },
        h('span', { text: t }), k + 1 === x.answer ? h('b', { text: '（正解）' }) : null))),
      x.explain ? h('p', { class: 'explain', text: x.explain }) : null,
      x.basis ? h('p', { class: 'src basis', text: L.basisText(x) }) : null,
      h('p', { class: 'src', text: L.sourceLabel(x) }))),
    h('section', { class: 'card' },
      h('div', { class: 'row' },
        h('a', { class: 'btn primary', href: `#/practice?cert=${certId}&mode=practice&objective=${obj.id}&skill=${skill.n}&count=${n}&order=unseen`,
          text: `讀完了，練這 ${n} 題` })),
      h('div', { class: 'row' }, link(all[at - 1]), link(all[at + 1]))));
}

// 內控（匯入的官方題）讀書模式：反覆考過的規定＋依科目與期別瀏覽。
// 一組＝同一條規定在不同期被考過（問法可能不同）；對讀書有用的單位是「規定」，不是「事實」（Dispatch 2026-10-08，docs/K）。
// 沒有官方解析，所以這裡只有題目與官方正解，不寫任何自己的說明（docs/K）。
async function importStudyView(gen, q, cert, questions) {
  const certId = cert.id;
  const view = q.get('view') === 'browse' ? 'browse' : 'points';
  const tabs = h('div', { class: 'row' },
    h('a', { class: view === 'points' ? 'btn primary' : 'btn', href: `#/study?cert=${certId}`, text: '反覆考過的規定' }),
    h('a', { class: view === 'browse' ? 'btn primary' : 'btn', href: `#/study?cert=${certId}&view=browse`, text: '依科目與期別瀏覽' }));
  const active = questions.filter(L.isActive);
  const subjName = new Map(cert.subjects.map(s => [s.id, s.short || s.name]));
  const optsList = x => h('ol', { class: 'study-opts' }, x.options.map((t, k) => h('li', { class: k + 1 === x.answer ? 'right' : null },
    h('span', { text: t }), k + 1 === x.answer ? h('b', { text: '（正解）' }) : null)));
  const home = h('a', { class: 'back', href: '#/', text: '← 回首頁' });
  if (!active.length) {
    render(gen, home, h('section', { class: 'card' },
      h('p', { text: '還沒有題目。這張證照的題目要從「設定 → 匯入題目」放進來。' }), h('a', { class: 'btn', href: '#/settings', text: '去匯入題目' })));
    return;
  }
  const lawSum = L.lawSummary(questions);

  if (view === 'points') {
    const list = L.pointList(await DB.getMeta(`points:${certId}`, []), questions);
    const covered = list.reduce((t, x) => t + x.ids.length, 0);
    const n = list.length;
    const notice = () => h('section', { class: 'card warn' },
      h('h3', { text: '這不是考試範圍——只列出「證明得了」被反覆考過的規定' }),
      h('p', { text: '每一組都逐組核對過，確定問的是同一條規定（核對時混入了刻意造的假組做對照，假組全部被挑出來）。' }),
      h('p', { text: '一組＝同一條規定在不同期被考過，問法可能不同（正問、反問、換一個數字或條件問）。讀懂那條規定，這一組的題目都會答。' }),
      h('p', { text: '少數幾組不是法規，是教材上的同一份清單被反覆考（例如影響消費金融業務的因素、COSO 的內部控制要素）。這類沒有條號可以指，出處也還沒查證，卡片上標「同一份清單（出處未查證）」，跟「同一條規定」分開。讀懂那份清單，一樣這一組都會答。' }),
      h('p', { text: '目前的分組是程式用「題目寫法相似」找出來的：題幹與正解逐字相同或高度相似才會被找到。同一條規定換個寫法再考，程式比對不出來，會被漏掉。' }),
      h('p', { text: '所以：沒出現在這份清單上，不代表那條規定不常考。這份清單是「先讀哪些」的參考，不是全部要讀的範圍；其餘題目請用「依科目與期別瀏覽」讀。' }),
      h('p', { text: `也因為是用相似度找的，這 ${n} 組量的是「題目寫法重複」，不等於「這條規定重要」：一條規定如果每次換不同問法考，反而不會出現在這份清單上。` }),
      h('p', { class: 'muted', text: '題目沒有官方解析，這裡只列題目與官方答案卷的正解。' }));
    if (!list.length) {
      render(gen, home, tabs, notice(),
        h('section', { class: 'card' }, h('p', { text: '這份匯入包沒有「反覆考過的規定」資料。請用新版的匯入包重新匯入（設定 → 匯入題目）。' })));
      return;
    }
    await markStudied(list.map(x => `${certId}:point:${x.id}`));
    render(gen, home, tabs, notice(), lawSummaryCard(lawSum),
      h('section', { class: 'card' },
        h('h2', { text: `${cert.short}：反覆考過的規定 ${n} 組` }),
        h('p', { class: 'muted', text: `涵蓋 ${covered} 題次；可練的題目一共 ${active.length} 題。依考過的期數排序，考過越多期的排越前面。` }),
        h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/practice?cert=${certId}&mode=practice&set=points&count=${list.length}&order=unseen`,
          text: `讀完了，練這 ${n} 組（各一題）` }))),
      list.map((x, i) => h('section', { class: 'card study-q' },
        h('p', { class: 'muted', text: `${i + 1}／${n}・${x.kind === 'list' ? '同一份清單（出處未查證）' : '同一條規定'}考過 ${x.periods.length} 期（問法可能不同）：第 ${x.periods.join('、')} 期・${subjName.get(x.rep.subject) || ''}` }),
        h('p', { class: 'stem', text: x.rep.stem }),
        optsList(x.rep),
        h('p', { class: 'src', text: L.sourceLabel(x.rep) }),
        lawNote(x.rep, lawSum),
        x.variants.length ? h('details', {}, h('summary', { text: `其他期的問法（${x.variants.length}）` }),
          x.variants.map(v => h('div', { class: 'variant' }, h('p', { class: 'stem', text: v.stem }),
            h('p', { class: 'muted', text: `正解：(${v.answer}) ${v.options[v.answer - 1]}` }), h('p', { class: 'src', text: L.sourceLabel(v) })))) : null)),
      notice());
    return;
  }

  // 依科目與期別瀏覽
  const subject = q.get('subject');
  const period = q.get('period');
  if (!subject || !period) {
    const groups = cert.subjects.map(s => {
      const periods = [...new Set(active.filter(x => x.subject === s.id && x.period).map(x => x.period))].sort((a, b) => b - a);
      return h('section', { class: 'card' }, h('h3', { text: subjName.get(s.id) }),
        h('div', { class: 'row' }, periods.map(pd => h('a', { class: 'btn', href: `#/study?cert=${certId}&view=browse&subject=${s.id}&period=${pd}`,
          text: `第 ${pd} 期（${active.filter(x => x.subject === s.id && x.period === pd).length} 題）` }))));
    });
    render(gen, home, tabs, lawSummaryCard(lawSum),
      h('section', { class: 'card' }, h('p', { class: 'muted', text: '逐期瀏覽題目與官方正解。重複出現的題目只列在最新的那一期。' })), groups);
    return;
  }
  const list = active.filter(x => x.subject === subject && String(x.period) === String(period)).sort((a, b) => (a.qno || 0) - (b.qno || 0));
  await markStudied([`${certId}:period:${subject}:${period}`]);
  render(gen, h('a', { class: 'back', href: `#/study?cert=${certId}&view=browse`, text: '← 回期別清單' }), tabs, lawSummaryCard(lawSum),
    h('section', { class: 'card' }, h('h2', { text: `${subjName.get(subject) || subject}・第 ${period} 期（${list.length} 題）` }),
      h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/practice?cert=${certId}&mode=practice&subject=${subject}&period=${period}&count=${list.length}&order=unseen`,
        text: `讀完了，練這 ${list.length} 題` }))),
    list.map((x, i) => h('section', { class: 'card study-q' },
      h('p', { class: 'muted', text: `${i + 1}／${list.length}` }),
      h('p', { class: 'stem', text: x.stem }),
      optsList(x),
      h('p', { class: 'src', text: L.sourceLabel(x) }),
      lawNote(x, lawSum))));
}

// ---------------------------------------------------------------- 法規修正標示（N1，Dispatch 2026-10-12）
// 所有數字都從匯入的題目數出來（L.lawSummary），不寫死。三句限度一定在畫面上；沒有版本資料的題也要有一句說明，不能只有沉默。
// 只寫官方事實（哪一部、哪一天修正），不寫「答案變了」；正解一律是官方答案卷的答案。
function lawLimits(sum) {
  const pend = sum.batches.filter(b => b.pending);
  return h('ul', { class: 'law-limits' },
    h('li', {}, h('b', { text: '有標示，不代表答案錯了。' }), '程式只知道整部法規改過，不知道題目問的那一條有沒有改。正解仍是官方答案卷的答案。'),
    pend.map(b => h('li', {}, h('b', { text: `「${b.name}」${b.latest} 那次修正，有部分條文還沒施行。` }),
      `全國法規資料庫寫：${b.pending}。你考試那天適用哪一版，要看考試日期。`)),
    h('li', {}, h('b', { text: '沒有標示，也不代表一定還有效。' }),
      `可練的 ${sum.total} 題裡，只有 ${sum.hasData} 題查得到法規的版本資料；其他 ${sum.none} 題沒有任何版本資料，我們不知道它依據的規定有沒有改過。`));
}

function lawSummaryCard(sum) {
  if (!sum.total) return null;
  return h('section', { class: 'card law-summary' },
    h('h3', { text: '法規修正：有些題目依據的法規，在考試後改過' }),
    h('p', { text: `可練的 ${sum.total} 題裡：考試後修正過 ${sum.amended} 題；查得到、考試後沒修正 ${sum.unchanged} 題；`
      + `${sum.partial ? `只查得到一部分、沒看到修正 ${sum.partial} 題；` : ''}沒有版本資料 ${sum.none} 題。` }),
    sum.batches.map(b => h('div', { class: 'law-batch' },
      h('p', { class: 'law-batch-h', text: `「${b.name}」整批依舊版` }),
      h('p', { text: `題庫裡點名這部法規的 ${b.total} 題，全部是照考試當時的舊版出題；它在 ${b.latest} 又修正過。這些題的官方正解是依舊版，讀的時候要知道。` }))),
    lawLimits(sum),
    h('p', { class: 'muted', text: `法規版本資料查詢日 ${sum.checked}（全國法規資料庫、金管會主管法規查詢系統）。每題的「法規基準日」是那期答案卷的疑義申請起日（測驗後約兩天）。` }));
}

function lawNote(item, sum) {
  const x = item.law;
  if (!x) return null;
  const asof = item.law_as_of ? `這期的法規基準日是 ${item.law_as_of}` : '';
  if (x.status === 'amended') {
    const b = L.lawBatchOf(item, sum.batches);
    return h('div', { class: 'law-note amended' },
      h('p', { class: 'law-batch-h', text: '這題點名的法規，在考試後修正過' }),
      x.laws.filter(e => e.after.length).map(e => h('p', { text: `「${e.name}」在 ${e.after.join('、')} 修正過（${asof}）。${e.pending ? `其中有部分條文還沒施行：${e.pending}。` : ''}` })),
      b ? h('p', { text: `題庫裡點名「${b.name}」的 ${b.total} 題全部是這種情況（整批依舊版）。` }) : null,
      h('p', { class: 'muted', text: '有標示不代表答案錯了：程式只知道整部法規改過，不知道這題問的那一條有沒有改。正解是官方答案卷的答案。' }));
  }
  const names = x.laws.map(e => `「${e.name}」`).join('、');
  const text = x.status === 'unchanged' ? `題目點名的法規 ${names} 查得到的版本，在這期考試後沒有修正（${asof}；查詢日 ${x.checked}）。`
    : x.status === 'partial' ? `題目點名的法規 ${names} 只查得到一部分的版本資料：查得到的沒有修正，查不到的不能保證。`
    : `這題沒有法規版本資料（${x.laws.length ? `點名的 ${names} 查不到版本` : '題目沒有點名法規'}），不知道依據的規定在考試後有沒有改過。沒有標示不代表仍然有效。`;
  return h('p', { class: 'src law-note', text });
}

// 正解換了的題（113 年版 → 116 年版）：寫明新舊正解各是什麼。照舊版背會「確信地答錯」，所以作答後與讀書頁都單獨標出來。
function answerChangeNote(item, questions) {
  if (item.prevAnswer) {
    return h('p', { class: 'ng answer-changed', text: `注意：這題的正解改過。113 年版的正解是 (${item.prevAnswer.answer})「${item.prevAnswer.text}」；116 年版改成 (${item.answer})「${item.options[item.answer - 1]}」。照 113 年版背會答錯。` });
  }
  if (item.answerChanged && item.newId) {
    const nw = questions.find(x => x.id === item.newId);
    if (nw) return h('p', { class: 'ng answer-changed', text: `注意：這是 113 年版，正解是 (${item.answer})「${item.options[item.answer - 1]}」；116 年版改成 (${nw.answer})「${nw.options[nw.answer - 1]}」。考試以 116 年版為準。` });
  }
  return null;
}

// 分版題庫（金融市場常識與職業道德）的讀書頁：116 年版依科目逐題列；113 年版裡不在考試範圍的題另外一頁，標明為什麼不在範圍。
// 只列題目與官方正解，不寫自己的解析（docs/L）。
async function versionedStudyView(gen, q, cert, questions) {
  const PAGE = 50;
  const view = ['outside', ...cert.subjects.map(s => s.id)].includes(q.get('view')) ? q.get('view') : cert.subjects[0].id;
  const page = Math.max(1, Number(q.get('page')) || 1);
  const active = questions.filter(L.isActive);
  const byId = new Map(questions.map(x => [x.id, x]));
  const inScope = id => active.filter(x => L.inScope(x) && x.subject === id);
  const outside = active.filter(x => !L.inScope(x));
  const subjNameAll = new Map(cert.subjects.map(s => [s.id, s.name]));
  const tab = (v, text) => h('a', { class: view === v ? 'btn primary' : 'btn', href: `#/study?cert=${cert.id}&view=${v}`, text });
  const opts = x => h('ol', { class: 'study-opts' }, x.options.map((t, k) => h('li', { class: k + 1 === x.answer ? 'right' : null },
    h('span', { text: t }), k + 1 === x.answer ? h('b', { text: '（正解）' }) : null)));
  const list = view === 'outside' ? outside.slice().sort((a, b) => a.subject.localeCompare(b.subject) || a.qno - b.qno)
    : inScope(view).sort((a, b) => a.qno - b.qno);
  const pages = Math.max(1, Math.ceil(list.length / PAGE));
  const shown = list.slice((page - 1) * PAGE, page * PAGE);
  const subjName = new Map(cert.subjects.map(s => [s.id, s.name]));
  const pager = pages > 1 ? h('div', { class: 'row' }, Array.from({ length: pages }, (_, k) => h('a', {
    class: k + 1 === page ? 'btn primary' : 'btn', href: `#/study?cert=${cert.id}&view=${view}&page=${k + 1}`, text: `${k * PAGE + 1}～${Math.min((k + 1) * PAGE, list.length)}` }))) : null;
  const changed = active.filter(x => x.prevAnswer);
  const changedCard = view === 'outside' && changed.length ? h('section', { class: 'card warn', id: 'answer-changed' },
    h('h3', { text: `正解換了的題（${changed.length} 題）` }),
    h('p', { text: '這些題 116 年版改過，而且正解換成另一個選項。照 113 年版背的話，會把錯的那個選項記成對的。' }),
    changed.map(x => h('div', { class: 'variant' },
      h('p', { class: 'muted', text: `${subjNameAll.get(x.subject)}・116 年版第 ${x.qno} 題（113 年版第 ${x.prevAnswer.qno} 題）` }),
      h('p', { class: 'stem', text: x.stem }),
      h('p', { text: `113 年版的正解：(${x.prevAnswer.answer})「${x.prevAnswer.text}」` }),
      h('p', { class: 'ok', text: `116 年版的正解：(${x.answer})「${x.options[x.answer - 1]}」（考試以這個為準）` })))) : null;
  const head = view === 'outside'
    ? h('section', { class: 'card warn', id: 'scope-note' }, h('h3', { text: `不在 116 年考試範圍內（113 年版，${outside.length} 題）` }),
      h('p', { text: '這些是 113 年版題庫裡、116 年版已經刪除或改過的題。116 年版從 2027 年 1 月 1 日起適用，這些題不會出現在你的考試裡。' }),
      h('p', { text: '改過的題，下面同時列出 116 年版的寫法與正解；背 116 年版的那一個。' }))
    : h('section', { class: 'card', id: 'scope-note' }, h('h2', { text: `116 年版・${subjName.get(view)}（${list.length} 題）` }),
      h('p', { class: 'muted', text: '116 年版是考試範圍（2027 年 1 月 1 日起適用）。題目與正解照證基會公告題庫，這裡不寫解析。' }),
      h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/practice?cert=${cert.id}&mode=practice&subject=${view}&count=50&order=unseen`, text: '練這一科（50 題）' })));
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
    h('div', { class: 'row' }, cert.subjects.map(s => tab(s.id, `116 年版・${s.name}（${inScope(s.id).length}）`)), tab('outside', `不在考試範圍（${outside.length}）`)),
    changedCard, head, pager,
    shown.map(x => {
      const nw = x.newId ? byId.get(x.newId) : null;
      return h('section', { class: 'card study-q' },
        h('p', { class: 'src', text: `${subjName.get(x.subject)}・${L.sourceLabel(x)}` }),
        h('p', { class: 'stem', text: x.stem }), opts(x),
        nw ? h('div', { class: 'variant' }, h('p', { class: 'muted', text: `116 年版的這題（第 ${nw.qno} 題）：` }),
          h('p', { class: 'stem', text: nw.stem }), h('p', { class: 'ok', text: `正解：(${nw.answer}) ${nw.options[nw.answer - 1]}` })) : null);
    }),
    pager);
}

// ---------------------------------------------------------------- 統計
async function statsView(gen, q) {
  const certId = q.get('cert');
  const { cert, questions } = await loadPool(certId);
  const byId = new Map(questions.map(x => [x.id, x]));
  const attempts = await DB.getAll('attempts', certId);
  const mistakes = await DB.getAll('mistakes', certId);
  const s = L.summarize(attempts);
  const subjName = new Map([...cert.subjects.map(x => [x.id, x.name]), ...(cert.exam ? [['all', cert.exam.name]] : [])]);
  const srcName = { 'tabf-official': '官網下載的', 'user-import': '我自己提供的', 'original-ai': '原創題', 'original-human': '原創題' };
  const table = (title, m, name) => h('section', { class: 'card' }, h('h3', { text: title }),
    m.size ? h('table', {}, h('tr', {}, h('th', { text: '' }), h('th', { text: '作答' }), h('th', { text: '答對率' })),
      [...m].map(([k, g]) => h('tr', {}, h('td', { text: (k === undefined || k === null || k === '') ? '未標示' : name(k) }), h('td', { text: String(g.answered) }), h('td', { text: pct(g.rate) }))))
      : h('p', { class: 'muted', text: '還沒有作答紀錄。' }));
  const hist = (await DB.getMeta('examHistory', [])).filter(x => x.cert === certId).slice(0, 10);
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
    h('section', { class: 'card' }, h('h2', { text: `${cert.short} 統計` }),
      h('p', { text: `作答 ${s.answered} 次、答對率 ${s.answered ? pct(s.rate) : '—'}、錯題本 ${mistakes.length} 題` }),
      h('p', { class: 'muted', text: '作答次數含練習與模擬考；同一題做多次會算多次。' })),
    table('依科目', L.groupRate(attempts, byId, x => x.subject), k => subjName.get(k) || k),
    table('依題目來源', L.groupRate(attempts, byId, x => x.source), k => srcName[k] || k),
    h('section', { class: 'card' }, h('h3', { text: '最近的模擬考' }),
      hist.length ? h('table', {}, h('tr', {}, ['日期', '科目', '分數', '結果'].map(t => h('th', { text: t }))),
        hist.map(x => h('tr', {}, h('td', { text: new Date(x.ts).toLocaleDateString('zh-TW') }), h('td', { text: subjName.get(x.subject) || x.subject }),
          h('td', { text: String(x.score) }), h('td', { class: x.passed ? 'ok' : 'ng', text: x.passed ? '及格' : '不及格' }))))
        : h('p', { class: 'muted', text: '還沒有模擬考紀錄。' })));
}

// ---------------------------------------------------------------- 設定：匯入題目
// 這台裝置的紀錄會不會被瀏覽器自動清掉：三種狀態分開寫，狀態不明時不能表現成安全
function persistCard(s) {
  const home = 'iPhone 請把這個網站加到主畫面（Safari 的「分享」→「加入主畫面」），之後都從主畫面打開；加到主畫面後，下次打開會再要求一次。';
  const body = {
    protected: [h('p', { class: 'ok', text: '已受保護' }),
      h('p', { text: '瀏覽器答應不會自動清掉這台裝置上的作答紀錄、錯題與匯入的題目。' }),
      h('p', { class: 'muted', text: '你自己清除瀏覽器資料、或刪掉主畫面上的 App 時，紀錄還是會不見。' })],
    denied: [h('p', { class: 'ng', text: '要求被拒絕' }),
      h('p', { text: '瀏覽器沒有答應保護。這台裝置上的作答紀錄、錯題與匯入的題目可能被自動清掉，而且被清掉時 App 不會知道。' }),
      h('p', { text: home })],
    unsupported: [h('p', { class: 'ng', text: '狀態不明' }),
      h('p', { text: `這個瀏覽器${s.why && s.why.startsWith('查詢') ? '在查詢時出錯' : '不支援查詢這件事'}，App 無法確認紀錄會不會被自動清掉。請不要假設它是安全的。` }),
      h('p', { text: home })],
  }[s.state];
  return h('section', { class: 'card', id: 'persist' }, h('h2', { text: '這台裝置的紀錄' }), ...body);
}

async function settingsView(gen) {
  const m = await loadManifest();
  const knownCerts = m.certs.map(c => c.id);
  const status = h('div', { class: 'status' });
  const counts = [];
  for (const c of m.certs) {
    const u = await DB.getAll('userQuestions', c.id);
    if (u.length) counts.push(h('li', { text: `${c.short}：已匯入 ${u.length} 題（可練 ${u.filter(L.isActive).length} 題）` }));
  }
  const input = h('input', { type: 'file', accept: '.json,application/json' });
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    fill(status, h('p', { text: '讀取中…' }));
    let obj;
    try { obj = JSON.parse(await file.text()); }
    catch { fill(status, h('p', { class: 'ng', text: '這個檔案不是正確的 JSON。' })); return; }
    const r = L.validateImportPack(obj, knownCerts);
    if (!r.ok) {
      fill(status, h('p', { class: 'ng', text: `不能匯入：${r.errors.length} 個問題（整包都沒有匯入）` }),
        h('ul', {}, r.errors.slice(0, 10).map(e => h('li', { text: e }))));
      return;
    }
    const active = r.questions.filter(L.isActive).length;
    const outN = r.questions.filter(x => L.isActive(x) && !L.inScope(x)).length;
    const activeText = outN ? `考試範圍內 ${active - outN} 題，另有不在範圍內的 ${outN} 題` : `可練 ${active} 題`;
    const cert = m.certs.find(c => c.id === r.cert);
    const confirmBtn = h('button', { class: 'btn primary', type: 'button', text: '確定匯入', onclick: async () => {
      confirmBtn.disabled = true;
      const res = await DB.replaceUserQuestions(r.cert, r.questions);
      await DB.setMeta(`points:${r.cert}`, r.points || []);   // 考點清單跟著匯入包走；舊版匯入包沒有考點就清成空的
      fill(status, h('p', { class: 'ok', text: `匯入完成：${cert.short} ${res.added} 題（${activeText}）。原本的 ${res.removed} 題已換成這一份；作答紀錄保留。` }),
        h('a', { class: 'btn', href: '#/', text: '回首頁開始練習' }));
    } });
    fill(status, h('p', { text: `${cert.short}：${r.questions.length} 題，去掉重複後${activeText}。` }),
      h('p', { class: 'muted', text: '匯入會換掉這張證照先前匯入的題目（同一題的作答紀錄會保留）。' }), confirmBtn);
  });
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
    h('section', { class: 'card' }, h('h2', { text: '匯入題目' }),
      h('p', { text: '選擇電腦產生的匯入包（例如 bic-匯入包.json）。題目只存在這支手機的瀏覽器裡，不會上傳到任何地方。' }),
      counts.length ? h('ul', {}, counts) : h('p', { class: 'muted', text: '目前沒有匯入的題目。' }),
      input, status),
    persistCard(await storagePromise),
    h('section', { class: 'card' }, h('h2', { text: '關於' }),
      h('p', { text: '這個網站只有練習功能。作答紀錄、錯題、匯入的題目都只存在你這支手機的瀏覽器裡；網站不收集任何資料。' }),
      h('p', { class: 'muted', text: '換手機或清除瀏覽器資料後，要重新匯入題目。' })));
}

// ---------------------------------------------------------------- 路由
async function route() {
  const gen = ++generation;
  const { path, q } = params();
  try {
    if (path === '/' || path === '') await homeView(gen);
    else if (path === '/setup') await setupView(gen, q);
    else if (path === '/practice') await practiceView(gen, q);
    else if (path === '/exam') await examView(gen, q);
    else if (path === '/stats') await statsView(gen, q);
    else if (path === '/study') await studyView(gen, q);
    else if (path === '/settings') await settingsView(gen);
    else go('#/');
  } catch (e) {
    render(gen, h('section', { class: 'card' }, h('h2', { text: '出了問題' }), h('p', { text: String(e.message || e) }),
      h('a', { class: 'btn', href: '#/', text: '回首頁' })));
  }
}

// 啟動時就向瀏覽器要求持久保存（不會跳出提示；設定頁顯示結果）。資料被自動清掉時 App 偵測不到，所以要讓他看得到狀態。
const storagePromise = L.requestPersistence(navigator.storage);
window.addEventListener('hashchange', route);
route();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
