// List your Ring cameras (no CAM_ID) or probe one: snapshot + optional 8s live test (--live). Keeps token.json refreshed.
import { RingApi } from 'ring-client-api';
import fs from 'node:fs';
import path from 'node:path';

const DIR = path.dirname(new URL(import.meta.url).pathname);
const TOK = path.join(DIR, 'token.json');
const CAM_ID = Number(process.env.CAM_ID);   // run `npm run cameras` to find yours
const tok = JSON.parse(fs.readFileSync(TOK, 'utf8'));

const api = new RingApi({ refreshToken: tok.refresh_token, ffmpegPath: process.env.FFMPEG || 'ffmpeg', cameraStatusPollingSeconds: 0 });
api.onRefreshTokenUpdated.subscribe(({ newRefreshToken }) => {
  const cur = JSON.parse(fs.readFileSync(TOK, 'utf8'));
  fs.writeFileSync(TOK, JSON.stringify({ ...cur, refresh_token: newRefreshToken }), { mode: 0o600 });
  console.log('token refreshed + saved');
});

const cams = await api.getCameras();
const cam = CAM_ID && cams.find(c => c.id === CAM_ID);
if (!cam) { console.log('camera not found; have:', cams.map(c => `${c.name}:${c.id}`).join(', ')); process.exit(1); }
console.log('camera:', cam.name, cam.model);

try {
  const snap = await cam.getSnapshot();
  fs.writeFileSync(path.join(DIR, 'snap.jpg'), snap);
  console.log('snapshot bytes', snap.length);
} catch (e) { console.log('snapshot failed:', e.message); }

if (process.argv.includes('--live')) {
  const secs = 8, out = path.join(DIR, 'live_test.mp4');
  const t0 = Date.now();
  try {
    await cam.recordToFile(out, secs);
    console.log('live recording', fs.statSync(out).size, 'bytes in', ((Date.now() - t0) / 1000).toFixed(1), 's');
  } catch (e) { console.log('live failed:', e.message); }
}
process.exit(0);
