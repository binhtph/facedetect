from __future__ import annotations

import time

from .db import UPLOAD_DIR, add_log, connect, get_setting, rows_to_dicts, utc_now
from .uploads import safe_upload_path


def normalize_upload_ref(path: str | None) -> str:
    return (path or "").strip().replace("\\", "/")


def upload_reference_count(conn, rel_path: str) -> int:
    rel_path = normalize_upload_ref(rel_path)
    if not rel_path:
        return 0
    variants = (rel_path, rel_path.replace("/", "\\"))
    references = 0
    for column in ("image_path", "thumb_path", "face_crop_path"):
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM events WHERE {column} IN (?, ?)",
            variants,
        ).fetchone()
        references += int(row["c"] if row else 0)
    for table in ("unknown_visitors", "person_faces"):
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE image_path IN (?, ?)",
            variants,
        ).fetchone()
        references += int(row["c"] if row else 0)
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM person_faces WHERE source_image_path IN (?, ?)", variants
    ).fetchone()
    references += int(row["c"] if row else 0)
    return references


def referenced_upload_paths(conn) -> set[str]:
    paths: set[str] = set()
    for column in ("image_path", "thumb_path", "face_crop_path"):
        rows = conn.execute(f"SELECT {column} AS path FROM events WHERE {column} != ''").fetchall()
        paths.update(normalize_upload_ref(row["path"]) for row in rows if normalize_upload_ref(row["path"]))
    for table in ("unknown_visitors", "person_faces"):
        rows = conn.execute(f"SELECT image_path AS path FROM {table} WHERE image_path != ''").fetchall()
        paths.update(normalize_upload_ref(row["path"]) for row in rows if normalize_upload_ref(row["path"]))
    rows = conn.execute(
        "SELECT source_image_path AS path FROM person_faces WHERE source_image_path != ''"
    ).fetchall()
    paths.update(normalize_upload_ref(row["path"]) for row in rows if normalize_upload_ref(row["path"]))
    return paths


def delete_upload_if_unreferenced(image_path: str) -> bool:
    image_path = normalize_upload_ref(image_path)
    if not image_path:
        return False
    with connect() as conn:
        references = upload_reference_count(conn, image_path)
    if references > 0:
        return False
    file_path = safe_upload_path(image_path)
    if not file_path or not file_path.is_file():
        return False
    try:
        file_path.unlink()
        return True
    except OSError:
        return False


def delete_unreferenced_uploads(image_paths: list[str]) -> int:
    deleted = 0
    seen: set[str] = set()
    for image_path in image_paths:
        normalized = normalize_upload_ref(image_path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if delete_upload_if_unreferenced(normalized):
            deleted += 1
    return deleted


def cleanup_orphan_uploads(min_age_seconds: int = 300) -> dict:
    if not UPLOAD_DIR.exists():
        return {"deleted_files": 0, "deleted_bytes": 0}
    with connect() as conn:
        referenced = referenced_upload_paths(conn)
    deleted_files = 0
    deleted_bytes = 0
    cutoff = time.time() - max(0, min_age_seconds)
    for file_path in sorted(UPLOAD_DIR.rglob("*"), reverse=True):
        if not file_path.is_file():
            continue
        try:
            if file_path.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        try:
            rel_path = file_path.relative_to(UPLOAD_DIR).as_posix()
        except ValueError:
            continue
        if rel_path in referenced:
            continue
        try:
            size = file_path.stat().st_size
            file_path.unlink()
        except OSError:
            continue
        deleted_files += 1
        deleted_bytes += size

    for directory in sorted((p for p in UPLOAD_DIR.rglob("*") if p.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return {"deleted_files": deleted_files, "deleted_bytes": deleted_bytes}


def upload_file_size(rel_path: str) -> int:
    file_path = safe_upload_path(rel_path)
    if not file_path or not file_path.is_file():
        return 0
    try:
        return file_path.stat().st_size
    except OSError:
        return 0


def upload_storage_bytes() -> int:
    total = 0
    if not UPLOAD_DIR.exists():
        return 0
    for file_path in UPLOAD_DIR.rglob("*"):
        if file_path.is_file():
            try:
                total += file_path.stat().st_size
            except OSError:
                pass
    return total


def protected_original_paths() -> set[str]:
    with connect() as conn:
        protected = {
            normalize_upload_ref(row["image_path"])
            for row in conn.execute("SELECT image_path FROM person_faces WHERE image_path != ''").fetchall()
        }
        protected.update(
            normalize_upload_ref(row["image_path"])
            for row in conn.execute("SELECT image_path FROM unknown_visitors WHERE image_path != ''").fetchall()
        )
    return protected


def cleanup_rank(event: dict, auto_accept: int) -> int:
    event_type = event.get("type")
    confidence = float(event.get("confidence") or 0)
    if event_type in {"skipped", "no_face", "error", "processing"}:
        return 10
    if event_type == "known" and confidence >= auto_accept:
        return 20
    if event_type == "known":
        return 35
    if event_type == "review":
        return 60
    if event_type == "unknown":
        return 90
    return 100


def cleanup_storage_to_quota() -> dict:
    with connect() as conn:
        storage = get_setting(conn, "storage", {"max_storage_mb": 2048})
        thresholds = get_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
    orphan_cleanup = cleanup_orphan_uploads()
    max_bytes = int(storage.get("max_storage_mb", 2048)) * 1024 * 1024
    used_bytes = upload_storage_bytes()
    deleted_bytes = int(orphan_cleanup["deleted_bytes"])
    deleted_files = int(orphan_cleanup["deleted_files"])
    if used_bytes <= max_bytes:
        if deleted_files:
            with connect() as conn:
                add_log(conn, "System", "info", f"Storage cleanup removed {deleted_files} orphan upload file(s)")
        return {"ok": True, "deleted_files": deleted_files, "deleted_bytes": deleted_bytes, "used_bytes": used_bytes, "max_bytes": max_bytes}

    protected = protected_original_paths()
    with connect() as conn:
        events = rows_to_dicts(
            conn.execute(
                """
                SELECT id, type, confidence, image_path, created_at
                FROM events
                WHERE image_path != '' AND original_deleted_at IS NULL
                ORDER BY created_at ASC
                """
            ).fetchall()
        )
    events.sort(key=lambda event: (cleanup_rank(event, int(thresholds.get("auto_accept", 55))), event.get("created_at") or ""))

    for event in events:
        if used_bytes <= max_bytes:
            break
        image_path = normalize_upload_ref(event.get("image_path") or "")
        if not image_path or image_path in protected:
            continue
        file_path = safe_upload_path(image_path)
        if not file_path or not file_path.is_file():
            with connect() as conn:
                conn.execute("UPDATE events SET image_path = '', original_deleted_at = ? WHERE id = ?", (utc_now(), event["id"]))
            continue
        size = upload_file_size(image_path)
        try:
            file_path.unlink()
        except OSError:
            continue
        with connect() as conn:
            conn.execute("UPDATE events SET image_path = '', original_deleted_at = ? WHERE id = ?", (utc_now(), event["id"]))
        used_bytes = max(0, used_bytes - size)
        deleted_bytes += size
        deleted_files += 1

    if deleted_files:
        with connect() as conn:
            add_log(conn, "System", "info", f"Storage cleanup removed {deleted_files} upload file(s)")
    return {"ok": True, "deleted_files": deleted_files, "deleted_bytes": deleted_bytes, "used_bytes": used_bytes, "max_bytes": max_bytes}


def storage_status() -> dict:
    with connect() as conn:
        storage = get_setting(conn, "storage", {"max_storage_mb": 2048})
        protected_unknown = conn.execute("SELECT COUNT(*) AS c FROM unknown_visitors WHERE image_path != ''").fetchone()["c"]
        protected_faces = conn.execute("SELECT COUNT(*) AS c FROM person_faces WHERE image_path != ''").fetchone()["c"]
    max_bytes = int(storage.get("max_storage_mb", 2048)) * 1024 * 1024
    used_bytes = upload_storage_bytes()
    return {
        "used_bytes": used_bytes,
        "max_bytes": max_bytes,
        "used_mb": round(used_bytes / 1024 / 1024, 2),
        "max_storage_mb": int(storage.get("max_storage_mb", 2048)),
        "percent": round((used_bytes / max_bytes) * 100, 1) if max_bytes else 0,
        "protected_unknown": protected_unknown,
        "protected_faces": protected_faces,
    }


def enforce_storage_quota() -> None:
    try:
        cleanup_storage_to_quota()
    except Exception:
        pass
