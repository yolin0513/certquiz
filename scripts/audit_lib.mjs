// 對比與預設樣式的逐元素檢查（App 的瀏覽器測試與本機 HTML 檢查共用同一套，免得各寫一份、越改越不一樣；2026-10-12 抽出）
// AUDIT(scope)：scope 是要量的範圍（App 是 '#view'，獨立 HTML 是 'body'）；母體一律從整個 body 數。
export const AUDIT = (scope = '#view') => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = x => { x /= 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = el => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 };   // 畫布預設白（body 有自己的背景，正常走不到這裡）
    for (const c of layers.reverse()) acc = over(c, acc);
    return acc;
  };
  const root = getComputedStyle(document.documentElement);
  const probe = document.createElement('span'); document.body.appendChild(probe);
  const tokens = ['--fg', '--muted', '--pri', '--pri-fg', '--ok', '--ng'].map(v => { probe.style.color = root.getPropertyValue(v).trim(); return getComputedStyle(probe).color; });
  probe.remove();
  for (const d of document.querySelectorAll('details')) d.open = true;
  const out = { n: 0, exempt: 0, fails: [], minRatio: 99, minAt: '', untoken: [], visitedRules: [], pop: {}, population: 0, missed: [] };
  const measured = new Set();
  const tag = el => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  for (const el of document.querySelectorAll(scope + ' *')) {
    if (!el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible') continue;
    if (/^(A|BUTTON|SELECT|INPUT|SUMMARY)$/.test(el.tagName)) {
      out.pop[tag(el)] = (out.pop[tag(el)] || 0) + 1;
      if (!tokens.includes(cs.color)) out.untoken.push(`${tag(el)}「${el.textContent.trim().slice(0, 12)}」${cs.color}`);
    }
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.data.trim()) || el.tagName === 'SELECT';
    if (!own) continue;
    let op = 1; for (let e = el; e; e = e.parentElement) op *= Number(getComputedStyle(e).opacity);
    if (el.closest('[aria-disabled="true"], :disabled')) { out.exempt++; measured.add(el); continue; }
    out.n++;
    measured.add(el);
    const fg = parse(cs.color), bg = bgOf(el);
    const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
    const r = op < 1 ? 0 : ratio(fg.a < 1 ? over(fg, bg) : fg, bg);
    if (r < out.minRatio) { out.minRatio = r; out.minAt = `${tag(el)}「${el.textContent.trim().slice(0, 12)}」`; }
    if (r < need) out.fails.push(`${tag(el)}「${el.textContent.trim().slice(0, 14)}」${op < 1 ? '半透明' : r.toFixed(2) + ':1 < ' + need}`);
  }
  // 母體：跟上面的選法無關，另外從整個 body 走每個文字節點，畫面上看得到的就算一個「文字元素」（加上 select）。
  // 量到的（算了對比的＋豁免的）必須剛好等於母體；選擇器少抓到一塊區域時，這裡會點名漏掉的元素。
  const popSet = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = tw.nextNode(); t; t = tw.nextNode()) {
    const p = t.parentElement;
    if (!t.data.trim() || !p || /^(SCRIPT|STYLE|NOSCRIPT|OPTION)$/.test(p.tagName)) continue;
    if (!p.getClientRects().length || getComputedStyle(p).visibility !== 'visible') continue;
    popSet.add(p);
  }
  for (const sel of document.querySelectorAll('select')) if (sel.getClientRects().length) popSet.add(sel);
  out.population = popSet.size;
  for (const e of popSet) if (!measured.has(e)) out.missed.push(`${tag(e)}「${e.textContent.trim().slice(0, 12)}」`);
  for (const e of measured) if (!popSet.has(e)) out.missed.push(`（量到但不在母體）${tag(e)}`);
  for (const sh of document.styleSheets) for (const rule of sh.cssRules || []) if ((rule.selectorText || '').includes(':visited')) out.visitedRules.push(rule.selectorText);
  return out;
};
// 驗尺：同一套公式對已知值——#767676／白 4.54（剛好過）、#777777／白 4.48（剛好不過）、黑／白 21
export const AUDIT_RULER = () => {
  const lum = h => { const f = x => { x /= 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; const v = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)); return 0.2126 * f(v[0]) + 0.7152 * f(v[1]) + 0.0722 * f(v[2]); };
  const r = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  return [r('#767676', '#ffffff'), r('#777777', '#ffffff'), r('#000000', '#ffffff')];
};
