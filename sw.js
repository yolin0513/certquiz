// Service Worker：讓 App 能離線開、能安裝到主畫面。只處理同一個網站的請求。
// 改了任何外殼檔（html／css／js／圖示）就要升 VERSION；題庫清單 data/manifest.json 一律先上網拿新的。
const VERSION = 'certquiz-v0.6.0';
const SHELL = [
  './', 'index.html', 'manifest.webmanifest', 'css/app.css',
  'js/app.js', 'js/logic.js', 'js/db.js', 'js/data.js',
  'icons/icon-192.png', 'icons/icon-512.png',
];

// 安裝時也把網站附的題庫檔（manifest 裡的 bundledFile）存進快取：第一次開 App 時 SW 還沒接手，
// 頁面讀的題庫不會經過 SW，不先存的話第一次離線就沒有題目。讀不到清單時不擋安裝（之後上網會再存）。
async function cacheBundled(c) {
  try {
    const r = await fetch('data/manifest.json', { cache: 'no-cache' });
    if (!r.ok) return;
    await c.put('data/manifest.json', r.clone());
    const m = await r.json();
    await Promise.all(m.certs.filter(x => x.bundledFile).map(x => c.add(x.bundledFile)));
  } catch { /* 離線安裝：略過，題庫走「先上網、失敗用快取」 */ }
}

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL).then(() => cacheBundled(c))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('/data/manifest.json') || url.pathname.includes('/data/q/')) {
    // 題庫：先上網，失敗才用快取（離線時仍可練已載入過的題）
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone();
      if (r.ok) caches.open(VERSION).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  // 外殼：快取優先
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(hit => hit || fetch(e.request)));
});
