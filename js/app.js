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

function render(gen, ...nodes) {
  if (gen !== generation) return false;
  view.replaceChildren(...nodes);
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
    const { questions } = await loadPool(c.id);
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
          h('a', { class: 'btn primary', href: `#/setup?cert=${c.id}`, text: '開始練習' }),
          h('a', { class: 'btn', href: `#/practice?cert=${c.id}&mode=mistakes&count=20`, 'aria-disabled': mistakes.length ? null : 'true', text: `錯題複習（${mistakes.length}）` })));
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
      count: Number(q.get('count')) || 10, order: q.get('order') || 'unseen' }, prog);
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
      feedback.replaceChildren(h('p', { class: correct ? 'ok' : 'ng', text: correct ? '答對了' : `答錯了，正解是 (${item.answer})` }),
        h('p', { class: 'src', text: L.sourceLabel(item) }),
        item.explain ? h('p', { class: 'explain', text: item.explain }) : null);
      feedback.hidden = false;
      next.hidden = false;
      results.push({ item, k, correct });
      const prev = await DB.get('mistakes', item.id);
      await DB.recordAnswer({ q: item, chosen: k, correct, mode, mistakeState: L.nextMistakeState(prev, correct, mode, Date.now()) });
    }

    render(gen,
      h('div', { class: 'bar' }, h('a', { class: 'back', href: '#/', text: '← 結束' }), h('span', { text: `${i + 1} / ${picked.length}` })),
      h('section', { class: 'card q' }, h('p', { class: 'stem', text: item.stem }), h('div', { class: 'opts' }, opts), feedback, next));
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
          h('p', { class: 'src', text: L.sourceLabel(r.item) })))),
        h('div', { class: 'row' }, h('a', { class: 'btn primary', href: `#/setup?cert=${certId}`, text: '再練一輪' }),
          h('a', { class: 'btn', href: '#/', text: '回首頁' }))));
  };

  showQuestion();
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
    status.replaceChildren(h('p', { text: '讀取中…' }));
    let obj;
    try { obj = JSON.parse(await file.text()); }
    catch { status.replaceChildren(h('p', { class: 'ng', text: '這個檔案不是正確的 JSON。' })); return; }
    const r = L.validateImportPack(obj, knownCerts);
    if (!r.ok) {
      status.replaceChildren(h('p', { class: 'ng', text: `不能匯入：${r.errors.length} 個問題（整包都沒有匯入）` }),
        h('ul', {}, r.errors.slice(0, 10).map(e => h('li', { text: e }))));
      return;
    }
    const active = r.questions.filter(L.isActive).length;
    const cert = m.certs.find(c => c.id === r.cert);
    const confirmBtn = h('button', { class: 'btn primary', type: 'button', text: '確定匯入', onclick: async () => {
      confirmBtn.disabled = true;
      const res = await DB.replaceUserQuestions(r.cert, r.questions);
      status.replaceChildren(h('p', { class: 'ok', text: `匯入完成：${cert.short} ${res.added} 題（可練 ${active} 題）。原本的 ${res.removed} 題已換成這一份；作答紀錄保留。` }),
        h('a', { class: 'btn', href: '#/', text: '回首頁開始練習' }));
    } });
    status.replaceChildren(h('p', { text: `${cert.short}：${r.questions.length} 題，去掉重複後可練 ${active} 題。` }),
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
