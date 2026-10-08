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
        h('p', { class: 'stat' }, `可練 ${active.length} 題`, questions.length !== active.length ? `（另有重複題 ${questions.length - active.length} 題已隱藏）` : ''),
        h('p', { class: 'stat' }, `已作答 ${s.answered} 次，答對率 ${s.answered ? pct(s.rate) : '—'}，錯題 ${mistakes.length} 題`),
        h('div', { class: 'row' },
          c.syllabus ? h('a', { class: 'btn primary', href: `#/study?cert=${c.id}`, text: '讀書（依官方大綱）' }) : null,
          h('a', { class: c.syllabus ? 'btn' : 'btn primary', href: `#/setup?cert=${c.id}`, text: '開始練習' }),
          h('a', { class: 'btn', href: `#/practice?cert=${c.id}&mode=mistakes&count=20`, 'aria-disabled': mistakes.length ? null : 'true', text: `錯題複習（${mistakes.length}）` })),
        h('div', { class: 'row' },
          c.subjects.filter(s => s.exam).map(s => h('a', { class: 'btn', href: `#/exam?cert=${c.id}&subject=${s.id}`,
            text: `模擬考：${s.name.replace(/^銀行內部控制與內部稽核/, '') || s.name}` })),
          h('a', { class: 'btn', href: `#/stats?cert=${c.id}`, text: '統計' })));
    }
    cards.push(h('section', { class: 'card' }, h('h2', { text: c.name }), h('p', { class: 'notice', text: c.notice }), ...body));
  }
  render(gen, h('h1', { text: '證照題庫練習' }), ...cards);
}

// ---------------------------------------------------------------- 練習設定
async function setupView(gen, q) {
  const certId = q.get('cert');
  const { cert } = await loadPool(certId);
  const subjects = [{ id: 'all', name: '全部科目' }, ...cert.subjects];
  const form = h('form', { class: 'card', onsubmit: e => {
    e.preventDefault();
    const f = new FormData(e.target);
    go(`#/practice?cert=${certId}&mode=practice&subject=${f.get('subject')}&source=${f.get('source')}&count=${f.get('count')}&order=${f.get('order')}`);
  } },
  h('h2', { text: cert.short }),
  h('label', { text: '科目' }), h('select', { name: 'subject' }, subjects.map(s => h('option', { value: s.id, text: s.name }))),
  cert.questionSource === 'import' ? [h('label', { text: '來源' }), h('select', { name: 'source' },
    h('option', { value: 'all', text: '全部' }), h('option', { value: 'official', text: '只出從官網下載的' }),
    h('option', { value: 'user', text: '只出我自己提供的' }))] : h('input', { type: 'hidden', name: 'source', value: 'all' }),
  h('label', { text: '題數' }), h('select', { name: 'count' }, [10, 20, 50].map(n => h('option', { value: n, text: `${n} 題` }))),
  h('label', { text: '出題順序' }), h('select', { name: 'order' },
    h('option', { value: 'unseen', text: '沒做過的優先' }), h('option', { value: 'random', text: '完全隨機' })),
  h('button', { class: 'btn primary', type: 'submit', text: '開始' }));
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }), form);
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
      objective: q.get('objective') || '', skill: q.get('skill') || '' }, prog);
  }
  if (!picked.length) {
    render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
      h('section', { class: 'card' }, h('p', { text: mode === 'mistakes' ? '錯題本是空的。' : '這個條件下沒有題目。' })));
    return;
  }
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
        item.basis ? h('p', { class: 'src basis', text: L.basisText(item) }) : null);
      feedback.hidden = false;
      next.hidden = false;
      results.push({ item, k, correct });
      const prev = await DB.get('mistakes', item.id);
      await DB.recordAnswer({ q: item, chosen: k, correct, mode, mistakeState: L.nextMistakeState(prev, correct, mode, Date.now()) });
    }

    render(gen,
      h('div', { class: 'bar' }, h('a', { class: 'back', href: '#/', text: '← 結束' }), h('span', { text: `${i + 1} / ${picked.length}` })),
      h('section', { class: 'card q' },
        item.source && item.source.startsWith('original') ? h('p', { class: 'src', text: L.sourceLabel(item) }) : null,
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
  const subject = cert.subjects.find(s => s.id === subjectId);
  if (!subject || !subject.exam) { render(gen, h('p', { text: '這個科目沒有模擬考設定。' })); return; }
  const ex = subject.exam;
  const built = L.buildExam(questions, subjectId, ex.count, Date.now());
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
        await DB.recordAnswer({ q: item, chosen: k, correct: k === item.answer, mode: 'exam',
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
// 先讀再練：依官方大綱（節次 → 細項）列出題目、正解、解析與依據，不必作答。
async function studyView(gen, q) {
  const certId = q.get('cert');
  const { cert, questions } = await loadPool(certId);
  const back = h('a', { class: 'back', href: '#/', text: '← 回首頁' });
  if (!cert.syllabus) {
    render(gen, back, h('section', { class: 'card' }, h('p', { text: '這張證照的讀書模式還在準備中。' })));
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
    render(gen, back,
      h('section', { class: 'card' }, h('h2', { text: `${cert.short} 讀書：依官方大綱` }),
        h('p', { class: 'muted', text: `${cert.syllabus.version}。細項名稱是官方原文；點進去可以看題目、正解、解析與依據，看完再練那一節。` })),
      domains.map(d => h('section', { class: 'card' }, h('h3', { text: d }),
        g.objectives.filter(o => o.domain === d).map(o => h('div', { class: 'study-obj' },
          h('p', { class: 'stat' }, h('b', { text: `${o.id} ${o.name}` }), `（${o.count} 題）`),
          h('ol', { class: 'study-skills' }, o.skills.map(k => h('li', {},
            k.questions.length
              ? h('a', { href: `#/study?cert=${certId}&objective=${o.id}&skill=${k.n}`, text: `${k.name}（${k.questions.length} 題）` })
              : h('span', { class: 'muted', text: k.name })))))))),
      g.other.length ? h('section', { class: 'card' }, h('p', { class: 'ng', text: `有 ${g.other.length} 題對不到大綱節次，請回報。` })) : null);
    return;
  }

  // 一個細項：逐題列出
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

// ---------------------------------------------------------------- 統計
async function statsView(gen, q) {
  const certId = q.get('cert');
  const { cert, questions } = await loadPool(certId);
  const byId = new Map(questions.map(x => [x.id, x]));
  const attempts = await DB.getAll('attempts', certId);
  const mistakes = await DB.getAll('mistakes', certId);
  const s = L.summarize(attempts);
  const subjName = new Map(cert.subjects.map(x => [x.id, x.name]));
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
    const cert = m.certs.find(c => c.id === r.cert);
    const confirmBtn = h('button', { class: 'btn primary', type: 'button', text: '確定匯入', onclick: async () => {
      confirmBtn.disabled = true;
      const res = await DB.replaceUserQuestions(r.cert, r.questions);
      fill(status, h('p', { class: 'ok', text: `匯入完成：${cert.short} ${res.added} 題（可練 ${active} 題）。原本的 ${res.removed} 題已換成這一份；作答紀錄保留。` }),
        h('a', { class: 'btn', href: '#/', text: '回首頁開始練習' }));
    } });
    fill(status, h('p', { text: `${cert.short}：${r.questions.length} 題，去掉重複後可練 ${active} 題。` }),
      h('p', { class: 'muted', text: '匯入會換掉這張證照先前匯入的題目（同一題的作答紀錄會保留）。' }), confirmBtn);
  });
  render(gen, h('a', { class: 'back', href: '#/', text: '← 回首頁' }),
    h('section', { class: 'card' }, h('h2', { text: '匯入題目' }),
      h('p', { text: '選擇電腦產生的匯入包（例如 bic-匯入包.json）。題目只存在這支手機的瀏覽器裡，不會上傳到任何地方。' }),
      counts.length ? h('ul', {}, counts) : h('p', { class: 'muted', text: '目前沒有匯入的題目。' }),
      input, status),
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

window.addEventListener('hashchange', route);
route();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
