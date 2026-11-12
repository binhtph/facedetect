"""Test-page uploads vs. MQTT: silent uploads must never reach Home Assistant, not even
through the automatic republish after a reconnect / HA restart; uploads with notify on
must update the MQTT state immediately.

Usage: python -I tests/backend/test_notify.py <repo> <buffalo_s.zip>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

REPO, MODEL_ZIP = sys.argv[1], sys.argv[2]
data_dir = Path(tempfile.mkdtemp(prefix="iris-notify-"))
os.environ["IRIS_DATA_DIR"] = str(data_dir)
model_dir = data_dir / "models" / "insightface" / "models" / "buffalo_s"
model_dir.mkdir(parents=True)
with zipfile.ZipFile(MODEL_ZIP) as archive:
    for member in archive.namelist():
        if member.endswith(".onnx") and ("det_500m" in member or "w600k_mbf" in member):
            (model_dir / Path(member).name).write_bytes(archive.read(member))
sys.path.insert(0, REPO)

import insightface  # noqa: E402
import paho.mqtt.client as mqtt  # noqa: E402
from amqtt.broker import Broker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PORT = 18831
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


async def start_broker() -> Broker:
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}},
        "sys_interval": 0,
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    })
    await broker.start()
    return broker


asyncio.run_coroutine_threadsafe(start_broker(), loop).result(15)

received: list[tuple[str, str]] = []
lock = threading.Lock()
watch = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="watch")
watch.on_connect = lambda c, u, f, rc, p: c.subscribe([("iris/state", 1), ("iris/event", 1)])
watch.on_message = lambda c, u, m: (lock.acquire(), received.append((m.topic, m.payload.decode())), lock.release())
watch.connect("127.0.0.1", PORT)
watch.loop_start()

from backend.app import main  # noqa: E402

group = (Path(insightface.__file__).parent / "data" / "images" / "t1.jpg").read_bytes()


def ok(label: str) -> None:
    print(f"PASS  {label}", flush=True)


def events_on(topic: str) -> list[dict]:
    with lock:
        return [json.loads(p) for t, p in received if t == topic]


with TestClient(main.app) as api:
    assert api.put("/api/settings/mqtt", json={
        "host": "127.0.0.1", "port": PORT, "username": "", "password": "", "discovery_prefix": "homeassistant",
        "base_topic": "iris", "device_id": "iris_test", "device_name": "IRIS", "use_tls": False,
    }).status_code == 200
    time.sleep(1)

    # 1. A real (notified) recognition updates the state immediately.
    loud = api.post("/api/recognize", files={"file": ("g.jpg", group, "image/jpeg")}, data={"camera_name": "Front door"}).json()
    time.sleep(1)
    assert any(e["event_id"] == loud["id"] for e in events_on("iris/event")), "notified upload must publish iris/event"
    assert events_on("iris/state")[-1]["latest_event_id"] == loud["id"]
    ok("upload with notify=true -> iris/event + state updated immediately")

    # 2. A silent Test-page upload publishes nothing...
    with lock:
        received.clear()
    silent = api.post(
        "/api/recognize", files={"file": ("g.jpg", group, "image/jpeg")},
        data={"camera_name": "Test upload", "notify": "false"},
    ).json()
    time.sleep(1.5)
    assert events_on("iris/event") == [] and events_on("iris/state") == [], received
    ok("Test upload with notify=false -> nothing published")

    # 3. ...and is NOT leaked by the automatic republish (HA restart / reconnect).
    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ha")
    pub.connect("127.0.0.1", PORT)
    pub.loop_start()
    pub.publish("homeassistant/status", "online", qos=1).wait_for_publish(5)
    deadline = time.time() + 10
    while not events_on("iris/state") and time.time() < deadline:
        time.sleep(0.1)
    state = events_on("iris/state")[-1]
    assert state["latest_event_id"] == loud["id"] != silent["id"], state["latest_event_id"]
    ok("republish after HA restart still shows the last real event, not the test upload")

    assert main.current_mqtt_state()["latest_event_id"] == loud["id"]
    assert api.get(f"/api/events/{silent['id']}").json().get("notified") == 0
    ok("silent events are stored (visible in IRIS) but flagged notified=0")

print("notify checks passed")
