from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt


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


def _client(config: MqttConfig, client_id_suffix: str = "publisher") -> mqtt.Client:
    if not config.configured:
        raise MqttError("MQTT host and port are required.")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{config.device_id}_{client_id_suffix}")
    if config.username:
        client.username_pw_set(config.username, config.password)
    if config.use_tls:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    return client


def publish_many(config: MqttConfig, messages: list[tuple[str, str | bytes, bool]]) -> None:
    client = _client(config)
    try:
        client.connect(config.host, config.port, keepalive=30)
        client.loop_start()
        for topic, payload, retain in messages:
            result = client.publish(topic, payload, qos=0, retain=retain)
            result.wait_for_publish(timeout=5)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise MqttError(f"Publish failed for {topic}: rc={result.rc}")
    except Exception as error:  # noqa: BLE001
        raise MqttError(str(error)) from error
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


def publish_many_connected(client: mqtt.Client, messages: list[tuple[str, str | bytes, bool]]) -> None:
    if not client.is_connected():
        raise MqttError("MQTT client is not connected.")
    for topic, payload, retain in messages:
        result = client.publish(topic, payload, qos=0, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttError(f"Publish failed for {topic}: rc={result.rc}")


def test_connection(config: MqttConfig) -> None:
    client = _client(config)
    try:
        client.connect(config.host, config.port, keepalive=10)
        client.disconnect()
    except Exception as error:  # noqa: BLE001
        raise MqttError(str(error)) from error


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


def start_command_listener(config: MqttConfig, on_camera_trigger: Any) -> mqtt.Client:
    base = config.base_topic.strip().strip("/") or "iris"
    command_topic = f"{base}/camera/+/trigger/set"
    client = _client(config, "commands")

    def handle_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code == 0:
            client.subscribe(command_topic, qos=0)

    def handle_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        payload = message.payload.decode("utf-8", errors="ignore").strip().lower()
        if payload != "press":
            return
        prefix = f"{base}/camera/"
        suffix = "/trigger/set"
        topic = message.topic
        if not topic.startswith(prefix) or not topic.endswith(suffix):
            return
        slug = topic[len(prefix) : -len(suffix)]
        if slug:
            on_camera_trigger(slug)

    client.on_connect = handle_connect
    client.on_message = handle_message
    try:
        client.connect(config.host, config.port, keepalive=30)
        client.loop_start()
    except Exception as error:  # noqa: BLE001
        raise MqttError(str(error)) from error
    return client


def stop_command_listener(client: mqtt.Client | None) -> None:
    if client is None:
        return
    try:
        client.loop_stop()
        client.disconnect()
    except Exception:
        pass
