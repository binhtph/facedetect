from __future__ import annotations

def serialize_person(row: dict, face_id: str = "", latest_image_path: str = "") -> dict:
    base = dict(row)
    base.pop("preview_face_id", None)
    base.pop("preview_image_path", None)
    return {
        **base,
        "displayName": row["alias"] or row["name"],
        "photos": row["indexed_faces"],
        "lastSeen": row["last_seen"] or "Never",
        "indexedFaces": row["indexed_faces"],
        "totalRecognitions": row["total_recognitions"],
        "faceId": face_id,
        "latest_image_path": latest_image_path,
    }


def person_preview_data(conn, person_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    if not person_ids:
        return {}, {}
    placeholders = ",".join("?" for _ in person_ids)
    face_rows = conn.execute(
        f"""
        SELECT person_id, face_id, image_path
        FROM person_faces
        WHERE person_id IN ({placeholders})
        ORDER BY created_at DESC
        """,
        person_ids,
    ).fetchall()
    face_ids: dict[str, str] = {}
    for row in face_rows:
        face_ids.setdefault(row["person_id"], row["face_id"])

    event_rows = conn.execute(
        f"""
        SELECT person_id, image_path, thumb_path, face_crop_path
        FROM events
        WHERE person_id IN ({placeholders})
          AND (image_path != '' OR thumb_path != '' OR face_crop_path != '')
        ORDER BY created_at DESC
        """,
        person_ids,
    ).fetchall()
    latest_image: dict[str, str] = {}
    for row in event_rows:
        latest_image.setdefault(
            row["person_id"],
            row["face_crop_path"] or row["thumb_path"] or row["image_path"] or "",
        )
    for row in face_rows:
        latest_image.setdefault(row["person_id"], row["image_path"] or "")
    return face_ids, latest_image


def person_name_from_external_id(external_id: str) -> str:
    value = external_id.strip() or "InsightFace imported face"
    value = value.replace("_", " ").replace("-", " ")
    return value[:1].upper() + value[1:]


def display_person_name(person: dict | None) -> str:
    if not person:
        return "Unknown match"
    return person.get("alias") or person.get("name") or "Unknown match"
