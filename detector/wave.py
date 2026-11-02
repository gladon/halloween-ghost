"""Wave detector: watches Ring frames, finds people with a pose model, and pokes the ghost when someone waves.

Live:   .venv/bin/python wave.py                      (reads ../ring/frames/latest.jpg)
Test:   .venv/bin/python wave.py --video clip.mp4     (no ghost calls unless --fire)

A "wave" = a wrist held above its shoulder for ~0.7s that also swings side to side,
or a hand held up for ~1.2s (small/far people often show little swing at this camera angle).
"""
import argparse, collections, json, os, time, urllib.request
from pathlib import Path
import cv2
from ultralytics import YOLO

HERE = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument('--frame', default=str(HERE.parent / 'ring/frames/latest.jpg'))
ap.add_argument('--video')
ap.add_argument('--fire', action='store_true', help='call the ghost in --video mode too')
ap.add_argument('--model', default='yolo11s-pose.pt')
ap.add_argument('--imgsz', type=int, default=1280)
ap.add_argument('--device', default=os.environ.get('DEVICE', 'mps'), help='mps (Apple Silicon), cuda, or cpu')
ap.add_argument('--ghost', default='http://127.0.0.1:8787')
ap.add_argument('--fps', type=float, default=6)
ap.add_argument('--flip-side', action='store_true', help='swap left/right sent to the ghost')
ap.add_argument('--hold', type=float, default=1.2, help='seconds of raised hand that count as a wave without swing')
args = ap.parse_args()

model = YOLO(str(HERE / args.model) if (HERE / args.model).exists() else args.model)
HITS = HERE / 'hits'; HITS.mkdir(exist_ok=True)
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 5, 6, 7, 8, 9, 10
KC = 0.3            # keypoint confidence floor
WINDOW = 2.0        # seconds of history per person
TRACK_COOLDOWN = 8.0
GREET_AFTER = 0.8      # a new person must be tracked this long before the ghost says hi
RESIDENT_AFTER = 75.0  # someone in view this long (the candy-giver) no longer greets or triggers reactions
first_seen, greeted = {}, set()
MIN_PERSON_CONF = 0.35   # phantom on the parked SUV scored 0.27-0.31; real people 0.45+
# Pixel boxes (x0, y0, x1, y1) in the camera frame to ignore: things the pose model keeps mistaking for a person
# (ours was a parked SUV at the far-left edge). Start empty; add one if you see a phantom in detector/hits/.
# e.g. IGNORE_BOXES='0,200,220,530'  (several: separate with ';')
IGNORE_BOXES = [tuple(int(v) for v in b.split(',')) for b in os.environ.get('IGNORE_BOXES', '').split(';') if b.strip()]
def ignored(box):
    x0, y0, x1, y1 = box
    for a0, b0, a1, b1 in IGNORE_BOXES:
        iw = max(0, min(x1, a1) - max(x0, a0)); ih = max(0, min(y1, b1) - max(y0, b0))
        if iw * ih > 0.6 * (x1 - x0) * (y1 - y0): return True
    return False

hist = collections.defaultdict(lambda: collections.deque())   # track id -> (t, raised, swing_x, cx)
last_fire = {}

def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)

def fire(side, kind='wave'):
    s = 'left' if side < 0 else 'right'
    try:
        with urllib.request.urlopen(f'{args.ghost}/{kind}?side={s}', timeout=2) as r: return r.status, r.read().decode()[:80]
    except urllib.error.HTTPError as e: return e.code, 'cooldown' if e.code == 429 else e.read().decode()[:80]
    except Exception as e: return 0, str(e)[:80]

def arm_state(k, c, sh, el, wr, scale):
    """raised?, wrist x relative to elbow (normalized) or None"""
    if c[wr] < KC or c[sh] < KC: return False, None
    raised = k[wr][1] < k[sh][1] - 0.05 * scale
    ref = k[el][0] if c[el] >= KC else k[sh][0]
    return raised, (k[wr][0] - ref) / scale

def reversals(xs, amp):
    """count direction changes bigger than amp (hysteresis)"""
    if len(xs) < 3: return 0
    n, d, ext = 0, 0, xs[0]
    for x in xs[1:]:
        if d >= 0 and x < ext - amp: n += (d > 0); d, ext = -1, x
        elif d <= 0 and x > ext + amp: n += (d < 0); d, ext = 1, x
        elif (d > 0 and x > ext) or (d < 0 and x < ext): ext = x
        elif d == 0: ext = x if abs(x - xs[0]) < amp else ext
    return n

def process(frame, now):
    H, W = frame.shape[:2]
    res = model.track(frame, persist=True, imgsz=args.imgsz, conf=0.25, verbose=False, tracker='bytetrack.yaml', device=args.device)[0]
    people, fired, greet = 0, None, None
    if res.keypoints is None or res.boxes is None or res.boxes.id is None: return people, fired, greet, res
    ids = res.boxes.id.int().tolist(); boxes = res.boxes.xyxy.tolist(); pconf = res.boxes.conf.tolist()
    kps = res.keypoints.xy.tolist(); confs = res.keypoints.conf.tolist() if res.keypoints.conf is not None else None
    for tid, box, pc, k, c in zip(ids, boxes, pconf, kps, confs or [[1] * 17] * len(ids)):
        if pc < MIN_PERSON_CONF or ignored(box): continue
        people += 1
        fs = first_seen.setdefault(tid, now); age = now - fs
        if age > RESIDENT_AFTER: continue
        x0, y0, x1, y1 = box;
        if tid not in greeted and age >= GREET_AFTER:
            greeted.add(tid); greet = dict(id=tid, side=1 if (x0 + x1) / 2 < W / 2 else -1)
            if args.flip_side: greet['side'] = -greet['side']
        x0, y0, x1, y1 = box; scale = max(20.0, (y1 - y0) * 0.35)   # ~shoulder-to-hip size
        best_raised, best_x = False, None
        for sh, el, wr in ((L_SH, L_EL, L_WR), (R_SH, R_EL, R_WR)):
            r, x = arm_state(k, c, sh, el, wr, scale)
            if r and not best_raised: best_raised, best_x = True, x
        h = hist[tid]; h.append((now, best_raised, best_x, (x0 + x1) / 2))
        while h and now - h[0][0] > WINDOW: h.popleft()
        up = [e for e in h if e[1]]
        if len(up) < max(3, int(0.7 * args.fps * 0.8)): continue
        # longest continuous raised run (seconds)
        run, best_run, prev = 0.0, 0.0, None
        for e in h:
            if e[1]: run = run + (e[0] - prev if prev is not None else 0); best_run = max(best_run, run)
            else: run = 0.0
            prev = e[0] if e[1] else None
        swings = reversals([e[2] for e in up if e[2] is not None], 0.12)
        if (swings >= 2 or best_run >= args.hold) and now - last_fire.get(tid, -99) > TRACK_COOLDOWN:
            last_fire[tid] = now
            cx = (x0 + x1) / 2
            # camera looks out from the house: camera-left is the street-viewer's right
            side = 1 if cx < W / 2 else -1
            if args.flip_side: side = -side
            fired = dict(id=tid, side=side, swings=swings, held=round(best_run, 2), box=[int(v) for v in box])
    for tid in [k for k, v in first_seen.items() if now - v > 600]: first_seen.pop(tid, None); greeted.discard(tid); hist.pop(tid, None)
    return people, fired, greet, res

def save_hit(res, info):
    img = res.plot(boxes=True, labels=False)
    p = HITS / f"hit_{time.strftime('%H%M%S')}_{info['id']}.jpg"; cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    for old in sorted(HITS.glob('hit_*.jpg'))[:-int(os.environ.get('KEEP_HITS', 30))]: old.unlink()   # these are photos of visitors; keep few
    return p

def run_video():
    cap = cv2.VideoCapture(args.video); src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(src_fps / args.fps)); i = 0; t0 = time.time(); n = 0
    while True:
        ok, frame = cap.read()
        if not ok: break
        if i % step == 0:
            now = i / src_fps; ppl, hit, gr, res = process(frame, now); n += 1
            if gr: log(f'GREET at {now:.1f}s', gr)
            if hit:
                log(f'WAVE at {now:.1f}s', hit, '->', save_hit(res, hit).name, fire(hit['side']) if args.fire else '(dry run)')
        i += 1
    log(f'done: {n} frames in {time.time() - t0:.1f}s ({n / max(.01, time.time() - t0):.1f} fps)')

def run_live():
    log('watching', args.frame)
    last_m, last_report, frames, max_people, stale_warned = 0, time.time(), 0, 0, False
    while True:
        try: m = os.stat(args.frame).st_mtime
        except FileNotFoundError: time.sleep(.5); continue
        if m == last_m:
            if time.time() - m > 10 and not stale_warned: log('no new camera frames (stream down?)'); stale_warned = True
            time.sleep(.03); continue
        last_m, stale_warned = m, False
        frame = cv2.imread(args.frame)
        if frame is None: continue
        ppl, hit, gr, res = process(frame, time.time()); frames += 1; max_people = max(max_people, ppl)
        if gr and not hit:
            st = fire(gr['side'], 'greet')
            if st[0] == 200: log('GREET', gr, '-> ghost', st)
        if hit:
            st = fire(hit['side']); log('WAVE', hit, '-> ghost', st, save_hit(res, hit).name)
        if time.time() - last_report > 60:
            log(f'alive: {frames / (time.time() - last_report):.1f} fps, up to {max_people} people in view')
            last_report, frames, max_people = time.time(), 0, 0

run_video() if args.video else run_live()
