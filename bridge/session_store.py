from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import threading


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._initialize()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS images (
                    image_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    client_request_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    text TEXT,
                    image_id TEXT,
                    answer_text TEXT,
                    error_code TEXT,
                    robot_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, client_request_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    image_id TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_session(self, name: str | None = None) -> str:
        import uuid
        session_id = f"sess_{uuid.uuid4().hex}"
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO sessions(session_id,name,created_at) VALUES(?,?,?)",
                (session_id, name, now()),
            )
        return session_id

    def session_exists(self, session_id: str) -> bool:
        row = self.connection.execute("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return row is not None

    def add_image(self, image, session_id: str | None) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO images VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (image.image_id, session_id, str(image.path), image.mime_type, image.sha256,
                 image.width, image.height, image.byte_size, image.source, image.captured_at, now()),
            )

    def get_image(self, image_id: str):
        return self.connection.execute("SELECT * FROM images WHERE image_id=?", (image_id,)).fetchone()

    def get_request(self, request_id: str):
        return self.connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()

    def get_by_client_id(self, session_id: str, client_request_id: str):
        return self.connection.execute(
            "SELECT * FROM requests WHERE session_id=? AND client_request_id=?",
            (session_id, client_request_id),
        ).fetchone()

    def create_request(self, request_id: str, session_id: str, client_request_id: str,
                       request_hash: str, kind: str, text: str | None, image_id: str | None) -> None:
        timestamp = now()
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO requests(request_id,session_id,client_request_id,request_hash,kind,status,text,image_id,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (request_id, session_id, client_request_id, request_hash, kind, "queued", text, image_id, timestamp, timestamp),
            )

    def update_request(self, request_id: str, **values) -> None:
        allowed = {"status", "answer_text", "error_code", "robot_json", "image_id"}
        values = {key: value for key, value in values.items() if key in allowed}
        if not values:
            return
        values["updated_at"] = now()
        assignments = ", ".join(f"{key}=?" for key in values)
        params = list(values.values()) + [request_id]
        with self.lock, self.connection:
            self.connection.execute(f"UPDATE requests SET {assignments} WHERE request_id=?", params)

    def add_message(self, session_id: str, request_id: str, role: str, text: str, image_id: str | None) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO messages(session_id,request_id,role,text,image_id,created_at) VALUES(?,?,?,?,?,?)",
                (session_id, request_id, role, text, image_id, now()),
            )

    def history(self, session_id: str, limit: int = 12) -> list[dict]:
        rows = self.connection.execute(
            "SELECT role,text,image_id FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    @staticmethod
    def request_json(row) -> dict:
        result = dict(row)
        result["robot"] = json.loads(result.pop("robot_json") or "{}")
        return result
