from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import insightface_engine, mqtt_homeassistant, telegram_notify
from .camera_utils import ensure_unique_camera_name, serialize_camera, unique_camera_slug
from .db import UPLOAD_DIR, add_log, clear_database, connect, get_setting, init_db, new_id, prune_logs, row_to_dict, rows_to_dicts, set_setting, utc_now
from .people_utils import display_person_name, person_name_from_external_id, person_preview_data, serialize_person
from .schemas import InsightFaceSettingsIn, CameraIn, LogsSettingsIn, MqttSettingsIn, PersonIn, StorageSettingsIn, TelegramSettingsIn, ThresholdsIn
from .storage_service import cleanup_storage_to_quota, delete_unreferenced_uploads, enforce_storage_quota, normalize_upload_ref, storage_status
from .uploads import create_event_images, crop_saved_image_to_face, fetch_still_image, safe_upload_path, save_image_bytes, save_upload

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("iris")
logger.setLevel(logging.INFO)

app = FastAPI(title="IRIS Face Recognition API")
mqtt_bridge = mqtt_homeassistant.MqttBridge(
    on_camera_trigger=lambda slug: handle_mqtt_camera_trigger(slug),
    on_connected=lambda config, reason: republish_mqtt_home_assistant(config, reason),
    on_status_change=lambda severity, message: record_mqtt_status(severity, message),
)
model_rebuild_lock = threading.Lock()
model_rebuild_status: dict = {
    "status": "idle",
    "model_name": "",
    "processed": 0,
    "total": 0,
    "progress": 0,
    "error": None,
}


def normalize_person_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = normalized.replace("đ", "d").replace("Đ", "d")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^a-z0-9_.-]+", "_", ascii_value).strip("_.-")
    safe = re.sub(r"_+", "_", safe)
    return safe[:255]


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https?://([a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\]):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def insightface_config() -> insightface_engine.InsightFaceConfig:
    with connect() as conn:
        cfg = get_setting(conn, "insightface", {})
    return insightface_engine.InsightFaceConfig(
        model_name=cfg.get("model_name", "buffalo_s"),
        provider=cfg.get("provider", "CPUExecutionProvider"),
        det_size=int(cfg.get("det_size", 640)),
        age_gender_enabled=bool(cfg.get("age_gender_enabled", False)),
        max_faces=max(1, min(10, int(cfg.get("max_faces", 1)))),
    )


def mqtt_config() -> mqtt_homeassistant.MqttConfig:
    with connect() as conn:
        cfg = get_setting(conn, "mqtt", {})
    return mqtt_homeassistant.MqttConfig(
        host=cfg.get("host", ""),
        port=int(cfg.get("port", 1883)),
        username=cfg.get("username", ""),
        password=cfg.get("password", ""),
        discovery_prefix=cfg.get("discovery_prefix", "homeassistant"),
        base_topic=cfg.get("base_topic", "iris"),
        device_id=cfg.get("device_id", "iris_face_recognition"),
        device_name=cfg.get("device_name", "IRIS Face Recognition"),
        use_tls=bool(cfg.get("use_tls", False)),
    )


def telegram_config() -> telegram_notify.TelegramConfig:
    with connect() as conn:
        cfg = get_setting(conn, "telegram", {})
    return telegram_notify.TelegramConfig(
        bot_token=cfg.get("bot_token", ""),
        chat_id=cfg.get("chat_id", ""),
    )


def public_telegram_settings() -> dict:
    with connect() as conn:
        cfg = get_setting(conn, "telegram", {})
    token = cfg.get("bot_token", "")
    return {
        "configured": bool(token and cfg.get("chat_id")),
        "bot_token_configured": bool(token),
        "chat_id": cfg.get("chat_id", ""),
    }


def public_mqtt_settings() -> dict:
    with connect() as conn:
        cfg = get_setting(conn, "mqtt", {})
    return {
        "configured": bool(cfg.get("host")),
        "host": cfg.get("host", ""),
        "port": int(cfg.get("port", 1883)),
        "username": cfg.get("username", ""),
        "password_configured": bool(cfg.get("password")),
        "discovery_prefix": cfg.get("discovery_prefix", "homeassistant"),
        "base_topic": cfg.get("base_topic", "iris"),
        "device_id": cfg.get("device_id", "iris_face_recognition"),
        "device_name": cfg.get("device_name", "IRIS Face Recognition"),
        "use_tls": bool(cfg.get("use_tls", False)),
    }


def public_settings() -> dict:
    with connect() as conn:
        cfg = get_setting(conn, "insightface", {})
        thresholds = get_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        storage = get_setting(conn, "storage", {"max_storage_mb": 2048})
        telegram = get_setting(conn, "telegram", {})
    return {
        "insightface_configured": True,
        "model_name": cfg.get("model_name", "buffalo_s"),
        "provider": cfg.get("provider", "CPUExecutionProvider"),
        "det_size": int(cfg.get("det_size", 640)),
        "age_gender_enabled": bool(cfg.get("age_gender_enabled", False)),
        "max_faces": max(1, min(10, int(cfg.get("max_faces", 1)))),
        "thresholds": thresholds,
        "storage": {"max_storage_mb": int(storage.get("max_storage_mb", 2048))},
        "telegram_configured": bool(telegram.get("bot_token") and telegram.get("chat_id")),
    }


def current_mqtt_state() -> dict:
    with connect() as conn:
        thresholds = get_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        latest = row_to_dict(
            conn.execute(
                """
                SELECT e.*, p.alias AS current_alias, p.name AS current_name
                FROM events e
                LEFT JOIN people p ON p.id = e.person_id
                WHERE e.type IN ('known', 'review', 'unknown', 'no_face') AND e.notified = 1
                ORDER BY e.created_at DESC
                LIMIT 1
                """
            ).fetchone()
        )
    latest_alias = (latest.get("current_alias") or "").strip() if latest else ""
    latest_name = (latest.get("current_name") or "").strip() if latest else ""
    latest_event_name = (latest.get("person_name") or "").strip() if latest else ""
    latest_details = parse_face_details(latest.get("face_details_json") if latest else "")
    latest_type = latest["type"] if latest else ""
    latest_confidence = float(latest["confidence"] if latest else 0)
    auto_accept = int(thresholds.get("auto_accept", 55))
    if latest_type == "known" and latest_confidence >= auto_accept:
        latest_decision = "auto_accept"
    elif latest_type == "review":
        latest_decision = "review"
    elif latest_type == "unknown":
        latest_decision = "unknown"
    elif latest_type == "no_face":
        latest_decision = "no_face"
    else:
        latest_decision = latest_type
    return {
        "latest_event_id": (latest.get("id") or "") if latest else "",
        "latest_person": latest_alias or latest_name or latest_event_name,
        "latest_person_alias": latest_alias,
        "latest_person_name": latest_name or latest_event_name,
        "latest_person_id": (latest.get("person_id") or "") if latest else "",
        "latest_type": latest_type,
        "latest_decision": latest_decision,
        "latest_camera": latest["camera_name"] if latest else "",
        "latest_confidence": latest_confidence,
        "latest_time": latest["event_time"] if latest else "",
        "latest_attributes": compact_face_attributes(latest_details),
    }


def mqtt_event_payload(event_id: str) -> dict | None:
    with connect() as conn:
        thresholds = get_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        event = row_to_dict(
            conn.execute(
                """
                SELECT e.*, p.alias AS current_alias, p.name AS current_name
                FROM events e
                LEFT JOIN people p ON p.id = e.person_id
                WHERE e.id = ?
                """,
                (event_id,),
            ).fetchone()
        )
    if not event:
        return None
    event_type = event.get("type") or ""
    confidence = float(event.get("confidence") or 0)
    auto_accept = int(thresholds.get("auto_accept", 55))
    if event_type == "known" and confidence >= auto_accept:
        decision = "auto_accept"
    elif event_type in {"review", "unknown", "no_face"}:
        decision = event_type
    else:
        decision = event_type
    alias = (event.get("current_alias") or "").strip()
    name = (event.get("current_name") or "").strip()
    event_name = (event.get("person_name") or "").strip()
    details = parse_face_details(event.get("face_details_json"))
    return {
        "event_id": event.get("id") or "",
        "latest_event_id": event.get("id") or "",
        "latest_person": alias or name or event_name,
        "latest_person_alias": alias,
        "latest_person_name": name or event_name,
        "latest_person_id": event.get("person_id") or "",
        "latest_type": event_type,
        "latest_decision": decision,
        "latest_camera": event.get("camera_name") or "",
        "latest_confidence": confidence,
        "latest_time": event.get("event_time") or "",
        "latest_attributes": compact_face_attributes(details),
    }


def latest_mqtt_image_payload() -> bytes | None:
    with connect() as conn:
        latest = row_to_dict(
            conn.execute(
                """
                SELECT e.image_path, e.thumb_path, e.face_crop_path, e.person_name, e.confidence, e.face_bounding_box, e.type,
                       p.alias AS current_alias, p.name AS current_name
                FROM events e
                LEFT JOIN people p ON p.id = e.person_id
                WHERE (e.image_path != '' OR e.thumb_path != '' OR e.face_crop_path != '') AND e.notified = 1
                ORDER BY e.created_at DESC
                LIMIT 1
                """
            ).fetchone()
        )
    if not latest:
        return None
    rel_path = latest.get("face_crop_path") or latest.get("thumb_path") or latest.get("image_path") or ""
    file_path = safe_upload_path(rel_path)
    if not file_path or not file_path.exists():
        return None
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            draw_mqtt_image_overlay(img, latest)
            out = BytesIO()
            img.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except Exception:
        return None


def parse_bounding_box(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_face_details(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def compact_face_attributes(details: dict) -> dict:
    box = details.get("bounding_box") or {}
    return {
        "face_confidence": details.get("confidence", 0),
        "model": details.get("model", ""),
        "provider": details.get("provider", ""),
        "inference_id": details.get("inference_id", ""),
        "box_left": box.get("Left", 0),
        "box_top": box.get("Top", 0),
        "box_width": box.get("Width", 0),
        "box_height": box.get("Height", 0),
        "landmark_count": len(details.get("landmarks") or []),
        "age": details.get("age"),
        "gender": details.get("gender"),
    }


def load_overlay_font(size: int) -> ImageFont.ImageFont:
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_mqtt_image_overlay(img: Image.Image, event: dict) -> None:
    width, height = img.size
    box = parse_bounding_box(event.get("face_bounding_box"))
    color = (38, 127, 229) if event.get("type") != "unknown" else (245, 158, 11)

    if box:
        left = max(0, int(float(box.get("Left", 0)) * width))
        top = max(0, int(float(box.get("Top", 0)) * height))
        right = min(width - 1, int((float(box.get("Left", 0)) + float(box.get("Width", 0))) * width))
        bottom = min(height - 1, int((float(box.get("Top", 0)) + float(box.get("Height", 0))) * height))
    else:
        inset_x = max(2, int(width * 0.04))
        inset_y = max(2, int(height * 0.04))
        left, top, right, bottom = inset_x, inset_y, width - inset_x, height - inset_y

    draw = ImageDraw.Draw(img)
    stroke = max(3, int(min(width, height) * 0.01))
    radius = max(10, int(min(width, height) * 0.035))
    box_width = max(1, right - left)
    box_height = max(1, bottom - top)
    corner = min(max(18, int(min(box_width, box_height) * 0.22)), box_width // 2, box_height // 2)

    for start, end in [
        ((left, top), (left + corner, top)),
        ((left, top), (left, top + corner)),
        ((right - corner, top), (right, top)),
        ((right, top), (right, top + corner)),
        ((left, bottom), (left + corner, bottom)),
        ((left, bottom - corner), (left, bottom)),
        ((right - corner, bottom), (right, bottom)),
        ((right, bottom - corner), (right, bottom)),
    ]:
        draw.line((start, end), fill=color, width=stroke)

    person = (event.get("current_alias") or event.get("current_name") or event.get("person_name") or "Unknown Visitor").strip()
    confidence = float(event.get("confidence") or 0)
    padding = max(7, int(height * 0.018))
    label_font = load_overlay_font(max(14, int(height * 0.045)))
    badge_font = load_overlay_font(max(12, int(height * 0.035)))

    label_box = draw.textbbox((0, 0), person, font=label_font)
    label_w = label_box[2] - label_box[0]
    label_h = label_box[3] - label_box[1]
    label_bar_h = label_h + padding * 2
    label_y1 = max(0, min(height - label_bar_h, bottom - label_bar_h))
    draw.rounded_rectangle((left, label_y1, right, label_y1 + label_bar_h), radius=radius, fill=(255, 255, 255))
    label_x = left + max(0, ((right - left) - label_w) // 2)
    draw.text((label_x, label_y1 + padding), person, fill=(17, 24, 39), font=label_font)

    if confidence > 0:
        badge = f"{confidence:.1f}%"
        badge_box = draw.textbbox((0, 0), badge, font=badge_font)
        badge_w = badge_box[2] - badge_box[0]
        badge_h = badge_box[3] - badge_box[1]
        badge_pad_x = max(6, padding - 1)
        badge_pad_y = max(4, padding - 3)
        badge_w_total = badge_w + badge_pad_x * 2
        badge_h_total = badge_h + badge_pad_y * 2
        badge_x2 = min(right - stroke, width - stroke)
        badge_x1 = max(left + stroke, badge_x2 - badge_w_total)
        badge_y1 = max(top + stroke, 0)
        badge_y2 = min(height - stroke, badge_y1 + badge_h_total)
        draw.rounded_rectangle((badge_x1, badge_y1, badge_x2, badge_y2), radius=badge_h_total // 2, fill=(255, 255, 255))
        draw.text((badge_x1 + badge_pad_x, badge_y1 + badge_pad_y), badge, fill=color, font=badge_font)


def publish_mqtt_latest_image_if_configured() -> None:
    config = mqtt_config()
    if not config.configured:
        return
    try:
        latest_image = latest_mqtt_image_payload()
    except Exception:  # noqa: BLE001
        logger.exception("Building the MQTT latest image failed")
        return
    if latest_image:
        base = mqtt_homeassistant.base_topic(config)
        # Images are large and only the newest one matters, so QoS 0 is enough;
        # the bridge republishes it after every reconnect.
        mqtt_bridge.publish([(f"{base}/latest_image", latest_image, True)], qos=0)


def publish_mqtt_latest_image_async() -> None:
    threading.Thread(target=publish_mqtt_latest_image_if_configured, daemon=True).start()


def publish_mqtt_state_if_configured(publish_image: bool = True) -> None:
    config = mqtt_config()
    if not config.configured:
        return
    base = mqtt_homeassistant.base_topic(config)
    mqtt_bridge.publish([(f"{base}/state", json.dumps(current_mqtt_state(), ensure_ascii=False), True)])
    if publish_image:
        publish_mqtt_latest_image_async()


def publish_mqtt_recognition_if_configured(event_id: str, publish_image: bool = True) -> None:
    config = mqtt_config()
    if not config.configured:
        return
    base = mqtt_homeassistant.base_topic(config)
    event_payload = mqtt_event_payload(event_id)
    messages: list[tuple[str, str | bytes, bool]] = [
        (f"{base}/state", json.dumps(current_mqtt_state(), ensure_ascii=False), True),
    ]
    if event_payload:
        messages.append((f"{base}/event", json.dumps(event_payload, ensure_ascii=False), False))
    mqtt_bridge.publish(messages)
    if publish_image:
        publish_mqtt_latest_image_async()


def publish_mqtt_decision_fast(payload: dict) -> None:
    config = mqtt_config()
    if not config.configured:
        return
    base = mqtt_homeassistant.base_topic(config)
    mqtt_bridge.publish(
        [
            (f"{base}/state", json.dumps(payload, ensure_ascii=False), True),
            (f"{base}/event", json.dumps({"event_id": payload["latest_event_id"], **payload}, ensure_ascii=False), False),
        ]
    )


def mqtt_discovery_messages(config: mqtt_homeassistant.MqttConfig) -> list[tuple[str, str | bytes, bool]]:
    with connect() as conn:
        cameras = rows_to_dicts(conn.execute("SELECT * FROM cameras ORDER BY name").fetchall())
    return mqtt_homeassistant.discovery_messages(
        config,
        current_mqtt_state(),
        [serialize_camera(camera) for camera in cameras],
    )


def republish_mqtt_home_assistant(config: mqtt_homeassistant.MqttConfig, reason: str) -> int:
    """Publish discovery, availability, state and the latest image on the shared connection.

    Called by the bridge after every (re)connect and when Home Assistant restarts, so
    entities never need a manual "save MQTT settings" to come back.
    """
    messages = mqtt_discovery_messages(config)
    mqtt_bridge.publish(messages)
    publish_mqtt_latest_image_if_configured()
    with connect() as conn:
        add_log(conn, "System", "info", f"Published Home Assistant discovery after {reason}")
    return len(messages)


def record_mqtt_status(severity: str, message: str) -> None:
    with connect() as conn:
        add_log(conn, "System", severity, message)


def publish_mqtt_discovery_if_configured(reason: str, clear_trigger_slugs: list[str] | None = None) -> None:
    config = mqtt_config()
    if not config.configured:
        return
    try:
        messages = mqtt_discovery_messages(config)
    except Exception as error:  # noqa: BLE001
        logger.exception("Building Home Assistant discovery failed")
        with connect() as conn:
            add_log(conn, "System", "error", f"MQTT discovery failed after {reason}: {error}")
        return
    for trigger_slug in clear_trigger_slugs or []:
        clear_message = mqtt_homeassistant.camera_trigger_discovery_clear_message(config, trigger_slug)
        if clear_message:
            messages.append(clear_message)
    mqtt_bridge.publish(messages)
    with connect() as conn:
        if mqtt_bridge.connected:
            add_log(conn, "System", "info", f"Published Home Assistant discovery after {reason}")
        else:
            add_log(conn, "System", "warn", f"MQTT offline; discovery after {reason} queued until it reconnects")


def publish_mqtt_discovery_async(reason: str, clear_trigger_slugs: list[str] | None = None) -> None:
    threading.Thread(
        target=publish_mqtt_discovery_if_configured,
        args=(reason, clear_trigger_slugs),
        daemon=True,
    ).start()


def restart_mqtt_command_listener() -> None:
    """(Re)start the shared MQTT connection with the saved settings."""
    try:
        mqtt_bridge.restart(mqtt_config())
    except mqtt_homeassistant.MqttError as error:
        with connect() as conn:
            add_log(conn, "System", "error", f"MQTT connection could not be started: {error}")


def handle_mqtt_camera_trigger(trigger_slug: str) -> None:
    try:
        event = request_camera_trigger(trigger_slug, source="MQTT")
        with connect() as conn:
            add_log(conn, "Recognition", "info", f"MQTT manual trigger accepted for {event['camera_name']}")
    except HTTPException as error:
        with connect() as conn:
            add_log(conn, "Recognition", "warn", f"MQTT manual trigger failed for {trigger_slug}: {error.detail}")


def backfill_camera_slugs() -> None:
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM cameras ORDER BY created_at, name").fetchall())
        for row in rows:
            updates: dict[str, str] = {}
            if not row.get("trigger_slug"):
                updates["trigger_slug"] = unique_camera_slug(conn, row["name"], row["id"])
            if not row.get("still_url") and row.get("stream_url"):
                updates["still_url"] = row["stream_url"]
            if updates:
                conn.execute(
                    "UPDATE cameras SET trigger_slug = ?, still_url = ? WHERE id = ?",
                    (updates.get("trigger_slug", row.get("trigger_slug", "")), updates.get("still_url", row.get("still_url", "")), row["id"]),
                )


def normalize_stored_upload_paths() -> None:
    with connect() as conn:
        for table, columns in {
            "events": ("image_path", "thumb_path", "face_crop_path"),
            "unknown_visitors": ("image_path",),
            "person_faces": ("image_path", "source_image_path"),
        }.items():
            for column in columns:
                rows = conn.execute(
                    f"SELECT id, {column} AS path FROM {table} WHERE {column} LIKE '%\\%'"
                ).fetchall()
                for row in rows:
                    conn.execute(
                        f"UPDATE {table} SET {column} = ? WHERE id = ?",
                        (normalize_upload_ref(row["path"]), row["id"]),
                    )


def rebuild_missing_embeddings() -> None:
    config = insightface_config()
    with connect() as conn:
        faces = rows_to_dicts(
            conn.execute(
                "SELECT id, person_id, image_path, source_image_path FROM person_faces WHERE embedding = '' OR embedding_model != ?",
                (config.model_name,),
            ).fetchall()
        )
    if not faces:
        return
    rebuilt = 0
    for face in faces:
        try:
            indexed = index_stored_face(config, face)
        except insightface_engine.InsightFaceError:
            continue
        with connect() as conn:
            conn.execute(
                "UPDATE person_faces SET face_id = ?, embedding = ?, embedding_model = ? WHERE id = ?",
                (indexed["face_id"], indexed["embedding"], config.model_name, face["id"]),
            )
        rebuilt += 1
    with connect() as conn:
        conn.execute(
            """
            UPDATE people
            SET indexed_faces = (
              SELECT COUNT(*) FROM person_faces pf
              WHERE pf.person_id = people.id AND pf.embedding != ''
            )
            """
        )
        add_log(conn, "InsightFace", "info", f"Rebuilt {rebuilt} local face embeddings")


@app.on_event("startup")
def startup() -> None:
    init_db()
    insightface_engine.start_model_download("buffalo_s")
    backfill_camera_slugs()
    normalize_stored_upload_paths()
    rebuild_missing_embeddings()
    restart_mqtt_command_listener()


@app.on_event("shutdown")
def shutdown() -> None:
    mqtt_bridge.stop()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/settings")
def get_settings() -> dict:
    return public_settings()


@app.get("/api/settings/mqtt")
def get_mqtt_settings() -> dict:
    return public_mqtt_settings()


@app.put("/api/settings/mqtt")
def save_mqtt_settings(payload: MqttSettingsIn) -> dict:
    next_config: mqtt_homeassistant.MqttConfig | None = None
    with connect() as conn:
        current = get_setting(conn, "mqtt", {})
        password = payload.password if payload.password else current.get("password", "")
        next_config = mqtt_homeassistant.MqttConfig(
            host=payload.host.strip(),
            port=payload.port,
            username=payload.username.strip(),
            password=password,
            discovery_prefix=payload.discovery_prefix.strip() or "homeassistant",
            base_topic=payload.base_topic.strip() or "iris",
            device_id=payload.device_id.strip() or "iris_face_recognition",
            device_name=payload.device_name.strip() or "IRIS Face Recognition",
            use_tls=payload.use_tls,
        )
        set_setting(
            conn,
            "mqtt",
            {
                "host": next_config.host,
                "port": next_config.port,
                "username": next_config.username,
                "password": password,
                "discovery_prefix": next_config.discovery_prefix,
                "base_topic": next_config.base_topic,
                "device_id": next_config.device_id,
                "device_name": next_config.device_name,
                "use_tls": next_config.use_tls,
            },
        )
        add_log(conn, "System", "info", f"Saved MQTT configuration for {next_config.host}:{next_config.port}")
    # Reconnect the shared client with the new settings. Discovery, state and the latest
    # image are republished automatically as soon as the broker accepts the connection.
    restart_mqtt_command_listener()
    if next_config.configured and not mqtt_bridge.wait_until_connected(8):
        detail = mqtt_bridge.status().get("last_error") or f"No answer from {next_config.host}:{next_config.port}"
        raise HTTPException(
            status_code=400,
            detail=f"Settings saved, but MQTT is not connected yet ({detail}). IRIS keeps retrying in the background.",
        )
    return public_mqtt_settings()


@app.post("/api/settings/mqtt/test")
def test_mqtt_settings() -> dict:
    try:
        mqtt_homeassistant.test_connection(mqtt_config())
    except mqtt_homeassistant.MqttError as error:
        with connect() as conn:
            add_log(conn, "System", "error", f"MQTT connection failed: {error}")
        raise HTTPException(status_code=400, detail=str(error)) from error
    with connect() as conn:
        add_log(conn, "System", "info", "MQTT connection OK")
    return {"ok": True}


@app.post("/api/settings/mqtt/discovery")
def publish_home_assistant_discovery() -> dict:
    config = mqtt_config()
    if not config.configured:
        raise HTTPException(status_code=400, detail="MQTT is not configured.")
    if not mqtt_bridge.connected:
        detail = mqtt_bridge.status().get("last_error") or "not connected"
        raise HTTPException(status_code=400, detail=f"MQTT is not connected ({detail}).")
    count = republish_mqtt_home_assistant(config, "manual request")
    return {"ok": True, "entities": count - 2}


@app.get("/api/mqtt/status")
def get_mqtt_status() -> dict:
    return mqtt_bridge.status()


@app.get("/api/mqtt/messages")
def get_mqtt_messages(limit: Annotated[int, Query(ge=1, le=200)] = 100) -> dict:
    return {"status": mqtt_bridge.status(), "messages": mqtt_bridge.messages(limit)}


@app.delete("/api/mqtt/messages")
def clear_mqtt_messages() -> dict:
    mqtt_bridge.clear_messages()
    return {"ok": True}


@app.get("/api/settings/telegram")
def get_telegram_settings() -> dict:
    return public_telegram_settings()


@app.put("/api/settings/telegram")
def save_telegram_settings(payload: TelegramSettingsIn) -> dict:
    with connect() as conn:
        current = get_setting(conn, "telegram", {})
        bot_token = payload.bot_token.strip() if payload.bot_token.strip() else current.get("bot_token", "")
        chat_id = payload.chat_id.strip()
        set_setting(conn, "telegram", {"bot_token": bot_token, "chat_id": chat_id})
        add_log(conn, "System", "info", f"Saved Telegram configuration for chat {chat_id}")
    return public_telegram_settings()


@app.post("/api/settings/telegram/test")
def test_telegram_settings() -> dict:
    config = telegram_config()
    try:
        result = telegram_notify.test_connection(config)
    except telegram_notify.TelegramError as error:
        with connect() as conn:
            add_log(conn, "System", "error", f"Telegram test failed: {error}")
        raise HTTPException(status_code=400, detail=str(error)) from error
    with connect() as conn:
        add_log(conn, "System", "info", f"Telegram connection OK (@{result.get('bot_username', '?')})")
    return result


def rebuild_model_embeddings(config: dict, faces: list[dict]) -> None:
    runtime_config = insightface_engine.InsightFaceConfig(**config)
    try:
        rebuilt: list[tuple[str, dict]] = []
        failures: list[str] = []
        for position, face in enumerate(faces, start=1):
            try:
                indexed = index_stored_face(runtime_config, face)
                rebuilt.append((face["id"], indexed))
            except insightface_engine.InsightFaceError:
                failures.append(face["id"])
            with model_rebuild_lock:
                model_rebuild_status["processed"] = position
                model_rebuild_status["progress"] = round(position * 100 / len(faces)) if faces else 100
        if failures:
            raise insightface_engine.InsightFaceError(
                f"Failed to rebuild {len(failures)} reference face(s). Model was not changed."
            )
        with connect() as conn:
            for face_id, indexed in rebuilt:
                conn.execute(
                    "UPDATE person_faces SET face_id = ?, embedding = ?, embedding_model = ? WHERE id = ?",
                    (indexed["face_id"], indexed["embedding"], config["model_name"], face_id),
                )
            set_setting(conn, "insightface", config)
            add_log(conn, "InsightFace", "info", f"Rebuilt {len(rebuilt)} face embeddings for {config['model_name']}")
        with model_rebuild_lock:
            model_rebuild_status.update(status="completed", progress=100, error=None)
    except Exception as error:  # noqa: BLE001
        with connect() as conn:
            add_log(conn, "InsightFace", "error", f"Model change aborted: {error}")
        with model_rebuild_lock:
            model_rebuild_status.update(status="error", error=str(error))


@app.put("/api/settings/insightface")
def save_insightface_settings(payload: InsightFaceSettingsIn) -> dict:
    config = payload.model_dump()
    runtime_config = insightface_engine.InsightFaceConfig(**config)
    with model_rebuild_lock:
        if model_rebuild_status["status"] == "running":
            raise HTTPException(status_code=409, detail="A model rebuild is already running.")
    insightface_engine.clear_engine_cache()
    try:
        insightface_engine.validate_config(runtime_config)
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with connect() as conn:
        previous = get_setting(conn, "insightface", {})
        faces = rows_to_dicts(
            conn.execute("SELECT id, person_id, image_path, source_image_path FROM person_faces").fetchall()
        )
    if previous.get("model_name", "buffalo_s") != payload.model_name:
        with model_rebuild_lock:
            model_rebuild_status.update(
                status="running",
                model_name=payload.model_name,
                processed=0,
                total=len(faces),
                progress=0,
                error=None,
            )
            response = dict(model_rebuild_status)
        threading.Thread(target=rebuild_model_embeddings, args=(config, faces), daemon=True).start()
        return response
    with connect() as conn:
        set_setting(conn, "insightface", config)
        add_log(conn, "InsightFace", "info", f"Saved model {payload.model_name} with {payload.provider}")
    return public_settings()


@app.get("/api/settings/insightface/rebuild")
def get_model_rebuild_status() -> dict:
    with model_rebuild_lock:
        return dict(model_rebuild_status)


@app.post("/api/settings/insightface/test")
def test_insightface() -> dict:
    try:
        insightface_engine.validate_config(insightface_config())
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"ok": True}


@app.get("/api/settings/insightface/models")
def get_insightface_models() -> list[dict]:
    return insightface_engine.model_download_status()


@app.post("/api/settings/insightface/models/{model_name}/download", status_code=202)
def download_insightface_model(model_name: str) -> dict:
    try:
        return insightface_engine.start_model_download(model_name)
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/settings/insightface/models/{model_name}")
def delete_insightface_model(model_name: str) -> dict:
    try:
        return insightface_engine.delete_model(model_name)
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/settings/thresholds")
def save_thresholds(payload: ThresholdsIn) -> dict:
    if payload.auto_accept < payload.match:
        raise HTTPException(status_code=400, detail="Auto-accept must be greater than or equal to match threshold.")
    with connect() as conn:
        set_setting(conn, "thresholds", payload.model_dump())
        add_log(conn, "System", "info", f"Updated thresholds: match {payload.match}, auto {payload.auto_accept}")
    return public_settings()


@app.get("/api/settings/storage")
def get_storage_settings() -> dict:
    return storage_status()


@app.put("/api/settings/storage")
def save_storage_settings(payload: StorageSettingsIn) -> dict:
    with connect() as conn:
        set_setting(conn, "storage", {"max_storage_mb": payload.max_storage_mb})
        add_log(conn, "System", "info", f"Updated storage quota to {payload.max_storage_mb} MB")
    cleanup = cleanup_storage_to_quota()
    return storage_status() | {"cleanup": cleanup}


@app.post("/api/settings/storage/cleanup")
def cleanup_storage() -> dict:
    cleanup = cleanup_storage_to_quota()
    publish_mqtt_state_if_configured()
    return storage_status() | {"cleanup": cleanup}


@app.post("/api/settings/data/clear")
def clear_all_data() -> dict:
    with model_rebuild_lock:
        if model_rebuild_status["status"] == "running":
            raise HTTPException(status_code=409, detail="Cannot clear data while embeddings are rebuilding.")
    try:
        insightface_engine.reset_model_storage()
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    clear_database()
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    init_db()
    with model_rebuild_lock:
        model_rebuild_status.update(
            status="idle", model_name="", processed=0, total=0, progress=0, error=None
        )
    restart_mqtt_command_listener()
    return {"ok": True}


@app.get("/api/summary")
def summary() -> dict:
    with connect() as conn:
        people_count = conn.execute("SELECT COUNT(*) AS c FROM people").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) AS c FROM people WHERE status = 'Active'").fetchone()["c"]
        events_today = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        unknown = conn.execute("SELECT COUNT(*) AS c FROM unknown_visitors").fetchone()["c"]
        latest = row_to_dict(conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 1").fetchone())
    return {"people": people_count, "activePeople": active, "events": events_today, "unknown": unknown, "latest": latest}


@app.get("/api/dashboard")
def dashboard() -> dict:
    with connect() as conn:
        people_count = conn.execute("SELECT COUNT(*) AS c FROM people").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) AS c FROM people WHERE status = 'Active'").fetchone()["c"]
        events_count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        unknown = conn.execute("SELECT COUNT(*) AS c FROM unknown_visitors").fetchone()["c"]
        latest_events = rows_to_dicts(
            conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 6").fetchall()
        )
        indexed_faces = conn.execute("SELECT COUNT(*) AS c FROM person_faces").fetchone()["c"]
        average_processing_ms = conn.execute(
            "SELECT COALESCE(AVG(processing_ms), 0) AS value FROM events WHERE processing_ms > 0"
        ).fetchone()["value"]
    settings = public_settings()
    mqtt = public_mqtt_settings()
    telegram = public_telegram_settings()
    return {
        "summary": {
            "people": people_count,
            "activePeople": active,
            "events": events_count,
            "unknown": unknown,
            "latest": latest_events[0] if latest_events else None,
        },
        "events": latest_events,
        "local_inference": {
            "indexed_faces": indexed_faces,
            "model": settings["model_name"],
            "provider": settings["provider"],
            "average_processing_ms": round(float(average_processing_ms), 1),
        },
        "services": {
            "system": True,
            "insightface": bool(settings["insightface_configured"]),
            "mqtt": bool(mqtt["configured"]),
            "telegram": bool(telegram["configured"]),
        },
    }


@app.get("/api/analytics")
def analytics(
    days: Annotated[int, Query(ge=1, le=365)] = 7,
    tz_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
) -> dict:
    """Recognition statistics for the analytics page.

    ``tz_offset_minutes`` is the browser's UTC offset (e.g. +420 for Vietnam) so daily and
    hourly buckets follow the viewer's local time instead of UTC.
    """
    local_tz = timezone(timedelta(minutes=tz_offset_minutes))
    now_local = datetime.now(local_tz)
    first_day = (now_local - timedelta(days=days - 1)).date()
    since_utc = datetime.combine(first_day, datetime.min.time(), tzinfo=local_tz).astimezone(timezone.utc)
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT type, person_id, person_name, confidence, processing_ms, camera_name, event_time
                FROM events
                WHERE event_time >= ? AND type IN ('known', 'review', 'unknown', 'no_face')
                ORDER BY event_time
                """,
                (since_utc.isoformat(),),
            ).fetchall()
        )
    kinds = ("known", "review", "unknown", "no_face")
    daily: dict[str, dict] = {}
    for offset in range(days):
        key = (first_day + timedelta(days=offset)).isoformat()
        daily[key] = {"date": key, "total": 0, **{kind: 0 for kind in kinds}}
    hourly = [{"hour": hour, "count": 0} for hour in range(24)]
    people: dict[str, dict] = {}
    cameras: dict[str, int] = {}
    totals = {kind: 0 for kind in kinds}
    known_confidences: list[float] = []
    processing: list[float] = []
    for row in rows:
        try:
            moment = datetime.fromisoformat(str(row["event_time"]).replace("Z", "+00:00")).astimezone(local_tz)
        except ValueError:
            continue
        kind = row["type"]
        bucket = daily.get(moment.date().isoformat())
        if bucket is None:
            continue
        bucket[kind] += 1
        bucket["total"] += 1
        totals[kind] += 1
        hourly[moment.hour]["count"] += 1
        camera = row.get("camera_name") or "Unknown camera"
        cameras[camera] = cameras.get(camera, 0) + 1
        if row.get("processing_ms"):
            processing.append(float(row["processing_ms"]))
        if kind in ("known", "review") and row.get("person_id"):
            entry = people.setdefault(
                row["person_id"],
                {"person_id": row["person_id"], "person_name": row["person_name"], "count": 0, "confidence_sum": 0.0, "last_seen": ""},
            )
            entry["count"] += 1
            entry["confidence_sum"] += float(row.get("confidence") or 0)
            entry["last_seen"] = max(entry["last_seen"], str(row["event_time"]))
            entry["person_name"] = row["person_name"] or entry["person_name"]
            if kind == "known":
                known_confidences.append(float(row.get("confidence") or 0))
    top_people = sorted(people.values(), key=lambda item: (-item["count"], item["person_name"] or ""))[:10]
    for entry in top_people:
        entry["avg_confidence"] = round(entry.pop("confidence_sum") / entry["count"], 1) if entry["count"] else 0
    total = sum(totals.values())
    faces = totals["known"] + totals["review"] + totals["unknown"]
    return {
        "days": days,
        "summary": {
            "total": total,
            **totals,
            "unique_people": len(people),
            "recognized_rate": round((totals["known"] + totals["review"]) / faces * 100, 1) if faces else 0,
            "avg_known_confidence": round(sum(known_confidences) / len(known_confidences), 1) if known_confidences else 0,
            "avg_processing_ms": round(sum(processing) / len(processing), 1) if processing else 0,
        },
        "daily": list(daily.values()),
        "hourly": hourly,
        "top_people": top_people,
        "cameras": [
            {"camera_name": name, "count": count}
            for name, count in sorted(cameras.items(), key=lambda item: -item[1])[:10]
        ],
    }


@app.get("/api/people")
def list_people() -> list[dict]:
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT
                  p.*,
                  (
                    SELECT pf.face_id
                    FROM person_faces pf
                    WHERE pf.person_id = p.id
                    ORDER BY pf.created_at DESC
                    LIMIT 1
                  ) AS preview_face_id,
                  COALESCE(
                    (
                      SELECT COALESCE(NULLIF(e.face_crop_path, ''), NULLIF(e.thumb_path, ''), e.image_path)
                      FROM events e
                      WHERE e.person_id = p.id
                        AND (e.image_path != '' OR e.thumb_path != '' OR e.face_crop_path != '')
                      ORDER BY e.created_at DESC
                      LIMIT 1
                    ),
                    (
                      SELECT pf.image_path
                      FROM person_faces pf
                      WHERE pf.person_id = p.id AND pf.image_path != ''
                      ORDER BY pf.created_at DESC
                      LIMIT 1
                    ),
                    ''
                  ) AS preview_image_path
                FROM people p
                ORDER BY p.name
                """
            ).fetchall()
        )
    return [
        serialize_person(
            row,
            row.get("preview_face_id") or "",
            row.get("preview_image_path") or "",
        )
        for row in rows
    ]


@app.post("/api/people")
def create_person(payload: PersonIn) -> dict:
    now = utc_now()
    person_id = normalize_person_id(payload.name)
    if not person_id:
        raise HTTPException(status_code=400, detail="Person ID must contain at least one letter or number.")
    name = person_id
    alias = payload.alias.strip()
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM people WHERE id = ? LIMIT 1", (person_id,)).fetchone()
        if exists:
            raise HTTPException(status_code=400, detail={"code": "person_id_exists", "message": "Person ID already exists."})
        conn.execute(
            """
            INSERT INTO people (id, name, alias, role, notes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (person_id, name, alias, payload.role, payload.notes, payload.status, now, now),
        )
        add_log(conn, "Recognition", "info", f"Created person {alias or name}")
        row = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
    publish_mqtt_state_if_configured()
    return serialize_person(row or {})


@app.get("/api/people/{person_id}")
def get_person(person_id: str) -> dict:
    with connect() as conn:
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
        faces = rows_to_dicts(conn.execute("SELECT id, person_id, face_id, image_path, created_at FROM person_faces WHERE person_id = ? ORDER BY created_at DESC", (person_id,)).fetchall())
        events = rows_to_dicts(conn.execute("SELECT * FROM events WHERE person_id = ? ORDER BY created_at DESC", (person_id,)).fetchall())
        face_ids, latest_images = person_preview_data(conn, [person_id])
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    return {
        **serialize_person(person, face_ids.get(person_id, ""), latest_images.get(person_id, "")),
        "faces": faces,
        "events": events,
    }


@app.put("/api/people/{person_id}")
def update_person(person_id: str, payload: PersonIn) -> dict:
    now = utc_now()
    name = payload.name.strip()
    alias = payload.alias.strip()
    with connect() as conn:
        current = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
        if current is None:
            raise HTTPException(status_code=404, detail="Person not found.")
        conn.execute(
            "UPDATE people SET name = ?, alias = ?, role = ?, notes = ?, status = ?, updated_at = ? WHERE id = ?",
            (name, alias, payload.role, payload.notes, payload.status, now, person_id),
        )
        add_log(conn, "Recognition", "info", f"Updated person {alias or name}")
        row = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
    publish_mqtt_state_if_configured()
    return serialize_person(row or {})


@app.delete("/api/people/{person_id}")
def delete_person(person_id: str) -> dict:
    with connect() as conn:
        face_rows = rows_to_dicts(
            conn.execute(
                "SELECT face_id, image_path, source_image_path FROM person_faces WHERE person_id = ?",
                (person_id,),
            ).fetchall()
        )
        image_paths = [path for row in face_rows for path in (row.get("image_path") or "", row.get("source_image_path") or "")]
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found.")
    with connect() as conn:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        add_log(conn, "Recognition", "warn", f"Deleted person {person['name']}")
    deleted_files = delete_unreferenced_uploads(image_paths)
    if deleted_files:
        with connect() as conn:
            add_log(conn, "System", "info", f"Removed {deleted_files} unreferenced person image(s)")
    publish_mqtt_state_if_configured()
    return {"ok": True}


@app.post("/api/people/{person_id}/faces")
def upload_person_face(person_id: str, file: Annotated[UploadFile, File()]) -> dict:
    with connect() as conn:
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    rel_path, image = save_upload(file, f"people/{person_id}")
    try:
        indexed = insightface_engine.index_face(insightface_config(), image, person_id)
    except insightface_engine.InsightFaceError as error:
        with connect() as conn:
            add_log(conn, "InsightFace", "error", str(error))
        raise HTTPException(status_code=400, detail=str(error)) from error
    source_image_path = save_image_bytes(image, f"face_sources/{person_id}")
    crop_saved_image_to_face(rel_path, indexed.get("bounding_box"))
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO person_faces (id, person_id, face_id, embedding, image_path, source_image_path, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("face"), person_id, indexed["face_id"], indexed["embedding"], rel_path, source_image_path, insightface_config().model_name, now),
        )
        conn.execute("UPDATE people SET indexed_faces = indexed_faces + 1, updated_at = ? WHERE id = ?", (now, person_id))
        add_log(conn, "InsightFace", "info", f"Indexed face for {person['name']} ({indexed['face_id']})")
    publish_mqtt_state_if_configured()
    return {"ok": True, "face_id": indexed["face_id"], "confidence": indexed["confidence"], "bounding_box": indexed["bounding_box"], "image_path": rel_path}


@app.delete("/api/people/{person_id}/faces/{face_id}")
def delete_person_face(person_id: str, face_id: str) -> dict:
    with connect() as conn:
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
        face = row_to_dict(
            conn.execute(
                "SELECT * FROM person_faces WHERE id = ? AND person_id = ?",
                (face_id, person_id),
            ).fetchone()
        )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    if face is None:
        raise HTTPException(status_code=404, detail="Face not found.")

    image_path = face.get("image_path") or ""
    now = utc_now()
    with connect() as conn:
        conn.execute("DELETE FROM person_faces WHERE id = ? AND person_id = ?", (face_id, person_id))
        count = conn.execute("SELECT COUNT(*) AS c FROM person_faces WHERE person_id = ?", (person_id,)).fetchone()["c"]
        conn.execute(
            "UPDATE people SET indexed_faces = ?, updated_at = ? WHERE id = ?",
            (count, now, person_id),
        )
        add_log(conn, "InsightFace", "warn", f"Deleted face for {person['name']} ({face.get('face_id') or face_id})")

    deleted_files = delete_unreferenced_uploads([image_path, face.get("source_image_path") or ""])
    if deleted_files:
        with connect() as conn:
            add_log(conn, "System", "info", f"Removed {deleted_files} unreferenced face image(s)")
    publish_mqtt_state_if_configured()
    return {"ok": True}


@app.get("/api/events")
def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    event_type: str = "",
    camera_id: str = "",
    person_id: str = "",
) -> dict:
    where: list[str] = []
    params: list[str] = []
    if event_type:
        where.append("type = ?")
        params.append(event_type)
    if camera_id:
        where.append("camera_id = ?")
        params.append(camera_id)
    if person_id:
        if person_id == "unknown":
            where.append("person_id IS NULL")
        else:
            where.append("person_id = ?")
            params.append(person_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM events {where_sql}", params).fetchone()["c"]
        total_pages = max(1, (total + limit - 1) // limit)
        current_page = min(page, total_pages)
        offset = (current_page - 1) * limit
        rows = rows_to_dicts(
            conn.execute(
                f"SELECT * FROM events {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        )
    return {
        "items": rows,
        "page": current_page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
    }


@app.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict:
    with connect() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        if row is not None:
            row["is_trained"] = event_has_trained_face(conn, row)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return row


def event_has_trained_face(conn: sqlite3.Connection, event: dict) -> bool:
    paths = [event.get("face_crop_path") or "", event.get("image_path") or ""]
    paths = [path for path in paths if path]
    if not paths:
        return False
    placeholders = ",".join("?" for _ in paths)
    row = conn.execute(
        f"SELECT 1 FROM person_faces WHERE image_path IN ({placeholders}) LIMIT 1",
        paths,
    ).fetchone()
    return row is not None


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str) -> dict:
    with connect() as conn:
        event = row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        image_paths = [event.get("image_path") or "", event.get("thumb_path") or "", event.get("face_crop_path") or ""]
        unknown_paths = [
            row["image_path"]
            for row in conn.execute(
                "SELECT image_path FROM unknown_visitors WHERE event_id = ? AND image_path != ''",
                (event_id,),
            ).fetchall()
        ]
        image_paths.extend(unknown_paths)
        conn.execute("DELETE FROM unknown_visitors WHERE event_id = ?", (event_id,))
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        add_log(conn, "Recognition", "warn", f"Deleted event {event_id}")
    deleted_files = delete_unreferenced_uploads(image_paths)
    if deleted_files:
        with connect() as conn:
            add_log(conn, "System", "info", f"Removed {deleted_files} unreferenced event image(s)")
    publish_mqtt_state_if_configured()
    return {"ok": True}


def event_face_box_in_original(event: dict) -> dict | None:
    """Bounding box of the event's face relative to the original image.

    ``face_details_json`` keeps the box from detection time (original coordinates). The
    ``face_bounding_box`` column is rewritten relative to the face crop once thumbnails are
    made, so it is only usable while no crop exists yet.
    """
    try:
        details = json.loads(event.get("face_details_json") or "{}")
    except (TypeError, ValueError):
        details = {}
    box = details.get("bounding_box") if isinstance(details, dict) else None
    if isinstance(box, dict) and box.get("Width"):
        return box
    if not event.get("face_crop_path"):
        try:
            box = json.loads(event.get("face_bounding_box") or "null")
        except (TypeError, ValueError):
            box = None
        if isinstance(box, dict) and box.get("Width"):
            return box
    return None


def index_stored_face(config: insightface_engine.InsightFaceConfig, face: dict) -> dict:
    """Re-index a stored reference face for a new model.

    The face crop is tried first because it is centred on the trained person, while the
    source image can be a group photo where the largest face is someone else.
    """
    candidates = [face.get("image_path"), face.get("source_image_path")]
    last_error: Exception | None = None
    for candidate in dict.fromkeys(item for item in candidates if item):
        path = safe_upload_path(candidate)
        if not path or not path.exists():
            continue
        try:
            return insightface_engine.index_face(config, path.read_bytes(), face["person_id"])
        except insightface_engine.InsightFaceError as error:
            last_error = error
    raise insightface_engine.InsightFaceError(str(last_error) if last_error else "Reference image file not found.")


def train_event_face_to_person(event_id: str, person_id: str) -> dict:
    with connect() as conn:
        event = row_to_dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
        already_trained = event_has_trained_face(conn, event) if event else False
    if event is None or person is None:
        raise HTTPException(status_code=404, detail="Event or person not found.")
    if already_trained:
        raise HTTPException(status_code=400, detail="This event has already been trained.")
    image_path = event.get("image_path") or ""
    if not image_path:
        raise HTTPException(status_code=400, detail="This event does not have a saved image to train.")
    file_path = safe_upload_path(image_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Event image file not found.")

    try:
        indexed = insightface_engine.index_face(
            insightface_config(), file_path.read_bytes(), person_id, event_face_box_in_original(event)
        )
    except insightface_engine.InsightFaceError as error:
        with connect() as conn:
            add_log(conn, "InsightFace", "error", str(error))
        raise HTTPException(status_code=400, detail=str(error)) from error
    thumb_path, face_crop_path, face_bounding_box = create_event_images(image_path, indexed.get("bounding_box"))
    face_image_path = face_crop_path or event.get("face_crop_path") or image_path
    face_bounding_box_json = json.dumps(face_bounding_box) if face_bounding_box else (event.get("face_bounding_box") or "")

    now = utc_now()
    person_name = display_person_name(person)
    with connect() as conn:
        conn.execute(
            "INSERT INTO person_faces (id, person_id, face_id, embedding, image_path, source_image_path, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("face"), person_id, indexed["face_id"], indexed["embedding"], face_image_path, image_path, insightface_config().model_name, now),
        )
        conn.execute(
            "UPDATE people SET indexed_faces = indexed_faces + 1, updated_at = ? WHERE id = ?",
            (now, person_id),
        )
        conn.execute(
            """
            UPDATE events
            SET person_id = ?,
                person_name = ?,
                type = 'known',
                face_id = ?,
                face_bounding_box = ?,
                thumb_path = COALESCE(NULLIF(thumb_path, ''), ?),
                face_crop_path = ?,
                event_time = ?
            WHERE id = ?
            """,
            (person_id, person_name, indexed["face_id"], face_bounding_box_json, thumb_path, face_image_path, now, event_id),
        )
        conn.execute("DELETE FROM unknown_visitors WHERE event_id = ?", (event_id,))
        add_log(conn, "Recognition", "info", f"Trained event {event_id} face for {person_name}")
    publish_mqtt_state_if_configured()
    return {"ok": True, **indexed, "event": get_event(event_id)}


@app.post("/api/events/{event_id}/train/{person_id}")
def train_event_face(event_id: str, person_id: str) -> dict:
    return train_event_face_to_person(event_id, person_id)


def create_event_shell(
    camera_id: str,
    camera_name: str,
    person_name: str = "Processing trigger",
    event_type: str = "processing",
    update_camera: bool = True,
) -> dict:
    now = utc_now()
    event_id = new_id("evt")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events
            (id, person_name, confidence, camera_id, camera_name, type, inference_id, image_path, event_time, created_at)
            VALUES (?, ?, 0, ?, ?, ?, '', '', ?, ?)
            """,
            (event_id, person_name, camera_id, camera_name, event_type, now, now),
        )
        if camera_id and update_camera:
            conn.execute("UPDATE cameras SET last_detection = ?, updated_at = ? WHERE id = ?", (now, now, camera_id))
        add_log(conn, "Recognition", "info", f"Accepted trigger from {camera_name}")
    return get_event(event_id)


def mark_event_failed(
    event_id: str,
    person_name: str,
    camera_name: str,
    message: str,
    rel_path: str = "",
    event_type: str = "error",
    camera_id: str = "",
    publish: bool = True,
    processing_ms: float = 0,
) -> dict:
    now = utc_now()
    thumb_path, face_crop_path, _ = create_event_images(rel_path, None)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events
            (id, person_name, confidence, camera_id, camera_name, type, inference_id, processing_ms, image_path, thumb_path, face_crop_path, event_time, created_at)
            VALUES (?, ?, 0, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              person_id = NULL,
              person_name = excluded.person_name,
              confidence = 0,
              camera_id = COALESCE(NULLIF(excluded.camera_id, ''), camera_id),
              camera_name = excluded.camera_name,
              type = excluded.type,
              face_id = NULL,
              inference_id = '',
              processing_ms = excluded.processing_ms,
              image_path = excluded.image_path,
              thumb_path = excluded.thumb_path,
              face_crop_path = excluded.face_crop_path,
              original_deleted_at = NULL,
              event_time = excluded.event_time
            """,
            (event_id, person_name, camera_id, camera_name, event_type, processing_ms, rel_path, thumb_path, face_crop_path, now, now),
        )
        add_log(conn, "Recognition", "warn", f"{message} at {camera_name}")
    if publish:
        publish_mqtt_recognition_if_configured(event_id)
    return get_event(event_id)


def is_no_face_error(error: Exception) -> bool:
    message = str(error).lower()
    return "no face" in message or "no faces" in message or "there are no faces" in message


def send_telegram_for_event(event: dict, person_name: str, event_type: str, confidence: float, rel_path: str) -> None:
    tg_config = telegram_config()
    if not tg_config.configured:
        return
    abs_image = str(UPLOAD_DIR / rel_path) if rel_path else None
    telegram_notify.send_recognition_alert(
        tg_config,
        person_name=person_name,
        confidence=confidence,
        event_type=event_type,
        camera_name=event.get("camera_name") or "Manual upload",
        event_time=event.get("event_time") or utc_now(),
        image_path=abs_image,
    )


def finalize_recognition_event(
    event_id: str,
    rel_path: str,
    bounding_box: dict | None,
    details: dict,
    notify: bool,
) -> None:
    thumb_path, face_crop_path, adjusted_box = create_event_images(rel_path, bounding_box)
    with connect() as conn:
        conn.execute(
            "UPDATE events SET thumb_path = ?, face_crop_path = ?, face_bounding_box = ?, face_details_json = ? WHERE id = ?",
            (
                thumb_path,
                face_crop_path,
                json.dumps(adjusted_box) if adjusted_box else "",
                json.dumps(details, ensure_ascii=False) if details else "",
                event_id,
            ),
        )
    if notify:
        publish_mqtt_latest_image_if_configured()


def finalize_recognition_event_async(
    event_id: str,
    rel_path: str,
    bounding_box: dict | None,
    details: dict,
    notify: bool,
) -> None:
    threading.Thread(
        target=finalize_recognition_event,
        args=(event_id, rel_path, bounding_box, details, notify),
        daemon=True,
    ).start()


def recognize_image_bytes(
    image: bytes,
    rel_path: str,
    camera_id: str = "",
    camera_name: str = "Manual upload",
    event_id: str | None = None,
    notify: bool = True,
) -> dict:
    with connect() as conn:
        thresholds = get_setting(conn, "thresholds", {"match": 40, "auto_accept": 55})
        references = rows_to_dicts(
            conn.execute(
                """
                SELECT pf.face_id, pf.person_id, pf.embedding
                FROM person_faces pf
                JOIN people p ON p.id = pf.person_id
                WHERE p.status = 'Active'
                """
            ).fetchall()
        )
    event_id = event_id or new_id("evt")
    recognition_started = time.perf_counter()
    try:
        result = insightface_engine.search_faces(insightface_config(), image, references, thresholds["match"])
    except insightface_engine.InsightFaceError as error:
        processing_ms = round((time.perf_counter() - recognition_started) * 1000, 2)
        if is_no_face_error(error):
            event = mark_event_failed(
                event_id,
                "No face detected",
                camera_name,
                "No face detected",
                rel_path,
                "no_face",
                camera_id,
                publish=notify,
                processing_ms=processing_ms,
            )
            if notify:
                send_telegram_for_event(event, "No face detected", "no_face", 0, rel_path)
            enforce_storage_quota()
            event = get_event(event_id)
            return event | {"unknown_id": None}
        with connect() as conn:
            add_log(conn, "InsightFace", "error", str(error))
        raise HTTPException(status_code=400, detail=str(error)) from error
    processing_ms = round((time.perf_counter() - recognition_started) * 1000, 2)
    if not result.get("face_detected") or not result.get("faces"):
        event = mark_event_failed(
            event_id, "No face detected", camera_name, "No face detected", rel_path, "no_face", camera_id, publish=notify,
            processing_ms=processing_ms,
        )
        if notify:
            send_telegram_for_event(event, "No face detected", "no_face", 0, rel_path)
        enforce_storage_quota()
        return get_event(event_id) | {"unknown_id": None, "additional_events": []}

    # One event per recognized face. The largest face keeps the requested event id so
    # camera triggers and the API keep working; extra faces get their own events.
    faces = result["faces"]
    event_ids = [event_id] + [new_id("evt") for _ in faces[1:]]
    stored = [
        store_face_event(face, face_event_id, rel_path, camera_id, camera_name, processing_ms, thresholds)
        for face, face_event_id in zip(faces, event_ids)
    ]
    if len(faces) > 1:
        with connect() as conn:
            add_log(conn, "Recognition", "info", f"{len(faces)} faces recognized in one image from {camera_name}")

    # Publish extra faces first and the largest face last, so the retained MQTT state
    # (Latest Person sensor) ends on the main face while every face still gets its own
    # iris/event message.
    for face, info in reversed(list(zip(faces, stored))):
        if notify:
            publish_mqtt_decision_fast({
                "latest_event_id": info["event_id"],
                "latest_person": info["person_name"],
                "latest_person_alias": info["person_alias"],
                "latest_person_name": info["person_name"],
                "latest_person_id": info["person_id"],
                "latest_type": info["event_type"],
                "latest_decision": info["decision"],
                "latest_camera": camera_name,
                "latest_confidence": info["confidence"],
                "latest_time": info["time"],
                "latest_attributes": compact_face_attributes(face.get("face_details", {})),
                "faces_in_image": len(faces),
            })
        finalize_recognition_event_async(
            info["event_id"],
            rel_path,
            face.get("bounding_box"),
            face.get("face_details", {}),
            notify and info["event_id"] == event_id,
        )
    if notify:
        for info in stored:
            send_telegram_for_event(
                get_event(info["event_id"]),
                person_name=info["person_name"],
                confidence=info["confidence"],
                event_type=info["event_type"],
                rel_path=rel_path,
            )
    enforce_storage_quota()
    event = get_event(event_id)
    return event | {
        "unknown_id": stored[0]["unknown_id"],
        "additional_events": [get_event(info["event_id"]) for info in stored[1:]],
    }


def store_face_event(
    face: dict,
    event_id: str,
    rel_path: str,
    camera_id: str,
    camera_name: str,
    processing_ms: float,
    thresholds: dict,
) -> dict:
    """Insert (or update) the event row for one recognized face and return a summary."""
    face_bounding_box = face.get("bounding_box")
    face_bounding_box_json = json.dumps(face_bounding_box) if face_bounding_box else ""
    match = face["matches"][0] if face.get("matches") else None
    now = utc_now()
    if match:
        person_id = match["person_id"]
        confidence = float(match["similarity"])
        event_type = "known" if confidence >= thresholds["auto_accept"] else "review"
        with connect() as conn:
            person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
            person_name = display_person_name(person)
            conn.execute(
                """
                INSERT INTO events
                (id, person_id, person_name, confidence, camera_id, camera_name, type, face_id, inference_id, processing_ms, face_bounding_box, image_path, thumb_path, face_crop_path, event_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  person_id = excluded.person_id,
                  person_name = excluded.person_name,
                  confidence = excluded.confidence,
                  camera_id = excluded.camera_id,
                  camera_name = excluded.camera_name,
                  type = excluded.type,
                  face_id = excluded.face_id,
                  inference_id = excluded.inference_id,
                  processing_ms = excluded.processing_ms,
                  face_bounding_box = excluded.face_bounding_box,
                  image_path = excluded.image_path,
                  thumb_path = excluded.thumb_path,
                  face_crop_path = excluded.face_crop_path,
                  original_deleted_at = NULL,
                  event_time = excluded.event_time
                """,
                (
                    event_id,
                    person_id,
                    person_name,
                    confidence,
                    camera_id,
                    camera_name,
                    event_type,
                    match["face_id"],
                    face["inference_id"],
                    processing_ms,
                    face_bounding_box_json,
                    rel_path,
                    "",
                    "",
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE people SET total_recognitions = total_recognitions + 1, last_seen = ?, updated_at = ? WHERE id = ?",
                (now, now, person_id),
            )
            if camera_id:
                conn.execute("UPDATE cameras SET last_detection = ?, updated_at = ? WHERE id = ?", (now, now, camera_id))
            add_log(conn, "Recognition", "info", f"Match: {person_name} {confidence:.1f}% from {camera_name}")
        return {
            "event_id": event_id,
            "person_id": person_id,
            "person_name": person_name,
            "person_alias": (person.get("alias") or "") if person else "",
            "confidence": confidence,
            "event_type": event_type,
            "decision": "auto_accept" if event_type == "known" else event_type,
            "unknown_id": None,
            "time": now,
        }

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events
            (id, person_name, confidence, camera_id, camera_name, type, inference_id, processing_ms, face_bounding_box, image_path, thumb_path, face_crop_path, event_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              person_id = NULL,
              person_name = excluded.person_name,
              confidence = excluded.confidence,
              camera_id = excluded.camera_id,
              camera_name = excluded.camera_name,
              type = excluded.type,
              face_id = NULL,
              inference_id = excluded.inference_id,
              processing_ms = excluded.processing_ms,
              face_bounding_box = excluded.face_bounding_box,
              image_path = excluded.image_path,
              thumb_path = excluded.thumb_path,
              face_crop_path = excluded.face_crop_path,
              original_deleted_at = NULL,
              event_time = excluded.event_time
            """,
            (
                event_id,
                "Unknown Visitor",
                0,
                camera_id,
                camera_name,
                "unknown",
                face["inference_id"],
                processing_ms,
                face_bounding_box_json,
                rel_path,
                "",
                "",
                now,
                now,
            ),
        )
        unknown_id = new_id("uv")
        conn.execute(
            """
            INSERT INTO unknown_visitors
            (id, camera_id, camera_name, image_path, detections, event_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (unknown_id, camera_id, camera_name, rel_path, event_id, now, now),
        )
        if camera_id:
            conn.execute("UPDATE cameras SET last_detection = ?, updated_at = ? WHERE id = ?", (now, now, camera_id))
        add_log(conn, "Recognition", "warn", f"No match at {camera_name}")
    return {
        "event_id": event_id,
        "person_id": "",
        "person_name": "Unknown Visitor",
        "person_alias": "",
        "confidence": 0,
        "event_type": "unknown",
        "decision": "unknown",
        "unknown_id": unknown_id,
        "time": now,
    }


def process_camera_trigger_event(event_id: str, camera: dict) -> None:
    camera_name = camera["name"]
    try:
        image, suffix = fetch_still_image(camera.get("still_url") or camera.get("stream_url") or "")
        rel_path = save_image_bytes(image, "events", suffix)
        with connect() as conn:
            add_log(conn, "Recognition", "info", f"Processing camera {camera_name} still image")
        recognize_image_bytes(image, rel_path, camera["id"], camera_name, event_id)
    except HTTPException as error:
        detail = str(error.detail)
        label = "No face detected" if is_no_face_error(Exception(detail)) else "Trigger processing failed"
        event_type = "no_face" if label == "No face detected" else "error"
        event = mark_event_failed(event_id, label, camera_name, detail, event_type=event_type, camera_id=camera["id"])
        send_telegram_for_event(event, label, event_type, 0, event.get("image_path", ""))
        enforce_storage_quota()
    except Exception as error:  # noqa: BLE001
        event = mark_event_failed(event_id, "Trigger processing failed", camera_name, str(error), event_type="error", camera_id=camera["id"])
        send_telegram_for_event(event, "Trigger processing failed", "error", 0, event.get("image_path", ""))
        enforce_storage_quota()


@app.post("/api/recognize")
def recognize(
    file: Annotated[UploadFile, File()],
    camera_id: Annotated[str, Form()] = "",
    camera_name: Annotated[str, Form()] = "Manual upload",
    notify: Annotated[bool, Form()] = True,
) -> dict:
    rel_path, image = save_upload(file, "events")
    result = recognize_image_bytes(image, rel_path, camera_id, camera_name, notify=notify)
    if not notify:
        # Keep silent recognitions (Test page) out of the MQTT state that IRIS republishes
        # on reconnect / Home Assistant restart, so they never reach automations.
        event_ids = [result.get("id"), *[extra.get("id") for extra in result.get("additional_events") or []]]
        event_ids = [event_id for event_id in event_ids if event_id]
        if event_ids:
            with connect() as conn:
                conn.executemany("UPDATE events SET notified = 0 WHERE id = ?", [(event_id,) for event_id in event_ids])
        result["notified"] = 0
    return result


@app.get("/api/unknowns")
def list_unknowns() -> list[dict]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM unknown_visitors ORDER BY created_at DESC").fetchall())


@app.post("/api/unknowns/{unknown_id}/assign/{person_id}")
def assign_unknown(unknown_id: str, person_id: str) -> dict:
    with connect() as conn:
        unknown = row_to_dict(conn.execute("SELECT * FROM unknown_visitors WHERE id = ?", (unknown_id,)).fetchone())
        person = row_to_dict(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())
    if unknown is None or person is None:
        raise HTTPException(status_code=404, detail="Unknown visitor or person not found.")
    if unknown.get("event_id"):
        return train_event_face_to_person(unknown["event_id"], person_id)

    image_path = safe_upload_path(unknown["image_path"])
    if not image_path or not image_path.exists():
        raise HTTPException(status_code=404, detail="Unknown visitor image file not found.")
    try:
        indexed = insightface_engine.index_face(insightface_config(), image_path.read_bytes(), person_id)
    except insightface_engine.InsightFaceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _, face_crop_path, _ = create_event_images(unknown["image_path"], indexed.get("bounding_box"))
    face_image_path = face_crop_path or unknown["image_path"]
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO person_faces (id, person_id, face_id, embedding, image_path, source_image_path, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("face"), person_id, indexed["face_id"], indexed["embedding"], face_image_path, unknown["image_path"], insightface_config().model_name, now),
        )
        conn.execute("UPDATE people SET indexed_faces = indexed_faces + 1, updated_at = ? WHERE id = ?", (now, person_id))
        conn.execute("DELETE FROM unknown_visitors WHERE id = ?", (unknown_id,))
        add_log(conn, "Recognition", "info", f"Assigned unknown {unknown_id} to {display_person_name(person)}")
    publish_mqtt_state_if_configured()
    return {"ok": True}


@app.delete("/api/unknowns/{unknown_id}")
def delete_unknown(unknown_id: str) -> dict:
    with connect() as conn:
        unknown = row_to_dict(conn.execute("SELECT * FROM unknown_visitors WHERE id = ?", (unknown_id,)).fetchone())
        if unknown is None:
            raise HTTPException(status_code=404, detail="Unknown visitor not found.")
        conn.execute("DELETE FROM unknown_visitors WHERE id = ?", (unknown_id,))
        add_log(conn, "Recognition", "warn", f"Ignored unknown {unknown_id}")
    deleted_files = delete_unreferenced_uploads([unknown.get("image_path") or ""])
    if deleted_files:
        with connect() as conn:
            add_log(conn, "System", "info", f"Removed {deleted_files} unreferenced unknown image(s)")
    publish_mqtt_state_if_configured()
    return {"ok": True}


@app.get("/api/cameras")
def list_cameras() -> list[dict]:
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM cameras ORDER BY name").fetchall())
    return [serialize_camera(row) for row in rows]


@app.post("/api/cameras")
def create_camera(payload: CameraIn) -> dict:
    camera_id = new_id("cam")
    now = utc_now()
    name = payload.name.strip()
    still_url = (payload.still_url or payload.stream_url).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Camera name is required.")
    if not still_url:
        raise HTTPException(status_code=400, detail="Still image URL is required.")
    with connect() as conn:
        ensure_unique_camera_name(conn, name)
        trigger_slug = unique_camera_slug(conn, name)
        conn.execute(
            """
            INSERT INTO cameras
            (id, name, model, status, stream_url, still_url, trigger_slug, face_detection, motion, cooldown, min_face, min_confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (camera_id, name, payload.model, payload.status, still_url, still_url, trigger_slug, int(payload.face_detection), int(payload.motion), payload.cooldown, payload.min_face, payload.min_confidence, now, now),
        )
        row = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
        add_log(conn, "System", "info", f"Created camera {name} with trigger {trigger_slug}")
    camera = serialize_camera(row or {})
    publish_mqtt_discovery_async(f"creating camera {name}")
    return camera


def request_camera_trigger(trigger_slug: str, source: str = "API") -> dict:
    with connect() as conn:
        camera = row_to_dict(conn.execute("SELECT * FROM cameras WHERE trigger_slug = ?", (trigger_slug,)).fetchone())
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera trigger not found.")
    if camera["status"] != "online":
        raise HTTPException(status_code=409, detail="Camera is offline.")

    if camera.get("last_detection"):
        last = datetime.fromisoformat(camera["last_detection"])
        now_dt = datetime.fromisoformat(utc_now())
        if (now_dt - last).total_seconds() < int(camera["cooldown"]):
            event = create_event_shell(camera["id"], camera["name"], "Skipped cooldown", "skipped", update_camera=False)
            with connect() as conn:
                add_log(conn, "Recognition", "warn", f"Skipped {source} trigger for {camera['name']} during cooldown")
            return {
                "ok": True,
                "accepted": False,
                "skipped": True,
                "reason": "cooldown",
                "camera_id": camera["id"],
                "camera_name": camera["name"],
                "event_id": event["id"],
                "event": event,
            }

    event = create_event_shell(camera["id"], camera["name"])
    threading.Thread(
        target=process_camera_trigger_event,
        args=(event["id"], camera),
        daemon=True,
    ).start()
    return {
        "ok": True,
        "accepted": True,
        "skipped": False,
        "camera_id": camera["id"],
        "camera_name": camera["name"],
        "event_id": event["id"],
        "event": event,
    }


@app.post("/api/cameras/trigger/{trigger_slug}")
@app.get("/api/cameras/trigger/{trigger_slug}")
def trigger_camera(trigger_slug: str) -> dict:
    return request_camera_trigger(trigger_slug)


@app.get("/api/cameras/{camera_id}/snapshot")
def camera_snapshot(camera_id: str) -> Response:
    with connect() as conn:
        camera = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    if camera["status"] != "online":
        raise HTTPException(status_code=409, detail="Camera is offline.")

    image, suffix = fetch_still_image(camera.get("still_url") or camera.get("stream_url") or "")
    media_type = "image/png" if suffix.lower() == ".png" else "image/jpeg"
    return Response(
        content=image,
        media_type=media_type,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: str) -> dict:
    with connect() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return serialize_camera(row)


@app.put("/api/cameras/{camera_id}")
def update_camera(camera_id: str, payload: CameraIn) -> dict:
    now = utc_now()
    name = payload.name.strip()
    still_url = (payload.still_url or payload.stream_url).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Camera name is required.")
    if not still_url:
        raise HTTPException(status_code=400, detail="Still image URL is required.")
    with connect() as conn:
        previous = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
        if previous is None:
            raise HTTPException(status_code=404, detail="Camera not found.")
        ensure_unique_camera_name(conn, name, camera_id)
        trigger_slug = unique_camera_slug(conn, name, camera_id)
        conn.execute(
            """
            UPDATE cameras SET name = ?, model = ?, status = ?, stream_url = ?, still_url = ?, trigger_slug = ?, face_detection = ?, motion = ?,
              cooldown = ?, min_face = ?, min_confidence = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, payload.model, payload.status, still_url, still_url, trigger_slug, int(payload.face_detection), int(payload.motion), payload.cooldown, payload.min_face, payload.min_confidence, now, camera_id),
        )
        row = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found.")
        add_log(conn, "System", "info", f"Updated camera {name}")
    camera = serialize_camera(row)
    old_slug = (previous.get("trigger_slug") or "").strip()
    clear_slugs = [old_slug] if old_slug and old_slug != camera["trigger_slug"] else None
    publish_mqtt_discovery_async(f"updating camera {name}", clear_slugs)
    return camera


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: str) -> dict:
    with connect() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone())
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found.")
        conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        add_log(conn, "System", "warn", f"Deleted camera {camera_id}")
    trigger_slug = (row.get("trigger_slug") or "").strip()
    publish_mqtt_discovery_async(f"deleting camera {camera_id}", [trigger_slug] if trigger_slug else None)
    return {"ok": True}


@app.get("/api/settings/logs")
def get_logs_settings() -> dict:
    with connect() as conn:
        cfg = get_setting(conn, "logs", {"max_rows": 500})
    return {"max_rows": int(cfg.get("max_rows", 500))}


@app.put("/api/settings/logs")
def save_logs_settings(payload: LogsSettingsIn) -> dict:
    with connect() as conn:
        set_setting(conn, "logs", {"max_rows": payload.max_rows})
        add_log(conn, "System", "info", f"Updated log retention limit to {payload.max_rows} rows")
        prune_logs(conn, payload.max_rows)
    return {"max_rows": payload.max_rows}


@app.get("/api/logs")
def list_logs(page: int = 1, limit: int | None = None) -> dict:
    with connect() as conn:
        cfg = get_setting(conn, "logs", {"max_rows": 500})
        max_rows = int(cfg.get("max_rows", 500))
        prune_logs(conn, max_rows)
        per_page = max(1, min(limit or 50, 200, max_rows))
        total = conn.execute("SELECT COUNT(*) AS c FROM logs").fetchone()["c"]
        total_pages = max(1, (total + per_page - 1) // per_page)
        current_page = max(1, min(page, total_pages))
        offset = (current_page - 1) * per_page
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
        )
    return {
        "items": rows,
        "page": current_page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


@app.get("/api/uploads/{path:path}")
def uploaded_file(path: str) -> FileResponse:
    file_path = safe_upload_path(path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(file_path)
