// Ghost trigger server. Serves the ghost page + sound clips and pushes events to it.
//   GET /            -> ghost (index.html)
//   GET /events      -> SSE stream the page listens to
//   GET /greet?side=left|right   -> someone arrived: ghost pops up and invites a wave
//   GET /wave?side=left|right    -> someone waved: random reaction
//   GET /react?kind=twirl|boo|sneeze|hat|triplets|bat|hiccup|candy|loop|golden  -> specific reaction (testing)
//   GET /mirror?on=1|0  GET /sound?on=1|0  GET /health
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const PORT = Number(process.env.PORT || 8787);
const DIR = path.dirname(new URL(import.meta.url).pathname);
const CD = { wave: 3000, greet: 8000 };
const clients = new Set();
const last = { wave: 0, greet: 0 }, count = { wave: 0, greet: 0, react: 0 };

const send = msg => { const s = `data: ${JSON.stringify(msg)}\n\n`; for (const c of clients) c.write(s); };
setInterval(() => { for (const c of clients) c.write(': ping\n\n'); }, 15000);
const json = (res, code, o) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)); };
const sideOf = q => q === 'left' || q === '-1' ? -1 : q === 'right' || q === '1' ? 1 : undefined;
const log = (...a) => console.log(new Date().toLocaleTimeString(), ...a);

http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), q = k => u.searchParams.get(k);
  const page = { '/': 'index.html', '/index.html': 'index.html' }[u.pathname];
  if (page) { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }); return fs.createReadStream(path.join(DIR, page)).pipe(res); }
  const m = u.pathname.match(/^\/sfx\/([a-z0-9]+)\.mp3$/);
  if (m) { const f = path.join(DIR, 'sfx', m[1] + '.mp3'); if (!fs.existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': 'audio/mpeg', 'cache-control': 'no-cache' }); return fs.createReadStream(f).pipe(res); }
  if (u.pathname === '/events') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
    res.write(': hi\n\n'); clients.add(res); req.on('close', () => clients.delete(res)); return;
  }
  if (u.pathname === '/wave' || u.pathname === '/greet') {
    const type = u.pathname.slice(1), now = Date.now();
    if (now - last[type] < CD[type]) return json(res, 429, { ok: false, reason: 'cooldown', retryInMs: CD[type] - (now - last[type]) });
    last[type] = now; count[type]++; send({ type, side: sideOf(q('side')) });
    log(type, q('side') || 'auto', `→ ${clients.size} screen(s)`); return json(res, 200, { ok: true, screens: clients.size, ...count });
  }
  if (u.pathname === '/react') { count.react++; send({ type: 'react', kind: q('kind') || undefined, side: sideOf(q('side')) }); log('react', q('kind') || 'random'); return json(res, 200, { ok: true, screens: clients.size }); }
  if (u.pathname === '/reload') { send({ type: 'reload' }); return json(res, 200, { ok: true, screens: clients.size }); }
  if (u.pathname === '/mirror' || u.pathname === '/sound') { send({ type: u.pathname.slice(1), on: q('on') !== '0' }); return json(res, 200, { ok: true }); }
  if (u.pathname === '/health') return json(res, 200, { ok: true, screens: clients.size, ...count, last });
  res.writeHead(404); res.end('not found');
}).listen(PORT, '127.0.0.1', () => log(`ghost server on http://127.0.0.1:${PORT}`));
