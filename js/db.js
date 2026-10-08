// 本機資料庫（IndexedDB）。所有作答紀錄、錯題、匯入的題目都只存在這支手機的瀏覽器裡，
// 沒有任何上傳（docs/STATUS.md 常設規則 12；scripts/check_privacy.py 靜態擋上傳類程式碼）。

const DB_NAME = 'certquiz';
const DB_VERSION = 1;
const STORES = {
  userQuestions: { keyPath: 'id', indexes: [['cert', 'cert']] },      // 使用者匯入的題目
  attempts: { keyPath: 'n', autoIncrement: true, indexes: [['cert', 'cert'], ['qid', 'qid']] }, // 每一次作答
  progress: { keyPath: 'qid', indexes: [['cert', 'cert']] },          // 每題彙總
  mistakes: { keyPath: 'qid', indexes: [['cert', 'cert']] },          // 錯題本
  meta: { keyPath: 'k' },                                             // 設定
};

let dbPromise = null;

export function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const [name, def] of Object.entries(STORES)) {
        if (db.objectStoreNames.contains(name)) continue;
        const s = db.createObjectStore(name, { keyPath: def.keyPath, autoIncrement: !!def.autoIncrement });
        for (const [iname, key] of def.indexes || []) s.createIndex(iname, key);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function done(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('交易中止'));
  });
}

function reqP(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function getAll(store, cert) {
  const db = await openDB();
  const tx = db.transaction(store, 'readonly');
  const s = tx.objectStore(store);
  return reqP(cert && s.indexNames.contains('cert') ? s.index('cert').getAll(cert) : s.getAll());
}

export async function get(store, key) {
  const db = await openDB();
  return reqP(db.transaction(store, 'readonly').objectStore(store).get(key));
}

export async function put(store, value) {
  const db = await openDB();
  const tx = db.transaction(store, 'readwrite');
  tx.objectStore(store).put(value);
  return done(tx);
}

export async function del(store, key) {
  const db = await openDB();
  const tx = db.transaction(store, 'readwrite');
  tx.objectStore(store).delete(key);
  return done(tx);
}

/** 匯入題目：同一筆交易裡先刪掉這張證照舊的匯入題，再寫入新的（同 id 覆蓋；整包成功或整包不動） */
// 注意：交易進行中不 await（舊版 Safari 會在 await 之間自動提交交易，整包成功或整包不動就破功），一律在 callback 裡接續。
export async function replaceUserQuestions(cert, questions) {
  const db = await openDB();
  const tx = db.transaction('userQuestions', 'readwrite');
  const s = tx.objectStore('userQuestions');
  let removed = 0;
  const keysReq = s.index('cert').getAllKeys(cert);
  keysReq.onsuccess = () => {
    removed = keysReq.result.length;
    for (const k of keysReq.result) s.delete(k);
    for (const q of questions) s.put(q);
  };
  await done(tx);
  return { removed, added: questions.length };
}

/** 一次作答：寫 attempts、更新 progress 與 mistakes，三個 store 同一筆交易 */
export async function recordAnswer({ q, chosen, correct, mode, mistakeState }) {
  const db = await openDB();
  const tx = db.transaction(['attempts', 'progress', 'mistakes'], 'readwrite');
  const now = Date.now();
  tx.objectStore('attempts').add({ cert: q.cert, qid: q.id, chosen, correct, mode, ts: now });
  const ps = tx.objectStore('progress');
  const prevReq = ps.get(q.id);
  prevReq.onsuccess = () => {
    const prev = prevReq.result;
    ps.put({ qid: q.id, cert: q.cert, seen: (prev?.seen || 0) + 1, correct: (prev?.correct || 0) + (correct ? 1 : 0), last: correct, ts: now });
  };
  const ms = tx.objectStore('mistakes');
  if (mistakeState) ms.put({ qid: q.id, cert: q.cert, ...mistakeState });
  else ms.delete(q.id);
  return done(tx);
}

export async function getMeta(k, fallback = null) {
  const r = await get('meta', k);
  return r ? r.v : fallback;
}

export async function setMeta(k, v) {
  return put('meta', { k, v });
}
