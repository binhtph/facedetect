from __future__ import annotations

import re

from fastapi import HTTPException

from .db import connect, new_id, row_to_dict


def slugify_camera_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return value.strip("-") or new_id("camera")


def ensure_unique_camera_name(conn, name: str, camera_id: str | None = None) -> None:
    row = conn.execute(
        "SELECT id FROM cameras WHERE lower(name) = lower(?) AND (? IS NULL OR id != ?) LIMIT 1",
        (name.strip(), camera_id, camera_id),
    ).fetchone()
    if row:
        raise HTTPException(status_code=409, detail="Camera name already exists.")


def unique_camera_slug(conn, name: str, camera_id: str | None = None) -> str:
    base = slugify_camera_name(name)
    slug = base
    index = 2
    while conn.execute(
        "SELECT 1 FROM cameras WHERE trigger_slug = ? AND (? IS NULL OR id != ?) LIMIT 1",
        (slug, camera_id, camera_id),
    ).fetchone():
        slug = f"{base}-{index}"
        index += 1
    return slug


def serialize_camera(row: dict) -> dict:
    slug = row.get("trigger_slug") or slugify_camera_name(row.get("name", "camera"))
    with connect() as conn:
        latest = row_to_dict(
            conn.execute(
                """
                SELECT image_path, thumb_path, face_crop_path
                FROM events
                WHERE camera_id = ?
                  AND (image_path != '' OR thumb_path != '' OR face_crop_path != '')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
        )
    still_url = row.get("still_url") or row.get("stream_url") or ""
    return {
        **row,
        "still_url": still_url,
        "trigger_slug": slug,
        "trigger_path": f"/api/cameras/trigger/{slug}",
        "latest_image_path": (latest.get("face_crop_path") or latest.get("image_path") or latest.get("thumb_path")) if latest else "",
    }
