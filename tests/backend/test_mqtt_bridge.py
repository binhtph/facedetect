"""End-to-end check of the IRIS MQTT bridge against a real (amqtt) broker.

Run from the repo root:  IRIS_DATA_DIR=<tmp> python -I tests/test_mqtt_bridge.py <repo>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time

REPO = sys.argv[1]
sys.path.insert(0, REPO)
os.environ.setdefault("IRIS_DATA_DIR", tempfile.mkdtemp(prefix="iris-data-"))

import paho.mqtt.client as mqtt  # noqa: E402
from amqtt.broker import Broker  # noqa: E402

PORT = 18830
BROKER_CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}},
    "sys_interval": 0,
    "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
    "topic-check": {"enabled": False},
}


class BrokerThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.broker: Broker | None = None

    def start(self) -> None:
        async def go() -> None:
            self.broker = Broker(BROKER_CONFIG)
            await self.broker.start()

        asyncio.run_coroutine_threadsafe(go(), self.loop).result(15)

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop).result(15)


received: list[tuple[str, str, bool]] = []
lock = threading.Lock()


def watcher() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_watcher")

    def on_connect(c, u, f, rc, p):
        c.subscribe([("iris/#", 1), ("homeassistant/#", 1)])

    def on_message(c, u, m):
        with lock:
            received.append((m.topic, m.payload.decode("utf-8", "replace") if len(m.payload) < 5000 else f"<{len(m.payload)} bytes>", bool(m.retain)))

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(1, 2)
    client.connect(f"127.0.0.1", PORT)
    client.loop_start()
    return client


def wait_for(predicate, timeout: float, label: str):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with lock:
            hit = predicate(list(received))
        if hit:
            return hit
        time.sleep(0.1)
    with lock:
        tail = received[-15:]
    raise AssertionError(f"Timed out waiting for {label}. Last messages: {tail}")


def last_payload(topic: str):
    def check(items):
        matches = [payload for t, payload, _ in items if t == topic]
        return matches[-1] if matches else None
    return check


results: list[str] = []


def ok(label: str) -> None:
    results.append(label)
    print(f"PASS  {label}", flush=True)


broker = BrokerThread()
broker.start()
w = watcher()
time.sleep(0.5)

from fastapi.testclient import TestClient  # noqa: E402
from backend.app import main  # noqa: E402

triggers: list[str] = []
main.handle_mqtt_camera_trigger = lambda slug: triggers.append(slug)  # type: ignore[assignment]

with TestClient(main.app) as api:
    # 1. Save settings -> bridge connects, discovery + availability published automatically
    response = api.put(
        "/api/settings/mqtt",
        json={"host": "127.0.0.1", "port": PORT, "username": "", "password": "", "discovery_prefix": "homeassistant",
              "base_topic": "iris", "device_id": "iris_test", "device_name": "IRIS Test", "use_tls": False},
    )
    assert response.status_code == 200, response.text
    wait_for(lambda items: any(t == "homeassistant/sensor/iris_test/latest_person/config" for t, _, _ in items), 10, "discovery")
    wait_for(lambda items: last_payload("iris/availability")(items) == "online", 10, "availability online")
    ok("save settings connects and publishes discovery + online")

    status = api.get("/api/mqtt/status").json()
    assert status["connected"] and status["client_id"] == "iris_test_iris", status
    ok("status endpoint reports one stable client id")

    # 2. Many recognitions published concurrently from several threads all arrive
    def fire(i: int) -> None:
        main.publish_mqtt_decision_fast({"latest_event_id": f"evt_{i}", "latest_person": f"P{i}", "latest_type": "known"})

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wait_for(lambda items: len({json.loads(p)["event_id"] for t, p, _ in items if t == "iris/event"}) >= 25, 10, "25 events")
    ok("25 concurrent recognitions -> 25 iris/event messages")

    # 3. Camera trigger command is handled
    cmd = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_cmd")
    cmd.connect("127.0.0.1", PORT)
    cmd.loop_start()
    cmd.publish("iris/camera/front-door/trigger/set", "press", qos=1).wait_for_publish(5)
    deadline = time.time() + 5
    while not triggers and time.time() < deadline:
        time.sleep(0.1)
    assert triggers == ["front-door"], triggers
    ok("camera trigger command reaches IRIS")

    # 4. Home Assistant birth message -> discovery republished
    with lock:
        received.clear()
    cmd.publish("homeassistant/status", "online", qos=1).wait_for_publish(5)
    wait_for(lambda items: any(t.endswith("/latest_person/config") for t, _, _ in items), 10, "republish after HA restart")
    ok("HA restart (birth message) republishes discovery")

    # 5. Broker restart -> bridge reconnects and republishes without saving settings again
    cmd.loop_stop()
    cmd.disconnect()
    with lock:
        received.clear()
    broker.stop()
    time.sleep(1.5)
    assert not main.mqtt_bridge.connected
    main.publish_mqtt_decision_fast({"latest_event_id": "evt_while_offline", "latest_person": "Offline", "latest_type": "known"})
    broker.start()
    assert main.mqtt_bridge.wait_until_connected(40), "bridge did not reconnect"
    wait_for(lambda items: any(t.endswith("/latest_person/config") for t, _, _ in items), 15, "republish after reconnect")
    wait_for(lambda items: last_payload("iris/availability")(items) == "online", 10, "online after reconnect")
    ok("broker restart -> automatic reconnect + republish")
    wait_for(lambda items: any(t == "iris/event" and "evt_while_offline" in p for t, p, _ in items), 10, "queued event")
    ok("QoS1 event published while offline is delivered after reconnect")

    # 6. Abrupt connection loss -> Last Will marks IRIS offline, then back online
    with lock:
        received.clear()
    sock = main.mqtt_bridge._client.socket()  # noqa: SLF001
    sock.close()
    wait_for(lambda items: "offline" in [p for t, p, _ in items if t == "iris/availability"], 40, "LWT offline")
    ok("abrupt disconnect -> Last Will publishes offline")
    wait_for(lambda items: [p for t, p, _ in items if t == "iris/availability"][-1:] == ["online"], 40, "online again")
    ok("...and IRIS comes back online by itself")

    # 7. Debug message log
    data = api.get("/api/mqtt/messages?limit=50").json()
    assert data["messages"] and {"time", "direction", "topic", "payload", "status"} <= set(data["messages"][0]), data["messages"][:1]
    assert any(m["direction"] == "system" for m in api.get("/api/mqtt/messages?limit=200").json()["messages"])
    assert api.delete("/api/mqtt/messages").json() == {"ok": True}
    ok("MQTT message log endpoints")

    # 8. Wrong broker -> save reports a clear error instead of hanging
    response = api.put(
        "/api/settings/mqtt",
        json={"host": "127.0.0.1", "port": 18999, "username": "", "password": "", "discovery_prefix": "homeassistant",
              "base_topic": "iris", "device_id": "iris_test", "device_name": "IRIS Test", "use_tls": False},
    )
    assert response.status_code == 400 and "not connected" in response.json()["detail"], response.text
    ok("unreachable broker -> 400 with explanation")

w.loop_stop()
print(f"\n{len(results)} checks passed")
