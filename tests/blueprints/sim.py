"""Fake IRIS + test devices over MQTT, and scenario checks for blueprints/automation/iris_face_door.yaml.

python sim.py setup  -> publish retained discovery/state, then exit (before HA starts)
python sim.py run    -> run scenarios against the running Home Assistant
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from PIL import Image, ImageDraw

from pathlib import Path

spec = importlib.util.spec_from_file_location("mh", Path(__file__).resolve().parents[2] / "backend/app/mqtt_homeassistant.py")
mh = importlib.util.module_from_spec(spec)
sys.modules["mh"] = mh
spec.loader.exec_module(mh)

PORT = 18831
SNAP_UNLOCK = "/media/snapshots/iris_cua.jpg"
CAMERAS = [{"trigger_slug": "cong", "name": "Cổng"}, {"trigger_slug": "san-sau", "name": "Sân sau"}]
BINH_GREETINGS = {"Chào mừng anh Bình về nhà!"} | {f"Anh Bình về rồi. Chúc anh buổi {b} vui vẻ!" for b in ("sáng", "trưa", "chiều", "tối")}

log: list[tuple[float, str, bytes]] = []
lock = threading.Lock()
responses: list[list[dict]] = []
images: dict[str, bytes] = {}
results: list[tuple[str, bool, str]] = []
state = {"jam": False}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def jpeg(label: str) -> bytes:
    img = Image.new("RGB", (64, 48), (hash(label) % 255, 80, 160))
    ImageDraw.Draw(img).text((2, 2), label[-6:], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def ev(type_: str, person: str = "", conf: float = 0, camera: str = "Cổng", faces: int | None = 1) -> dict:
    eid = "evt_" + uuid.uuid4().hex[:10]
    payload = {
        "event_id": eid,
        "latest_event_id": eid,
        "latest_person": person,
        "latest_person_alias": "",
        "latest_person_name": person,
        "latest_person_id": "p_1" if type_ in ("known", "review") else "",
        "latest_type": type_,
        "latest_decision": "auto_accept" if type_ == "known" else type_,
        "latest_camera": camera,
        "latest_confidence": conf,
        "latest_time": utc_now(),
        "latest_attributes": {"face_confidence": 88.1, "age": None, "gender": None},
    }
    if faces is not None:
        payload["faces_in_image"] = faces
    return payload


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iris_sim")


def publish_result(events: list[dict], image_delay: float = 0.4) -> None:
    """Mimic IRIS: extra faces first, main face last, then the annotated image."""
    time.sleep(0.3)
    for payload in events:
        client.publish("iris/state", json.dumps(payload, ensure_ascii=False), qos=1, retain=True)
        client.publish("iris/event", json.dumps(payload, ensure_ascii=False), qos=1)
    time.sleep(image_delay)
    label = events[-1]["event_id"]
    data = jpeg(label)
    images[label] = data
    client.publish("iris/latest_image", data, qos=0, retain=True)


def on_connect(c, u, f, rc, p):
    c.subscribe([("iris/camera/+/trigger/set", 1), ("test/#", 1), ("homeassistant/status", 1)])


def on_message(c, u, m):
    with lock:
        log.append((time.time(), m.topic, m.payload))
    if m.topic.startswith("iris/camera/") and m.topic.endswith("/trigger/set"):
        with lock:
            resp = responses.pop(0) if responses else None
        if resp:
            threading.Thread(target=publish_result, args=(resp,), daemon=True).start()
    elif m.topic in ("test/led/set", "test/led2/set"):
        client.publish(m.topic.replace("/set", "/state"), m.payload, qos=1, retain=True)
    elif m.topic == "test/lock/set":
        cmd = m.payload.decode()
        if cmd == "UNLOCK" and not state["jam"]:
            threading.Timer(0.5, lambda: client.publish("test/lock/state", "UNLOCKED", qos=1, retain=True)).start()
        elif cmd == "LOCK":
            threading.Timer(0.3, lambda: client.publish("test/lock/state", "LOCKED", qos=1, retain=True)).start()


client.on_connect = on_connect
client.on_message = on_message


def since(t0: float, topic: str) -> list[bytes]:
    with lock:
        return [p for t, tp, p in log if t >= t0 and (tp == topic or (topic.endswith("#") and tp.startswith(topic[:-1])))]


def notes(t0: float) -> list[dict]:
    return [json.loads(p) for p in since(t0, "test/notify")]


def says(t0: float) -> list[dict]:
    return [json.loads(p) for p in since(t0, "test/speaker/say")]


def volumes(t0: float) -> list[float]:
    return [json.loads(p)["volume"] for p in since(t0, "test/speaker/volume")]


def presses(t0: float) -> list[bytes]:
    return since(t0, "iris/camera/#")


def led(t0: float, which: str = "led") -> list[bytes]:
    """Commands to light.door_led ("led", unlock shots) or light.door_led_inside ("led2", door-open shots)."""
    return since(t0, f"test/{which}/set")


def first_time(t0: float, topic: str) -> float:
    with lock:
        return next((t for t, tp, _ in log if t >= t0 and (tp == topic or (topic.endswith("#") and tp.startswith(topic[:-1])))), 0)


def wait_until(fn, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return fn()


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  -> {detail}" if detail and not ok else ""), flush=True)


def pulse(topic: str) -> None:
    client.publish(topic, "OFF", qos=1, retain=True)
    time.sleep(0.3)
    client.publish(topic, "ON", qos=1, retain=True)
    time.sleep(0.3)


def motion() -> None:
    pulse("test/motion")
    client.publish("test/motion", "OFF", qos=1, retain=True)


def door_open() -> None:
    pulse("test/door")


def door_close() -> None:
    client.publish("test/door", "OFF", qos=1, retain=True)


def relock() -> None:
    client.publish("test/lock/state", "LOCKED", qos=1, retain=True)
    time.sleep(0.5)


def snap_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return b""


def setup() -> None:
    client.connect("127.0.0.1", PORT)
    client.loop_start()
    cfg = mh.MqttConfig(host="127.0.0.1", port=PORT)
    old = ev("unknown", "Unknown Visitor", 0, camera="Test upload")
    old["latest_time"] = "2026-11-12T07:46:26+00:00"
    for topic, payload, retain in mh.discovery_messages(cfg, old, CAMERAS):
        client.publish(topic, payload, qos=1, retain=retain)
    test_entities = {
        "homeassistant/binary_sensor/test/motion/config": {
            "name": "motion_sensor_occupancy", "unique_id": "t_motion", "state_topic": "test/motion",
            "default_entity_id": "binary_sensor.motion_sensor_occupancy",
        },
        "homeassistant/binary_sensor/test/door/config": {
            "name": "Living Room Door", "unique_id": "t_door", "state_topic": "test/door", "device_class": "door",
            "default_entity_id": "binary_sensor.living_room_door_contact",
        },
        "homeassistant/event/test/button/config": {
            "name": "test_button", "unique_id": "t_btn", "state_topic": "test/button",
            "event_types": ["single", "double"], "default_entity_id": "event.test_button",
        },
        "homeassistant/lock/test/lock/config": {
            "name": "Aqara Smart Lock A100", "unique_id": "t_lock", "command_topic": "test/lock/set",
            "state_topic": "test/lock/state", "default_entity_id": "lock.aqara_smart_lock_a100",
        },
        "homeassistant/light/test/led/config": {
            "name": "Door LED", "unique_id": "t_led", "command_topic": "test/led/set", "state_topic": "test/led/state",
            "brightness_command_topic": "test/led/brightness", "default_entity_id": "light.door_led",
        },
        "homeassistant/light/test/led2/config": {
            "name": "Door LED inside", "unique_id": "t_led2", "command_topic": "test/led2/set", "state_topic": "test/led2/state",
            "default_entity_id": "light.door_led_inside",
        },
        "homeassistant/light/test/light/config": {
            "name": "Study Lamp", "unique_id": "t_light", "command_topic": "test/light/set",
            "default_entity_id": "light.midesklamp1s_52cf",
        },
    }
    for topic, body in test_entities.items():
        client.publish(topic, json.dumps(body), qos=1, retain=True)
    client.publish("test/motion", "OFF", qos=1, retain=True)
    client.publish("test/door", "OFF", qos=1, retain=True)
    client.publish("test/lock/state", "LOCKED", qos=1, retain=True)
    client.publish("test/led/state", "OFF", qos=1, retain=True)
    client.publish("test/led2/state", "OFF", qos=1, retain=True)
    client.publish("iris/latest_image", jpeg("startup"), qos=0, retain=True)
    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print("setup published", flush=True)


def unlock_scenarios() -> None:
    # U1 motion -> allowed person -> unlock, light, greeting, notification with photo
    t0 = time.time()
    first = ev("known", "Bình", 72.4)
    responses.append([first])
    motion()
    check("U1 motion presses IRIS once", wait_until(lambda: len(presses(t0)) == 1, 5), str(presses(t0)))
    t_busy = time.time()
    motion()  # U2: a new trigger while U1 is still being handled must not queue another shot
    check("U1 unlock sent", wait_until(lambda: since(t0, "test/lock/set") == [b"UNLOCK"], 6), str(since(t0, "test/lock/set")))
    check("U1 light on", wait_until(lambda: since(t0, "test/light/set") == [b"ON"], 6), str(since(t0, "test/light/set")))
    check("U1 LED on, then off after the result", wait_until(lambda: led(t0) == [b"ON", b"OFF"], 8), str(led(t0)))
    check("U1 LED on before the shot (warm-up)", 0 < first_time(t0, "test/led/set") < first_time(t0, "iris/camera/#") - 0.4,
          f"{first_time(t0, 'test/led/set') - t0:.2f} vs {first_time(t0, 'iris/camera/#') - t0:.2f}")
    check("U1 LED at chosen brightness (100%)", since(t0, "test/led/brightness") == [b"255"], str(since(t0, "test/led/brightness")))
    check("U1 door-open LED untouched", led(t0, "led2") == [], str(led(t0, "led2")))
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    check("U1 one notification", len(n) == 1, str(n))
    if n:
        check("U1 title", n[0]["title"] == "🏠 AN NINH › NGƯỜI NHÀ VỀ", n[0]["title"])
        check("U1 message", n[0]["message"] == "Bình đã về, cửa đã mở (khớp 72%).", n[0]["message"])
        check("U1 photo + iOS image, no unlock button", n[0]["photo"] == SNAP_UNLOCK and n[0]["ios_data"] == {"image": "/media/local/snapshots/iris_cua.jpg"}, str(n[0]))
        check("U1 phones + telegram", n[0]["phones"] == ["brians_iphone"] and n[0]["telegram"] is True, str(n[0]))
        check("U1 photo is this event's image", snap_bytes(SNAP_UNLOCK) == images.get(first["event_id"]))
    check("U1 spoke one personal greeting in Vietnamese", len(s) == 1 and s[0]["message"] in BINH_GREETINGS and s[0]["language"] == "vi", str(s))
    if s:
        check("U1 spoke at 40% volume", s[0]["volume"] == 0.4, str(s[0]))
    check("U1 volume set once (speaker was off, old volume unknown)", wait_until(lambda: volumes(t0) == [0.4], 4) and (time.sleep(3) or volumes(t0) == [0.4]), str(volumes(t0)))
    time.sleep(1)

    check("U2 trigger during a run is dropped", presses(t_busy) == [], str(presses(t_busy)))
    # U2b cooldown: right after the run, still inside 5 s of the last shot -> no press
    t0 = time.time()
    if time.time() - t_busy < 4:
        motion()
        time.sleep(1.5)
        check("U2b cooldown blocks a new shot", presses(t0) == [], str(presses(t0)))
    time.sleep(5)
    relock()

    # U3 event button: double ignored, single -> acquaintance -> notify + 'not allowed' speech + unlock button
    t0 = time.time()
    client.publish("test/button", json.dumps({"event_type": "double"}), qos=1)
    time.sleep(1.5)
    check("U3 double press ignored", presses(t0) == [], str(presses(t0)))
    responses.append([ev("known", "Lan", 81)])
    client.publish("test/button", json.dumps({"event_type": "single"}), qos=1)
    check("U3 single press presses IRIS", wait_until(lambda: len(presses(t0)) == 1, 5))
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    lan_note = n[0] if n else {}
    check("U3 acquaintance notification", len(n) == 1 and lan_note["title"] == "👋 AN NINH › NGƯỜI QUEN"
          and lan_note["message"] == "Lan đang ở cửa (khớp 81%), chưa có trong danh sách được mở cửa.", str(n))
    ios = lan_note.get("ios_data", {})
    check("U3 unlock button on notification", ios.get("actions") == [{"action": "IRIS_UNLOCK_IRIS_DOOR_TEST", "title": "🔓 Mở cửa", "authenticationRequired": True}]
          and ios.get("action_data", {}).get("person") == "Lan", str(ios))
    check("U3 spoke 'not allowed'", [x["message"] for x in s] == ["Xin chào Lan. Bạn chưa được phép mở cửa, vui lòng chờ chủ nhà một chút nhé."], str(s))
    check("U3 no unlock / light", since(t0, "test/lock/set") == [] and since(t0, "test/light/set") == [])

    # U3b owner taps "Mở cửa" on that notification
    t1 = time.time()
    client.publish("test/fire_action", json.dumps({"action": "IRIS_UNLOCK_IRIS_DOOR_TEST", "action_data": ios.get("action_data", {})}), qos=1)
    check("U3b remote unlock sent", wait_until(lambda: since(t1, "test/lock/set") == [b"UNLOCK"], 6), str(since(t1, "test/lock/set")))
    wait_until(lambda: len(notes(t1)) >= 1 and len(says(t1)) >= 1, 10)
    n, s = notes(t1), says(t1)
    check("U3b remote unlock notification", len(n) == 1 and n[0]["title"] == "🔓 AN NINH › MỞ CỬA TỪ XA"
          and n[0]["message"] == "Đã mở cửa cho Lan từ điện thoại.", str(n))
    check("U3b spoke welcome", [x["message"] for x in s] == ["Mời Lan vào nhà."], str(s))
    time.sleep(3)
    relock()

    # U3c an old notification button does not unlock
    t1 = time.time()
    client.publish("test/fire_action", json.dumps({"action": "IRIS_UNLOCK_IRIS_DOOR_TEST", "action_data": {"person": "Lan", "ts": int(time.time()) - 3600}}), qos=1)
    client.publish("test/fire_action", json.dumps({"action": "SOMETHING_ELSE", "action_data": {"person": "Lan", "ts": int(time.time())}}), qos=1)
    wait_until(lambda: len(notes(t1)) >= 1, 8)
    n = notes(t1)
    check("U3c expired button refused", len(n) == 1 and n[0]["title"] == "⏰ AN NINH › NÚT MỞ CỬA ĐÃ HẾT HẠN" and since(t1, "test/lock/set") == [], str(n))
    time.sleep(3)

    # U4 review first, retry -> known allowed ('táo' in list, 'Táo' from IRIS)
    t0 = time.time()
    responses.append([ev("review", "Táo", 47)])
    responses.append([ev("known", "Táo", 66)])
    motion()
    check("U4 retried after 'review' (2 presses)", wait_until(lambda: len(presses(t0)) == 2, 10), str(presses(t0)))
    check("U4 unlock after retry", wait_until(lambda: since(t0, "test/lock/set") == [b"UNLOCK"], 8), str(since(t0, "test/lock/set")))
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    check("U4 one 'home' notification only", [x["title"] for x in n] == ["🏠 AN NINH › NGƯỜI NHÀ VỀ"] and n[0]["message"] == "Táo đã về, cửa đã mở (khớp 66%).", str(n))
    check("U4 Táo greeting", [x["message"] for x in s] == ["Táo ơi, mừng con về nhà!"], str(s))
    time.sleep(5)
    relock()

    # U5 lock jammed -> failure notice + apology
    state["jam"] = True
    t0 = time.time()
    responses.append([ev("known", "Bình", 80)])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1, 25)
    n, s = notes(t0), says(t0)
    check("U5 unlock failed notification", len(n) == 1 and n[0]["title"] == "⚠️ AN NINH › MỞ KHÓA THẤT BẠI"
          and n[0]["message"] == "Nhận ra Bình nhưng không mở được khóa (đang khóa).", str(n))
    if n:
        check("U5 time-sensitive push", n[0]["ios_data"].get("push") == {"interruption-level": "time-sensitive"}, str(n[0]["ios_data"]))
    wait_until(lambda: len(says(t0)) >= 1, 5)
    check("U5 apology spoken", [x["message"] for x in says(t0)] == ["Xin lỗi Bình, khóa cửa chưa mở được. Vui lòng thử lại."], str(says(t0)))
    check("U5 no light when unlock failed", since(t0, "test/light/set") == [])
    state["jam"] = False
    time.sleep(5)

    # U6 stranger -> alert with photo, unlock button, waiting message (LED already on: left alone)
    client.publish("test/led/state", "ON", qos=1, retain=True)
    time.sleep(0.5)
    t0 = time.time()
    stranger = ev("unknown", "Unknown Visitor", 0)
    responses.append([stranger])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    check("U6 single press (no retry for strangers)", len(presses(t0)) == 1, str(presses(t0)))
    check("U6 stranger notification", len(n) == 1 and n[0]["title"] == "🚨 AN NINH › NGƯỜI LẠ Ở CỬA" and n[0]["message"] == "Có người lạ ở cửa (Cổng).", str(n))
    if n:
        ios = n[0]["ios_data"]
        check("U6 photo + push + unlock button for 'khách'", n[0]["photo"] == SNAP_UNLOCK and ios.get("push") == {"interruption-level": "time-sensitive"}
              and ios.get("action_data", {}).get("person") == "khách" and snap_bytes(SNAP_UNLOCK) == images.get(stranger["event_id"]), str(ios))
    check("U6 waiting message spoken", [x["message"] for x in s] == ["Xin chào, chủ nhà đã nhận được thông báo. Vui lòng chờ trong giây lát."], str(s))
    check("U6 no unlock", since(t0, "test/lock/set") == [])
    check("U6 LED that was already on is left on", led(t0) == [], str(led(t0)))
    client.publish("test/led/state", "OFF", qos=1, retain=True)
    time.sleep(5)

    # U7 no face twice -> retried once, then silent (no_face not notified by default)
    t0 = time.time()
    responses.append([ev("no_face", "No face detected", 0, faces=None)])
    responses.append([ev("no_face", "No face detected", 0, faces=None)])
    motion()
    check("U7 retried once", wait_until(lambda: len(presses(t0)) == 2, 8), str(presses(t0)))
    time.sleep(3)
    check("U7 silent", notes(t0) == [] and says(t0) == [], str(notes(t0)) + str(says(t0)))
    time.sleep(3)

    # U8 IRIS skips the shot (camera cooldown in IRIS) -> timeout notice, nothing spoken
    t0 = time.time()
    motion()
    wait_until(lambda: len(notes(t0)) >= 1, 12)
    n = notes(t0)
    check("U8 timeout notification", len(n) == 1 and n[0]["title"] == "⚠️ AN NINH › IRIS KHÔNG TRẢ LỜI"
          and n[0]["message"].startswith("IRIS không nhận diện được: IRIS không trả kết quả sau 6 giây") and n[0]["photo"] == "", str(n))
    check("U8 nothing spoken", says(t0) == [], str(says(t0)))
    time.sleep(5)

    # U9 two faces, allowed person reaches HA first -> no auto unlock
    t0 = time.time()
    responses.append([ev("known", "Bình", 77, faces=2), ev("unknown", "Unknown Visitor", 0, faces=2)])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    check("U9 blocked: two faces", len(n) == 1 and n[0]["title"] == "🚪 AN NINH › NGƯỜI NHÀ (CHƯA MỞ CỬA)"
          and n[0]["message"] == "Bình ở cửa (khớp 77%) nhưng không tự mở: ảnh có 2 khuôn mặt.", str(n))
    check("U9 blocked speech", [x["message"] for x in s] == ["Xin chào Bình. Cửa chưa tự mở lúc này, chủ nhà đã nhận được thông báo."], str(s))
    check("U9 no unlock", since(t0, "test/lock/set") == [])
    time.sleep(5)

    # U10 a result from another camera arrives first -> ignored, own camera result used
    t0 = time.time()
    responses.append([ev("known", "Bình", 90, camera="Sân sau"), ev("unknown", "Unknown Visitor", 0)])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1, 12)
    n = notes(t0)
    check("U10 other camera ignored", len(n) == 1 and n[0]["title"] == "🚨 AN NINH › NGƯỜI LẠ Ở CỬA", str(n))
    check("U10 no unlock from other camera", since(t0, "test/lock/set") == [])
    time.sleep(5)

    # U11 IRIS test-page upload while idle -> ignored entirely
    t0 = time.time()
    publish_result([ev("known", "Bình", 95, camera="Test upload")])
    time.sleep(3)
    check("U11 idle results ignored", notes(t0) == [] and says(t0) == [] and since(t0, "test/lock/set") == [])
    time.sleep(3)

    # U12 LED already on (someone switched it on) -> not touched, not switched off afterwards
    client.publish("test/led/state", "ON", qos=1, retain=True)
    time.sleep(1)
    t0 = time.time()
    responses.append([ev("unknown", "Unknown Visitor", 0)])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1, 12)
    time.sleep(3)
    check("U12 LED already on is left alone", led(t0) == [], str(led(t0)))
    client.publish("test/led/state", "OFF", qos=1, retain=True)
    time.sleep(5)


def greeting_scenarios() -> None:
    # G1 door opens, nothing recent -> LED + shot -> family greeting + Telegram only
    relock()
    t0 = time.time()
    responses.append([ev("known", "Táo", 70)])
    door_open()
    check("G1 door open presses IRIS", wait_until(lambda: len(presses(t0)) == 1, 5), str(presses(t0)))
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    n, s = notes(t0), says(t0)
    check("G1 greeting", [x["message"] for x in s] == ["Táo ơi, mừng con về nhà!"], str(s))
    check("G1 Telegram only, family title", len(n) == 1 and n[0]["title"] == "🏡 CỬA CHÍNH › NGƯỜI NHÀ VỀ" and n[0]["phones"] == []
          and n[0]["message"].startswith("Táo vừa về nhà. Chúc buổi "), str(n))
    if n:
        check("G1 photo attached", n[0]["photo"] == SNAP_UNLOCK, str(n[0]["photo"]))
    check("G1 door-open LED on for the shot, then off", wait_until(lambda: led(t0, "led2") == [b"ON", b"OFF"], 8), str(led(t0, "led2")))
    check("G1 unlock LED untouched", led(t0) == [], str(led(t0)))
    check("G1 no unlock while greeting", since(t0, "test/lock/set") == [])
    time.sleep(3)
    # G1b door still open -> motion does not start an unlock shot
    t1 = time.time()
    motion()
    time.sleep(2)
    check("G1b no unlock shot while the door is open", presses(t1) == [], str(presses(t1)))
    door_close()

    # G2 door re-opened 2 s after closing -> nothing
    time.sleep(2)
    t0 = time.time()
    door_open()
    time.sleep(3)
    check("G2 quick re-open: no shot, no greeting", presses(t0) == [] and says(t0) == [], str(presses(t0)))
    door_close()
    time.sleep(6)

    # G3 family member unlocked by face -> door opens -> no second greeting, no shot
    t0 = time.time()
    responses.append([ev("known", "Bình", 74)])
    motion()
    check("G3 unlocked", wait_until(lambda: since(t0, "test/lock/set") == [b"UNLOCK"], 8), str(since(t0, "test/lock/set")))
    wait_until(lambda: len(says(t0)) >= 1, 10)
    time.sleep(3)
    t1 = time.time()
    door_open()
    time.sleep(4)
    check("G3 no extra shot after unlock", len(presses(t0)) == 1, str(presses(t0)))
    check("G3 not greeted twice", says(t1) == [] and notes(t1) == [], str(says(t1)) + str(notes(t1)))
    door_close()
    time.sleep(6)
    relock()

    # G4 acquaintance waits at the door -> owner taps "Mở cửa" -> door opens -> greeted without a new shot
    t0 = time.time()
    lan = ev("known", "Lan", 63)
    responses.append([lan])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    ios = notes(t0)[0].get("ios_data", {}) if notes(t0) else {}
    t1 = time.time()
    client.publish("test/fire_action", json.dumps({"action": "IRIS_UNLOCK_IRIS_DOOR_TEST", "action_data": ios.get("action_data", {})}), qos=1)
    check("G4 remote unlock", wait_until(lambda: since(t1, "test/lock/set") == [b"UNLOCK"], 6), str(since(t1, "test/lock/set")))
    time.sleep(3)
    t2 = time.time()
    responses.append([ev("no_face", "No face detected", 0, faces=None)])  # Lan already stepped past the camera
    responses.append([ev("no_face", "No face detected", 0, faces=None)])
    door_open()
    wait_until(lambda: len(notes(t2)) >= 1 and len(says(t2)) >= 1, 12)
    check("G4 new shot (with door-open LED), nobody in it -> earlier result used", len(presses(t2)) == 2
          and led(t2, "led2")[:1] == [b"ON"] and led(t2) == [], str(presses(t2)) + str(led(t2)) + str(led(t2, "led2")))
    check("G4 acquaintance greeting", [x["message"] for x in says(t2)] == ["Xin chào Lan, rất vui được gặp bạn!"], str(says(t2)))
    check("G4 acquaintance message", [(x["title"], x["message"]) for x in notes(t2)] == [("👋 CỬA CHÍNH › KHÁCH QUEN", "Lan vừa đến chơi nhà.")], str(notes(t2)))
    door_close()
    time.sleep(6)
    relock()

    # G5 strangers (two faces) when the door opens -> guest greeting + group line
    t0 = time.time()
    responses.append([ev("unknown", "Unknown Visitor", 0, faces=2), ev("unknown", "Unknown Visitor", 0, faces=2)])
    door_open()
    wait_until(lambda: len(notes(t0)) >= 1 and len(says(t0)) >= 1, 12)
    check("G5 guest greeting + group", [x["message"] for x in says(t0)] == ["Xin chào quý khách, chào mừng đến chơi nhà! Chào mừng mọi người!"], str(says(t0)))
    check("G5 guest message", [(x["title"], x["message"]) for x in notes(t0)] == [("🙋 CỬA CHÍNH › KHÁCH LẠ", "Có khách lạ vừa vào nhà. Ảnh có 2 khuôn mặt.")], str(notes(t0)))
    door_close()
    time.sleep(6)

    # G6 someone walks out (no face twice) -> retried once, silent, LED stays on across retries
    t0 = time.time()
    responses.append([ev("no_face", "No face detected", 0, faces=None)])
    responses.append([ev("no_face", "No face detected", 0, faces=None)])
    door_open()
    check("G6 retried once", wait_until(lambda: len(presses(t0)) == 2, 8), str(presses(t0)))
    time.sleep(3)
    check("G6 silent", notes(t0) == [] and says(t0) == [], str(notes(t0)) + str(says(t0)))
    check("G6 door-open LED on once across retries, then off", led(t0, "led2") == [b"ON", b"OFF"], str(led(t0, "led2")))
    door_close()
    time.sleep(6)

    # G7 a stranger was at the door a minute ago, then Táo comes home with a key/fingerprint
    relock()
    t0 = time.time()
    responses.append([ev("unknown", "Unknown Visitor", 0)])
    motion()
    wait_until(lambda: len(notes(t0)) >= 1, 12)
    time.sleep(8)
    t1 = time.time()
    responses.append([ev("known", "Táo", 68)])
    door_open()
    wait_until(lambda: len(says(t1)) >= 1 and len(notes(t1)) >= 1, 12)
    check("G7 fresh shot wins over the old stranger result", len(presses(t1)) == 1
          and [x["message"] for x in says(t1)] == ["Táo ơi, mừng con về nhà!"]
          and [x["title"] for x in notes(t1)] == ["🏡 CỬA CHÍNH › NGƯỜI NHÀ VỀ"], str(says(t1)) + str(notes(t1)))
    door_close()
    time.sleep(6)


def offline_scenarios() -> None:
    # O1 IRIS offline > 1 min -> alert; motion while offline does nothing; back online -> notice
    t0 = time.time()
    client.publish("iris/availability", "offline", qos=1, retain=True)
    time.sleep(3)
    motion()
    time.sleep(3)
    check("O1 no press while IRIS offline", presses(t0) == [], str(presses(t0)))
    wait_until(lambda: len(notes(t0)) >= 1, 75)
    n = notes(t0)
    check("O1 offline alert", len(n) == 1 and n[0]["title"] == "🔌 AN NINH › IRIS MẤT KẾT NỐI", str(n))
    t1 = time.time()
    client.publish("iris/availability", "online", qos=1, retain=True)
    wait_until(lambda: len(notes(t1)) >= 1, 10)
    n = notes(t1)
    check("O1 back-online notice", len(n) == 1 and n[0]["title"] == "✅ AN NINH › IRIS ĐÃ KẾT NỐI LẠI" and "sau 1 phút" in n[0]["message"], str(n))


def run() -> None:
    client.connect("127.0.0.1", PORT)
    client.loop_start()
    t_start = time.time()
    wait_until(lambda: any(p == b"online" for p in since(0, "homeassistant/status")), 90)
    time.sleep(8)
    check("startup: no notification, no speech, no press", notes(t_start) == [] and says(t_start) == [] and presses(t_start) == [],
          str(notes(t_start)) + str(says(t_start)))
    only = sys.argv[2] if len(sys.argv) > 2 else "all"
    if only in ("all", "unlock"):
        unlock_scenarios()
    if only in ("all", "greet"):
        greeting_scenarios()
    if only in ("all", "offline"):
        offline_scenarios()
    client.loop_stop()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    {"setup": setup, "run": run}[sys.argv[1]]()
