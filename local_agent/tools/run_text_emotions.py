import json, time, pathlib, httpx
from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / '.env')
H = {'Authorization': 'Bearer ' + env['BRIDGE_TOKEN'], 'Origin': 'http://127.0.0.1:8765'}
A = httpx.Client(base_url='http://127.0.0.1:8765', headers=H, timeout=60, trust_env=False)
D = httpx.Client(base_url='http://127.0.0.1:8000', timeout=10, trust_env=False)
pose = lambda: D.get('/api/state/present_head_pose').json()

CASES = [
    ('anger', '我上周按合同交的押金，房东今天说不退了，理由一个都不给，联系也不回。这明摆着是不讲道理。'),
    ('confusion', '你刚才说评审会是周三上午，可是邮件里写的是周五下午，两个时间对不上，我不知道该按哪个准备。'),
]
EXPECT = {'anger': 'roll -5,+5,0', 'confusion': 'roll -6,+6,0'}
rows = []
for name, text in CASES:
    sid = A.post('/api/sessions').json()['session_id']
    base = pose()
    jid = A.post('/api/jobs', json={'session_id': sid, 'request_id': 'text-' + name,
                                    'kind': 'message', 'text': text}).json()['id']
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
    ex = res.get('expression_result') or {}
    sel = ex.get('selected_emotion')
    print('=' * 72)
    print('input   : text (no image)   target class: %s (%s)' % (name, EXPECT[name]))
    print('said    : %s' % text)
    print('status  : %s  %.1fs  error=%s' % (status, time.time() - t0, row.get('error')))
    print('reply   : %s' % res.get('reply'))
    print('SELECTED: %s   %s' % (sel, 'MATCH' if sel == name else '<-- different class'))
    print('mapped  : %s' % json.dumps(ex.get('mapped_activity'), ensure_ascii=False))
    print('motion  : %s' % json.dumps(ex.get('motion'), ensure_ascii=False))
    print('measured: pitch %+.4f..%+.4f rad | roll %+.4f..%+.4f rad' % (pmin, pmax, rmin, rmax))
    rows.append({'path': 'text', 'target': name, 'selected': sel, 'mapped': ex.get('mapped_activity'),
                 'motion': ex.get('motion'), 'pitch_range': [pmin, pmax], 'roll_range': [rmin, rmax],
                 'reply': res.get('reply'), 'job_id': jid})
    json.dump(row, open(ROOT / 'data' / ('text-%s.json' % name), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
json.dump(rows, open(ROOT / 'data' / 'emotion-matrix-text.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
