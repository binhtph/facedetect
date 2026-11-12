from __future__ import annotations

import json
import logging
import ssl
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger("iris.mqtt")

MESSAGE_PREVIEW_CHARS = 600


class MqttError(RuntimeError):
    pass


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int = 1883
    username: str = ""
    password: str = ""
    discovery_prefix: str = "homeassistant"
    base_topic: str = "iris"
    device_id: str = "iris_face_recognition"
    device_name: str = "IRIS Face Recognition"
    use_tls: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.host and self.port)


def _client(config: MqttConfig, client_id: str) -> mqtt.Client:
    if not config.configured:
        raise MqttError("MQTT host and port are required.")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if config.username:
        client.username_pw_set(config.username, config.password)
    if config.use_tls:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    return client


def base_topic(config: MqttConfig) -> str:
    return config.base_topic.strip().strip("/") or "iris"


def discovery_prefix(config: MqttConfig) -> str:
    return config.discovery_prefix.strip().strip("/") or "homeassistant"


def availability_topic(config: MqttConfig) -> str:
    return f"{base_topic(config)}/availability"


def test_connection(config: MqttConfig, timeout: float = 10.0) -> None:
    """Open a short-lived connection with its own unique client id and wait for CONNACK."""
    client = _client(config, f"{config.device_id}_test_{uuid.uuid4().hex[:8]}")
    connected = threading.Event()
    outcome: dict[str, Any] = {}

    def handle_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        outcome["reason"] = reason_code
        connected.set()

    client.on_connect = handle_connect
    try:
        client.connect(config.host, config.port, keepalive=10)
        client.loop_start()
        if not connected.wait(timeout):
            raise MqttError(f"No answer from MQTT broker {config.host}:{config.port} within {timeout:.0f}s.")
        reason = outcome.get("reason")
        if reason is not None and getattr(reason, "is_failure", False):
            raise MqttError(f"MQTT broker refused the connection: {reason}")
    except MqttError:
        raise
    except Exception as error:  # noqa: BLE001
        raise MqttError(str(error)) from error
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception as error:  # noqa: BLE001
            logger.debug("Ignoring error while closing MQTT test client: %s", error)


def _describe_payload(payload: str | bytes) -> str:
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary {len(payload)} bytes>"
    else:
        text = payload
    if len(text) > MESSAGE_PREVIEW_CHARS:
        return f"{text[:MESSAGE_PREVIEW_CHARS]}… ({len(text)} chars)"
    return text


class MqttBridge:
    """One long-lived MQTT connection shared by every publisher and the command listener.

    - A single, stable client id per IRIS instance (no more client-id fights between
      short-lived connections).
    - Last Will marks the device offline in Home Assistant if IRIS dies or loses the broker.
    - paho reconnects automatically; on every (re)connect the availability is set back to
      ``online``, subscriptions are restored and ``on_connected`` republishes discovery/state.
    - Home Assistant's birth message (``<discovery_prefix>/status`` = ``online``) triggers a
      republish too, so entities survive an HA restart.
    - Every publish, received command and connection change is kept in a small ring buffer
      for the MQTT debug view.
    """

    def __init__(
        self,
        on_camera_trigger: Callable[[str], None],
        on_connected: Callable[[MqttConfig, str], None] | None = None,
        on_status_change: Callable[[str, str], None] | None = None,
        history_size: int = 200,
    ) -> None:
        self._on_camera_trigger = on_camera_trigger
        self._on_connected = on_connected
        self._on_status_change = on_status_change
        self._lock = threading.RLock()
        self._client: mqtt.Client | None = None
        self._config: MqttConfig | None = None
        self._connected = threading.Event()
        self._messages: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._last_error = ""
        self._last_connected_at = ""
        self._last_disconnected_at = ""

    # ----- lifecycle -------------------------------------------------------------------
    def restart(self, config: MqttConfig | None) -> None:
        with self._lock:
            self._stop_locked(publish_offline=False)
            self._last_error = ""
            if config is None or not config.configured:
                self._config = None
                return
            self._config = config
            client = _client(config, f"{config.device_id}_iris")
            client.will_set(availability_topic(config), "offline", qos=1, retain=True)
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            # Keep at most this many QoS 1 messages while the broker is unreachable.
            client.max_queued_messages_set(500)
            client.on_connect = self._handle_connect
            client.on_disconnect = self._handle_disconnect
            client.on_message = self._handle_message
            self._client = client
            try:
                client.connect_async(config.host, config.port, keepalive=30)
                client.loop_start()
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error)
                self._record("system", "", f"Cannot start MQTT connection: {error}")
                logger.error("Cannot start MQTT connection to %s:%s: %s", config.host, config.port, error)
                raise MqttError(str(error)) from error
            self._record("system", "", f"Connecting to {config.host}:{config.port}")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked(publish_offline=True)
            self._config = None

    def _stop_locked(self, publish_offline: bool) -> None:
        client, config = self._client, self._config
        self._client = None
        self._connected.clear()
        if client is None:
            return
        try:
            if publish_offline and config is not None and client.is_connected():
                client.publish(availability_topic(config), "offline", qos=1, retain=True).wait_for_publish(timeout=2)
            client.disconnect()
            client.loop_stop()
        except Exception as error:  # noqa: BLE001
            logger.debug("Ignoring error while stopping MQTT client: %s", error)

    def wait_until_connected(self, timeout: float) -> bool:
        return self._connected.wait(timeout)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def config(self) -> MqttConfig | None:
        return self._config

    # ----- publishing ------------------------------------------------------------------
    def publish(self, messages: list[tuple[str, str | bytes, bool]], qos: int = 1) -> bool:
        """Queue messages on the shared connection.

        Returns False when MQTT is not configured. QoS 1 messages published while the
        connection is down are kept by paho and delivered after it reconnects; QoS 0
        messages (used for large images) are dropped and logged instead.
        """
        with self._lock:
            client = self._client
        if client is None:
            return False
        delivered_all = True
        for topic, payload, retain in messages:
            try:
                info = client.publish(topic, payload, qos=qos, retain=retain)
                status = "queued" if info.rc == mqtt.MQTT_ERR_NO_CONN else ("sent" if info.rc == mqtt.MQTT_ERR_SUCCESS else f"error rc={info.rc}")
                if info.rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN) or (info.rc == mqtt.MQTT_ERR_NO_CONN and qos == 0):
                    delivered_all = False
                    logger.warning("MQTT publish to %s not delivered (%s)", topic, status if qos else "dropped, broker offline")
            except Exception as error:  # noqa: BLE001
                delivered_all = False
                status = f"error: {error}"
                logger.warning("MQTT publish to %s failed: %s", topic, error)
            self._record("out", topic, _describe_payload(payload), retain=retain, qos=qos, status=status)
        return delivered_all

    # ----- debug data ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        config = self._config
        return {
            "configured": config is not None,
            "connected": self.connected,
            "host": config.host if config else "",
            "port": config.port if config else 0,
            "client_id": f"{config.device_id}_iris" if config else "",
            "last_connected_at": self._last_connected_at,
            "last_disconnected_at": self._last_disconnected_at,
            "last_error": self._last_error,
        }

    def messages(self, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._messages)[-max(1, limit):]
        items.reverse()
        return items

    def clear_messages(self) -> None:
        self._messages.clear()

    def _record(self, direction: str, topic: str, payload: str, retain: bool = False, qos: int = 0, status: str = "") -> None:
        self._messages.append(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "direction": direction,
                "topic": topic,
                "payload": payload,
                "retain": retain,
                "qos": qos,
                "status": status,
            }
        )

    # ----- paho callbacks (run on paho's network thread) -------------------------------
    def _handle_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        config = self._config
        if config is None:
            return
        if getattr(reason_code, "is_failure", False):
            self._last_error = f"Broker refused connection: {reason_code}"
            self._record("system", "", self._last_error)
            logger.error("MQTT broker %s:%s refused connection: %s", config.host, config.port, reason_code)
            self._notify_status("error", self._last_error)
            return
        self._connected.set()
        self._last_error = ""
        self._last_connected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        base = base_topic(config)
        client.subscribe([(f"{base}/camera/+/trigger/set", 1), (f"{discovery_prefix(config)}/status", 1)])
        client.publish(availability_topic(config), "online", qos=1, retain=True)
        self._record("system", "", f"Connected to {config.host}:{config.port}")
        logger.info("MQTT connected to %s:%s as %s_iris", config.host, config.port, config.device_id)
        self._notify_status("info", f"MQTT connected to {config.host}:{config.port}")
        self._run_on_connected(config, "connect")

    def _handle_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        was_connected = self._connected.is_set()
        self._connected.clear()
        self._last_disconnected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if self._client is not client:
            return  # intentional stop/restart
        reason = str(reason_code)
        self._last_error = f"Disconnected: {reason}"
        self._record("system", "", f"Disconnected ({reason}); reconnecting automatically")
        logger.warning("MQTT disconnected (%s); paho will reconnect", reason)
        if was_connected:
            self._notify_status("warn", f"MQTT disconnected ({reason}); reconnecting")

    def _handle_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        config = self._config
        if config is None:
            return
        payload = message.payload.decode("utf-8", errors="ignore").strip()
        self._record("in", message.topic, _describe_payload(payload), retain=bool(message.retain), qos=message.qos)
        if message.topic == f"{discovery_prefix(config)}/status":
            if payload.lower() == "online" and not message.retain:
                self._run_on_connected(config, "Home Assistant restart")
            return
        if payload.lower() != "press":
            return
        prefix = f"{base_topic(config)}/camera/"
        suffix = "/trigger/set"
        topic = message.topic
        if not topic.startswith(prefix) or not topic.endswith(suffix):
            return
        slug = topic[len(prefix) : -len(suffix)]
        if slug:
            threading.Thread(target=self._safe_trigger, args=(slug,), daemon=True).start()

    def _safe_trigger(self, slug: str) -> None:
        try:
            self._on_camera_trigger(slug)
        except Exception:  # noqa: BLE001
            logger.exception("MQTT camera trigger for %s failed", slug)

    def _run_on_connected(self, config: MqttConfig, reason: str) -> None:
        if self._on_connected is None:
            return

        def runner() -> None:
            try:
                self._on_connected(config, reason)
            except Exception:  # noqa: BLE001
                logger.exception("Republishing Home Assistant data after %s failed", reason)

        threading.Thread(target=runner, daemon=True).start()

    def _notify_status(self, severity: str, message: str) -> None:
        if self._on_status_change is None:
            return
        try:
            self._on_status_change(severity, message)
        except Exception:  # noqa: BLE001
            logger.exception("Recording MQTT status change failed")


def discovery_messages(config: MqttConfig, state: dict[str, Any], cameras: list[dict[str, Any]] | None = None) -> list[tuple[str, str, bool]]:
    base = config.base_topic.strip().strip("/") or "iris"
    prefix = config.discovery_prefix.strip().strip("/") or "homeassistant"
    device = {
        "identifiers": [config.device_id],
        "name": config.device_name,
        "manufacturer": "IRIS",
        "model": "Face Recognition Console",
    }
    availability_topic = f"{base}/availability"
    state_topic = f"{base}/state"

    entities = [
        (
            "sensor",
            "latest_person",
            {
                "name": "Latest Person",
                "state_topic": state_topic,
                "value_template": "{{ value_json.latest_person }}",
                "json_attributes_topic": state_topic,
                "json_attributes_template": "{{ value_json.latest_attributes | tojson }}",
                "icon": "mdi:account-search",
            },
        ),
        (
            "sensor",
            "latest_type",
            {
                "name": "Latest Recognition Type",
                "state_topic": state_topic,
                "value_template": "{{ value_json.latest_type }}",
                "icon": "mdi:shape",
            },
        ),
        (
            "sensor",
            "latest_decision",
            {
                "name": "Latest Decision",
                "state_topic": state_topic,
                "value_template": "{{ value_json.latest_decision }}",
                "icon": "mdi:shield-check",
            },
        ),
        (
            "sensor",
            "latest_event",
            {
                "name": "Latest Recognition Event",
                "state_topic": f"{base}/event",
                "value_template": "{{ value_json.event_id }}",
                "json_attributes_topic": f"{base}/event",
                "json_attributes_template": "{{ value_json | tojson }}",
                "icon": "mdi:calendar-check",
            },
        ),
        (
            "sensor",
            "latest_camera",
            {
                "name": "Latest Camera",
                "state_topic": state_topic,
                "value_template": "{{ value_json.latest_camera }}",
                "icon": "mdi:camera",
            },
        ),
        (
            "sensor",
            "latest_confidence",
            {
                "name": "Latest Confidence",
                "state_topic": state_topic,
                "value_template": "{{ value_json.latest_confidence }}",
                "unit_of_measurement": "%",
                "icon": "mdi:percent",
            },
        ),
        (
            "image",
            "latest_snapshot",
            {
                "name": "Latest Snapshot",
                "image_topic": f"{base}/latest_image",
                "content_type": "image/jpeg",
                "icon": "mdi:image-area",
            },
        ),
    ]

    messages: list[tuple[str, str | bytes, bool]] = []
    for domain, object_id, payload in entities:
        unique_id = f"{config.device_id}_{object_id}"
        topic = f"{prefix}/{domain}/{config.device_id}/{object_id}/config"
        body = {
            "unique_id": unique_id,
            "object_id": unique_id,
            "availability_topic": availability_topic,
            "device": device,
            **payload,
        }
        messages.append((topic, json.dumps(body, ensure_ascii=False), True))

    for camera in cameras or []:
        slug = (camera.get("trigger_slug") or "").strip()
        name = (camera.get("name") or slug).strip()
        if not slug or not name:
            continue
        object_id = f"trigger_{slug.replace('-', '_')}"
        unique_id = f"{config.device_id}_{object_id}"
        topic = f"{prefix}/button/{config.device_id}/{object_id}/config"
        body = {
            "unique_id": unique_id,
            "object_id": unique_id,
            "name": f"Trigger {name}",
            "availability_topic": availability_topic,
            "command_topic": f"{base}/camera/{slug}/trigger/set",
            "payload_press": "press",
            "icon": "mdi:camera-control",
            "device": device,
        }
        messages.append((topic, json.dumps(body, ensure_ascii=False), True))

    removed_entities = [
        ("binary_sensor", "engine_online"),
        ("sensor", "known_people"),
        ("sensor", "pending_unknown"),
        ("sensor", "recognition_events"),
        ("sensor", "latest_image_path"),
        ("sensor", "latest_person_alias"),
    ]
    for domain, object_id in removed_entities:
        messages.append((f"{prefix}/{domain}/{config.device_id}/{object_id}/config", "", True))

    messages.append((availability_topic, "online", True))
    messages.append((state_topic, json.dumps(state, ensure_ascii=False), True))
    return messages


def camera_trigger_discovery_clear_message(config: MqttConfig, trigger_slug: str) -> tuple[str, str, bool] | None:
    slug = trigger_slug.strip()
    if not slug:
        return None
    prefix = config.discovery_prefix.strip().strip("/") or "homeassistant"
    object_id = f"trigger_{slug.replace('-', '_')}"
    return (f"{prefix}/button/{config.device_id}/{object_id}/config", "", True)
