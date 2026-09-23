import json, sys, time, pathlib, httpx
from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMGS = pathlib.Path(sys.argv[1])
env = dotenv_values(ROOT / '.env')
H = {'Authorization': 'Bearer ' + env['BRIDGE_TOKEN'], 'Origin': 'http://127.0.0.1:8765'}
A = httpx.Client(base_url='http://127.0.0.1:8765', headers=H, timeout=60, trust_env=False)
D = httpx.Client(base_url='http://127.0.0.1:8000', timeout=10, trust_env=False)
pose = lambda: D.get('/api/state/present_head_pose').json()

EXPECTED = {'joy': 'pitch +4,0,+4', 'excitement': 'pitch +6,-3,+6,0', 'sadness': 'pitch -5,0',
            'anger': 'roll -5,+5,0', 'confusion': 'roll -6,+6,0', 'curiosity': 'roll +6,0'}

names = sys.argv[2:] or ['joy', 'excitement', 'sadness', 'anger', 'confusion']
rows = []
for name in names:
    path = IMGS / (name + '.jpg')
    sid = A.post('/api/sessions').json()['session_id']
    with path.open('rb') as f:
        up = A.post('/api/images', data={'session_id': sid},
                    files={'image': (path.name, f, 'image/jpeg')})
    up.raise_for_status()
    iid = up.json()['image_id']
    base = pose()
    jid = A.post('/api/jobs', json={'session_id': sid, 'request_id': 'emo-' + name,
        'kind': 'image', 'image_id': iid,
        'text': '这是我分享的一张画面，按可见内容选一个回应情绪。'}).json()['id']
    pmin = pmax = rmin = rmax = 0.0
    status = None; t0 = time.time()
    while time.time() - t0 < 200:
        status = A.get('/api/jobs/' + jid).json().get('status')
        try:
            p = pose()
            dp, dr = p['pitch'] - base['pitch'], p['roll'] - base['roll']
            pmin, pmax = min(pmin, dp), max(pmax, dp)
            rmin, rmax = min(rmin, dr), max(rmax, dr)
        except Exception:
            pass
        if status in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(0.08)
    row = A.get('/api/jobs/' + jid).json()
    res = row.get('result') or {}
    obs = (res.get('observation') or {}).get('content') or {}
    ex = res.get('expression_result') or {}
    sel = ex.get('selected_emotion')
    print('=' * 72)
    cls = name.rstrip('0123456789')
    print('image   : %s.jpg   expected class: %s (%s)' % (name, cls, EXPECTED[cls]))
    print('status  : %s  %.1fs  error=%s' % (status, time.time() - t0, row.get('error')))
    print('summary : %s' % obs.get('summary'))
    print('model   : %s  | evidence: %s' % (obs.get('response_emotion'), obs.get('emotion_evidence')))
    print('SELECTED: %s   %s' % (sel, 'MATCH' if sel == name.rstrip('0123456789') else '<-- different class'))
    print('mapped  : %s' % json.dumps(ex.get('mapped_activity'), ensure_ascii=False))
    print('motion  : %s' % json.dumps(ex.get('motion'), ensure_ascii=False))
    print('measured: pitch %+.4f..%+.4f rad | roll %+.4f..%+.4f rad' % (pmin, pmax, rmin, rmax))
    rows.append({'image': name, 'selected': sel, 'model': obs.get('response_emotion'),
                 'mapped': ex.get('mapped_activity'), 'motion': ex.get('motion'),
                 'pitch_range': [pmin, pmax], 'roll_range': [rmin, rmax],
                 'summary': obs.get('summary'), 'evidence': obs.get('emotion_evidence'),
                 'job_id': jid, 'image_id': iid})
    json.dump(row, open(ROOT / 'data' / ('emo-%s.json' % name), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
json.dump(rows, open(ROOT / 'data' / 'emotion-matrix.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('=' * 72)
print('summary:', ' | '.join('%s->%s(%s)' % (r['image'], r['selected'],
      (r['motion'] or {}).get('status')) for r in rows))
