/* ============================================================
   赛博导师 · 学案 — Service Worker（REQ-20260813-004 任务3）
   版本化缓存：install 预缓存核心静态资源；fetch 策略：
   - 静态资源（同源、非 /api/）：cache-first（离线可开）
   - /api/ 请求：network-only，绝不缓存（本机版 API 不被 SW 干扰）
   ============================================================ */
const CACHE_NAME = 'cyber-mentor-v1.0.0';
const PRECACHE_URLS = [
  './',
  './index.html',
  './marked.min.js',
  './p5.min.js',
  './manifest.json',
  './data/knowledge.json',
  './data/quiz.json',
  './icons/icon.svg',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 同源判定；跨域（Google Fonts 等）不拦截，交给浏览器默认行为
  if (url.origin !== self.location.origin) return;

  // /api/ 请求一律 network-only：本机版（localhost:8899）的动态数据不受 SW 缓存影响
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // 导航请求（页面本身）：network-first，保证本机版/公网版都能看到最新 HTML；
  // 断网时回退到缓存的 index.html（离线可开）
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return resp;
      }).catch(() => caches.match('./index.html').then((r) => r || caches.match('./')))
    );
    return;
  }

  // 静态资源（js/css/图标/数据）：cache-first，命中即返，未命中回网络并写入缓存
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return resp;
      });
    })
  );
});
