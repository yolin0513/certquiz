// 題庫載入：只讀同一個網站的檔案（data/manifest.json、data/q/<證照>.json），加上本機匯入的題目。
import { getAll } from './db.js';

let manifestP = null;

export function loadManifest() {
  if (!manifestP) {
    manifestP = fetch('data/manifest.json', { cache: 'no-cache' }).then(r => {
      if (!r.ok) throw new Error(`讀不到題庫清單（HTTP ${r.status}）`);
      return r.json();
    }).catch(e => { manifestP = null; throw e; });
  }
  return manifestP;
}

const bundled = new Map();

async function loadBundled(cert) {
  if (!cert.bundledFile) return [];
  if (!bundled.has(cert.id)) {
    bundled.set(cert.id, fetch(cert.bundledFile).then(r => {
      if (!r.ok) throw new Error(`讀不到 ${cert.short} 的題庫（HTTP ${r.status}）`);
      return r.json();
    }).then(j => j.questions).catch(e => { bundled.delete(cert.id); throw e; }));
  }
  return bundled.get(cert.id);
}

/** 這張證照全部的題目：網站附的＋使用者匯入的（同 id 時以匯入的為準） */
export async function loadPool(certId) {
  const m = await loadManifest();
  const cert = m.certs.find(c => c.id === certId);
  if (!cert) throw new Error(`不認得的證照：${certId}`);
  const [b, u] = await Promise.all([loadBundled(cert), getAll('userQuestions', certId)]);
  const byId = new Map(b.map(q => [q.id, q]));
  for (const q of u) byId.set(q.id, q);
  return { cert, questions: [...byId.values()] };
}
