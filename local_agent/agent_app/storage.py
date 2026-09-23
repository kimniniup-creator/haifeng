import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex

def now():
    return datetime.now(timezone.utc).isoformat()

def dump(value):
    return json.dumps(value, ensure_ascii=False)

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, quiet INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), request_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, image_id TEXT, status TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', created TEXT NOT NULL, UNIQUE(session_id, request_id));
        CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), path TEXT NOT NULL, sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id), content TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), job_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL, supersedes TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS effects(job_id TEXT PRIMARY KEY REFERENCES jobs(id), status TEXT NOT NULL, result TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY, job_id TEXT, stage TEXT, model TEXT, usage TEXT, latency_ms INTEGER, created TEXT);
        CREATE INDEX IF NOT EXISTS idx_messages ON messages(session_id, created);
        CREATE INDEX IF NOT EXISTS idx_jobs ON jobs(status, created);
        ''')

    def execute(self, sql, args=()):
        with self.db:
            return self.db.execute(sql, args)

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def session(self):
        sid = uid('session')
        self.execute('INSERT INTO sessions(id,created) VALUES(?,?)', (sid, now()))
        return sid

    def message(self, sid, job, role, content):
        mid = uid('msg')
        self.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)', (mid, sid, job, role, dump(content), now()))
        return mid

    def job(self, jid):
        row = self.one('SELECT * FROM jobs WHERE id=?', (jid,))
        if row:
            row['result'] = json.loads(row['result'])
        return row

    def update_job(self, jid, status, **updates):
        row = self.job(jid)
        result = row['result']
        result.update(updates)
        self.execute('UPDATE jobs SET status=?,result=? WHERE id=?', (status, dump(result), jid))

    def quiet(self, sid):
        return bool(self.one('SELECT quiet FROM sessions WHERE id=?', (sid,))['quiet'])

    def set_quiet(self, sid, enabled):
        self.execute('UPDATE sessions SET quiet=? WHERE id=?', (int(enabled), sid))

    def recover(self):
        # A persisted effect may already have happened. Never replay it.
        self.execute("UPDATE effects SET status='unknown' WHERE status='running'")
        self.execute("UPDATE jobs SET status='interrupted' WHERE status NOT IN ('queued','completed','failed','cancelled','interrupted')")

    def claim_effect(self, jid):
        with self.db:
            cursor = self.db.execute('INSERT OR IGNORE INTO effects VALUES(?,?,?,?)', (jid, 'running', '{}', now()))
        return cursor.rowcount == 1

    def effect(self, jid, status, result):
        self.execute('UPDATE effects SET status=?,result=?,updated=? WHERE job_id=?', (status, dump(result), now(), jid))

    def memory(self, text, evidence, kind, sid, supersedes=None):
        if not text.strip() or len(text) > 1000 or not evidence:
            raise ValueError('MEMORY_NEEDS_TEXT_AND_EVIDENCE')
        has_user = has_observation = False
        for ref in evidence:
            msg = self.one("SELECT role FROM messages WHERE id=? AND session_id=?", (ref, sid))
            obs = self.one('SELECT o.id FROM observations o JOIN images i ON i.id=o.image_id WHERE o.id=? AND i.session_id=?', (ref, sid))
            if not msg and not obs:
                raise ValueError('INVALID_EVIDENCE')
            has_user |= bool(msg and msg['role'] == 'user')
            has_observation |= bool(obs)
        if kind == 'user_statement' and not has_user:
            raise ValueError('USER_MESSAGE_REQUIRED')
        if kind == 'shared_observation' and not has_observation:
            raise ValueError('OBSERVATION_REQUIRED')
        previous = self.one("SELECT id FROM memories WHERE text=? AND evidence=? AND status='active'", (text, dump(evidence)))
        if previous:
            return previous['id']
        mid = uid('mem')
        self.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?)', (mid, text, kind, dump(evidence), 'active', supersedes, now()))
        return mid

    def search(self, query, limit=5):
        limit = min(max(int(limit), 1), 5)
        rows = self.all("SELECT * FROM memories WHERE status='active' ORDER BY created DESC LIMIT 500")
        text = query.lower().strip()
        target_day = None
        local_now = datetime.now().astimezone()
        if '今天' in text or 'today' in text:
            target_day = local_now.date()
        elif '昨天' in text or 'yesterday' in text:
            target_day = (local_now - timedelta(days=1)).date()
        if target_day:
            rows = [r for r in rows if datetime.fromisoformat(r['created']).astimezone().date() == target_day]
        terms = re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]{2,}', text)
        stop = {'今天', '昨天', '什么', '记得', '看过', '我们', '东西', '给你', 'today', 'yesterday'}
        grams = set()
        for term in terms:
            if re.search(r'[\u4e00-\u9fff]', term):
                grams.update(term[i:i+2] for i in range(len(term)-1) if term[i:i+2] not in stop)
            elif term not in stop:
                grams.add(term)
        ranked = [(sum(g in r['text'].lower() for g in grams), r) for r in rows]
        hits = [r for score, r in sorted(ranked, key=lambda x:x[0], reverse=True) if score > 0]
        if not hits and (target_day or not text or '最近' in text):
            hits = rows
        for row in hits[:limit]:
            row['evidence'] = json.loads(row['evidence'])
        return hits[:limit]

    def close(self):
        self.db.close()
