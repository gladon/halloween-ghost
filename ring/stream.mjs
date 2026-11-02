// Keep a live Ring stream running and write the newest frame to frames/latest.jpg (~6 fps).
// Restarts automatically when Ring ends the live session. Ctrl-C / SIGTERM to stop.
import { RingApi } from 'ring-client-api';
import { useLogger } from 'ring-client-api/util';
if (process.env.DEBUG) useLogger({ logInfo: (...a) => console.log('[ring]', ...a), logError: (...a) => console.log('[ring ERR]', ...a) });
import fs from 'node:fs';
import path from 'node:path';

const DIR = path.dirname(new URL(import.meta.url).pathname);
const TOK = path.join(DIR, 'token.json');
const OUT_DIR = path.join(DIR, 'frames');
const OUT = path.join(OUT_DIR, 'latest.jpg');
const CAM_ID = Number(process.env.CAM_ID);   // run `npm run cameras` to find yours
const FPS = Number(process.env.FPS || 6);
fs.mkdirSync(OUT_DIR, { recursive: true });

if (!CAM_ID) { console.error('Set CAM_ID (see `npm run cameras`)'); process.exit(1); }
const tok = JSON.parse(fs.readFileSync(TOK, 'utf8'));
const api = new RingApi({ refreshToken: tok.refresh_token, ffmpegPath: process.env.FFMPEG || 'ffmpeg', cameraStatusPollingSeconds: 0, debug: !!process.env.DEBUG });
api.onRefreshTokenUpdated.subscribe(({ newRefreshToken }) => {
  const cur = JSON.parse(fs.readFileSync(TOK, 'utf8'));
  fs.writeFileSync(TOK, JSON.stringify({ ...cur, refresh_token: newRefreshToken }), { mode: 0o600 });
});

const cam = (await api.getCameras()).find(c => c.id === CAM_ID);
if (!cam) { console.error('camera not found'); process.exit(1); }
const log = (...a) => console.log(new Date().toLocaleTimeString(), ...a);
log('camera:', cam.name);

let call = null, stopping = false, startedAt = 0, quickFails = 0;
async function start() {
  if (stopping) return;
  try {
    log('starting live stream…');
    startedAt = Date.now();
    call = await cam.streamVideo({
      // library defaults to '-vcodec copy', which can't take a filter, so ffmpeg exited instantly; set codec explicitly
      audio: ['-an'],
      video: ['-vf', `fps=${FPS}`, '-vcodec', 'mjpeg', '-q:v', '3'],
      output: ['-y', '-f', 'image2', '-update', '1', '-atomic_writing', '1', OUT],
    });
    log('live');
    call.onCallEnded.subscribe(() => {
      const lived = (Date.now() - startedAt) / 1000; call = null;
      // Ring refuses a new live session right after the last one; quick deaths mean "back off", not "retry fast"
      quickFails = lived < 12 ? quickFails + 1 : 0;
      const wait = quickFails ? Math.min(60, 15 * quickFails) : 1.5;
      log(`stream ended after ${lived.toFixed(0)}s; restarting in ${wait}s`);
      if (!stopping) setTimeout(start, wait * 1000);
    });
  } catch (e) {
    log('stream failed:', e.message); call = null;
    if (!stopping) setTimeout(start, 5000);
  }
}
// watchdog: if no new frame for 15s, restart the call
setInterval(() => {
  if (stopping || !call) return;
  let age = Infinity; try { age = (Date.now() - fs.statSync(OUT).mtimeMs) / 1000; } catch {}
  if (age > 15 && Date.now() - startedAt > 20000) { log(`no frames for ${age.toFixed(0)}s, restarting`); try { call.stop(); } catch {} }
}, 5000);

const shutdown = () => { stopping = true; log('stopping'); try { call && call.stop(); } catch {} setTimeout(() => process.exit(0), 800); };
process.on('SIGINT', shutdown); process.on('SIGTERM', shutdown);
await start();
