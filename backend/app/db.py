from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("IRIS_DATA_DIR", ROOT_DIR / "data")).expanduser().resolve()
DATABASE_DIR = DATA_DIR / "database"
UPLOAD_DIR = DATA_DIR / "uploads"
MODEL_DIR = DATA_DIR / "models" / "insightface"
DB_PATH = DATABASE_DIR / "iris.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    legacy_db = DATA_DIR / "iris.sqlite3"
    legacy_models = DATA_DIR / "insightface"
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    if legacy_db.is_file() and not DB_PATH.exists():
        shutil.move(str(legacy_db), str(DB_PATH))
    if legacy_models.is_dir() and not MODEL_DIR.exists():
        shutil.move(str(legacy_models), str(MODEL_DIR))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value_json"])


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value), utc_now()),
    )


def init_db() -> None:
    ensure_dirs()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS people (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              alias TEXT NOT NULL DEFAULT '',
              role TEXT NOT NULL CHECK(role IN ('Family', 'Friend', 'Employee', 'Guest')),
              notes TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL CHECK(status IN ('Active', 'Disabled')) DEFAULT 'Active',
              indexed_faces INTEGER NOT NULL DEFAULT 0,
              total_recognitions INTEGER NOT NULL DEFAULT 0,
              last_seen TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS person_faces (
              id TEXT PRIMARY KEY,
              person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              face_id TEXT NOT NULL,
              embedding TEXT NOT NULL,
              image_path TEXT NOT NULL,
              source_image_path TEXT NOT NULL DEFAULT '',
              embedding_model TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cameras (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              model TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL CHECK(status IN ('online', 'offline')) DEFAULT 'online',
              stream_url TEXT NOT NULL DEFAULT '',
              still_url TEXT NOT NULL DEFAULT '',
              trigger_slug TEXT NOT NULL DEFAULT '',
              face_detection INTEGER NOT NULL DEFAULT 1,
              motion INTEGER NOT NULL DEFAULT 1,
              cooldown INTEGER NOT NULL DEFAULT 60,
              min_face INTEGER NOT NULL DEFAULT 8,
              min_confidence INTEGER NOT NULL DEFAULT 80,
              last_detection TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
              person_name TEXT NOT NULL,
              confidence REAL NOT NULL DEFAULT 0,
              camera_id TEXT,
              camera_name TEXT NOT NULL DEFAULT 'Manual upload',
              type TEXT NOT NULL CHECK(type IN ('known', 'unknown', 'review', 'no_face', 'skipped', 'error', 'processing')),
              face_id TEXT,
              inference_id TEXT NOT NULL DEFAULT '',
              face_bounding_box TEXT NOT NULL DEFAULT '',
              face_details_json TEXT NOT NULL DEFAULT '',
              processing_ms REAL NOT NULL DEFAULT 0,
              image_path TEXT NOT NULL DEFAULT '',
              thumb_path TEXT NOT NULL DEFAULT '',
              face_crop_path TEXT NOT NULL DEFAULT '',
              original_deleted_at TEXT,
              event_time TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unknown_visitors (
              id TEXT PRIMARY KEY,
              camera_id TEXT,
              camera_name TEXT NOT NULL DEFAULT 'Manual upload',
              image_path TEXT NOT NULL,
              detections INTEGER NOT NULL DEFAULT 1,
              event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS logs (
              id TEXT PRIMARY KEY,
              time TEXT NOT NULL,
              service TEXT NOT NULL,
              severity TEXT NOT NULL CHECK(severity IN ('info', 'warn', 'error')),
              message TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            """
        )
        if get_setting(conn, "insightface") is None:
            set_setting(conn, "insightface", {
                "model_name": "buffalo_s",
                "provider": "CPUExecutionProvider",
                "det_size": 640,
                "age_gender_enabled": False,
            })
        if get_setting(conn, "thresholds") is None:
            set_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        else:
            thresholds = get_setting(conn, "thresholds", {})
            if int(thresholds.get("match", 0)) >= 80:
                set_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        if get_setting(conn, "storage") is None:
            set_setting(conn, "storage", {"max_storage_mb": 2048})
        if get_setting(conn, "logs") is None:
            set_setting(conn, "logs", {"max_rows": 500})
        if get_setting(conn, "mqtt") is None:
            set_setting(
                conn,
                "mqtt",
                {
                    "host": "",
                    "port": 1883,
                    "username": "",
                    "password": "",
                    "discovery_prefix": "homeassistant",
                    "base_topic": "iris",
                    "device_id": "iris_face_recognition",
                    "device_name": "IRIS Face Recognition",
                    "use_tls": False,
                },
            )
        if get_setting(conn, "telegram") is None:
            set_setting(conn, "telegram", {"bot_token": "", "chat_id": ""})
        event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "face_details_json" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN face_details_json TEXT NOT NULL DEFAULT ''")
        if "face_id" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN face_id TEXT")
        if "inference_id" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN inference_id TEXT NOT NULL DEFAULT ''")
        if "processing_ms" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN processing_ms REAL NOT NULL DEFAULT 0")

        face_columns = {row["name"] for row in conn.execute("PRAGMA table_info(person_faces)").fetchall()}
        if "embedding" not in face_columns:
            conn.executescript(
                """
                ALTER TABLE person_faces RENAME TO legacy_person_faces;
                CREATE TABLE person_faces (
                  id TEXT PRIMARY KEY,
                  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                  face_id TEXT NOT NULL,
                  embedding TEXT NOT NULL,
                  image_path TEXT NOT NULL,
                  source_image_path TEXT NOT NULL DEFAULT '',
                  embedding_model TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL
                );
                INSERT INTO person_faces (id, person_id, face_id, embedding, image_path, created_at)
                SELECT id, person_id, id, '', image_path, created_at FROM legacy_person_faces;
                DROP TABLE legacy_person_faces;
                """
            )
        face_columns = {row["name"] for row in conn.execute("PRAGMA table_info(person_faces)").fetchall()}
        if "source_image_path" not in face_columns:
            conn.execute("ALTER TABLE person_faces ADD COLUMN source_image_path TEXT NOT NULL DEFAULT ''")
        if "embedding_model" not in face_columns:
            conn.execute("ALTER TABLE person_faces ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            UPDATE person_faces
            SET source_image_path = COALESCE((
              SELECT e.image_path FROM events e
              WHERE e.face_crop_path = person_faces.image_path AND e.image_path != ''
              ORDER BY e.created_at ASC LIMIT 1
            ), '')
            WHERE source_image_path = ''
            """
        )

        conn.execute(
            "DELETE FROM settings WHERE key NOT IN ('insightface', 'thresholds', 'storage', 'logs', 'mqtt', 'telegram')"
        )
        conn.execute(
            "DELETE FROM logs WHERE service NOT IN ('InsightFace', 'UniFi', 'Recognition', 'Notification', 'System')"
        )
        allowed_tables = {
            "settings", "people", "person_faces", "cameras", "events", "unknown_visitors", "logs"
        }
        extra_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for table in extra_tables:
            if table["name"] not in allowed_tables:
                safe_name = table["name"].replace('"', '""')
                conn.execute(f'DROP TABLE "{safe_name}"')
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
            CREATE INDEX IF NOT EXISTS idx_events_camera_time ON events(camera_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_person_time ON events(person_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_person_faces_person_time ON person_faces(person_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at DESC);
            """
        )


def clear_database() -> None:
    with connect() as conn:
        conn.executescript(
            """
            DELETE FROM unknown_visitors;
            DELETE FROM events;
            DELETE FROM person_faces;
            DELETE FROM cameras;
            DELETE FROM people;
            DELETE FROM logs;
            DELETE FROM settings;
            """
        )


def prune_logs(conn: sqlite3.Connection, max_rows: int | None = None) -> None:
    if max_rows is None:
        cfg = get_setting(conn, "logs", {"max_rows": 500})
        max_rows = int(cfg.get("max_rows", 500))
    max_rows = max(50, min(10000, int(max_rows)))
    total = conn.execute("SELECT COUNT(*) AS c FROM logs").fetchone()["c"]
    if total <= max_rows:
        return
    conn.execute(
        """
        DELETE FROM logs
        WHERE id NOT IN (
          SELECT id FROM logs ORDER BY created_at DESC LIMIT ?
        )
        """,
        (max_rows,),
    )


def add_log(conn: sqlite3.Connection, service: str, severity: str, message: str) -> str:
    now = utc_now()
    log_id = new_id("log")
    conn.execute(
        "INSERT INTO logs (id, time, service, severity, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (log_id, now[11:19], service, severity, message, now),
    )
    prune_logs(conn)
    return log_id
