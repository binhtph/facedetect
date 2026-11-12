[English](README.md) | [Tiếng Việt](README_vi.md)

# IRIS Face Recognition

IRIS performs local face recognition with InsightFace. Images, embeddings, settings, and logs remain on the machine running the application; no cloud account is required.

## Versions and repositories

Current version: **2.0.1** (image `ghcr.io/binhtph/facedetect:2.0.1`). See [CHANGELOG.md](CHANGELOG.md).

| How to run            | Repository                                                                     |
| --------------------- | ------------------------------------------------------------------------------ |
| Standalone Docker     | [binhtph/facedetect](https://github.com/binhtph/facedetect) (this repository)  |
| Home Assistant add-on | [binhtph/ha-addons](https://github.com/binhtph/ha-addons), folder `facedetect` |

This project continues from the original author's Release 1.0:

- [anhnvme/facedetect](https://github.com/anhnvme/facedetect): standalone Docker.
- [anhnvme/hass-facedetect-addon](https://github.com/anhnvme/hass-facedetect-addon): Home Assistant add-on.

According to the original author, it is a basic face recognition app that has been running in several friends' homes for more than a year.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Open `http://127.0.0.1:8080`. The lightweight `buffalo_s` model is downloaded automatically on first startup.

Runtime options include:

- Model pack: `antelopev2`, `buffalo_l`, `buffalo_m`, or `buffalo_s`;
- Provider: ONNX CPU, Intel OpenVINO CPU/iGPU/NPU/Auto, or NVIDIA CUDA;
- Detection size: 320, 640, or 1280;
- Age/gender estimation: disabled by default for lower latency.

## Model and speed notes

InsightFace model packs trade accuracy, startup time, memory use, and CPU cost:

- `buffalo_s`: fastest and lightest. Recommended for CPU-only devices, mini PCs, Raspberry Pi-class hosts, or low-latency MQTT triggers.
- `buffalo_m`: balanced option for CPU if `buffalo_s` is not accurate enough.
- `buffalo_l`: heavier and usually more accurate, better when the host has a GPU/iGPU or a strong CPU.
- `antelopev2`: strong accuracy-oriented pack, but not the first choice for low-power CPU-only deployments.

Recommended CPU profile:

- Model: start with `buffalo_s`.
- Detection size: start with `320`; use `640` only if faces are missed.
- Age/gender: keep disabled unless needed.
- MQTT: the recognition result is published first; thumbnails are published afterward.

Detection size guidance:

- `320`: fastest. Use for close, clear, single-person camera views.
- `640`: default balance. Use when faces are smaller or detection misses happen.
- `1280`: slowest. Use only for distant faces, wide scenes, or crowded frames.

For Intel iGPU/OpenVINO in Docker, pass the DRM device into the container:

```yaml
services:
  iris:
    image: ghcr.io/binhtph/facedetect:latest
    ports:
      - "8080:80"
    volumes:
      - ./backend/data:/data
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - video
      - render
```

Then select an OpenVINO provider in Settings, for example OpenVINO CPU/iGPU/Auto. The host must have a working Intel graphics driver and `/dev/dri` available.

## MQTT and model setup

Configure MQTT and the model to suit your machine and use case:

- **Model:** pick one using [Model and speed notes](#model-and-speed-notes) above. Start with `buffalo_s` on modest hardware.
- **MQTT:** enter your broker in **Settings → MQTT**. IRIS keeps one persistent connection, reconnects by itself and republishes Home Assistant discovery after IRIS, the broker or Home Assistant restarts. The **MQTT Monitor** page shows the connection state and the messages sent/received.
- **Several people in one frame:** set **Settings → Faces per image** (default 1 = largest face only).
- **Test page:** uploads are **not** sent to MQTT/Telegram by default so they cannot trigger automations. Turn on **Send to Home Assistant & Telegram** to test the whole chain (sensors, `iris/event`, Telegram).

Every recognition publishes a message on `iris/event` (one per face) and updates sensors such as `Latest Person` and `Latest Recognition Event`. When IRIS loses its connection, the device shows as _Unavailable_ in Home Assistant.

Example automation that notifies when a known person is recognized:

```yaml
automation:
  - alias: IRIS - known person
    triggers:
      - trigger: mqtt
        topic: iris/event
    conditions:
      - condition: template
        value_template: "{{ trigger.payload_json.latest_type == 'known' }}"
    actions:
      - action: notify.notify
        data:
          message: "{{ trigger.payload_json.latest_person }} arrived at {{ trigger.payload_json.latest_camera }}"
```

## Adding cameras with go2rtc

IRIS does not watch video continuously. On every **trigger** it fetches **one still image** from the camera and recognizes it. The easiest way to get still images from RTSP cameras is [go2rtc](https://github.com/AlexxIT/go2rtc):

1. Add the camera to go2rtc, for example in `go2rtc.yaml`:

   ```yaml
   streams:
     front_gate: rtsp://user:pass@192.168.1.50:554/stream1
   ```

2. The camera's still image URL looks like:

   ```text
   http://<go2rtc-host>:1984/api/frame.jpeg?src=<camera_name>
   ```

   For example `http://192.168.1.10:1984/api/frame.jpeg?src=front_gate`. Open it in a browser; you should see a JPEG.

3. In IRIS open **Cameras → Add camera** and paste the link into **Still image URL**. Adjust **Cooldown** to avoid repeated recognitions.

4. Trigger recognition in one of two ways:
   - The **MQTT button** `Trigger <camera name>` that IRIS creates in Home Assistant (the entity id follows the camera name in IRIS), e.g. from an automation on motion or a doorbell press:

     ```yaml
     actions:
       - action: button.press
         target:
           entity_id: button.iris_face_recognition_trigger_front_gate
     ```

   - **HTTP:** `GET` or `POST` to `http://<IRIS-host>:8080/api/cameras/trigger/<slug>` (the full link is shown on the camera page).

## Home Assistant blueprint

[Import the blueprint into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fbinhtph%2Ffacedetect%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Firis_face_door.yaml) (`blueprints/automation/iris_face_door.yaml`). One automation for the front door with two features you can switch on separately, sharing people, greetings, speaker, LEDs and notifications:

- **Face unlock** (door closed): motion / button / any trigger → LED on → shot → family: unlock, light, a personal spoken greeting; acquaintance: notify, "not allowed" announcement and an **Unlock** button on the phone; stranger, unsure, no face, jammed lock, several faces, IRIS error or offline: notify with the reason.
- **Greeting when the door opens**: a family member who was just unlocked is not greeted twice; anyone else gets an LED-lit shot, then a spoken greeting and a Telegram message for family, acquaintances and guests (if the shot shows nobody, the recognition from while the door was closed is used).
- **Capture LEDs** for both moments (unlock shot, door-open shot), which can be different lights, each with its own switch; on just before the shot, off after recognition, never touching a light that was already on.

Notifications go through a script that takes `title`, `message`, `phones`, `ios_data`, `photo`, `telegram`. Greetings and messages accept `{name}` `{confidence}` `{camera}` `{buoi}` (time of day) `{gio}` (time) `{faces}` `{reason}` `{lock}`. With the blueprint, set the door camera **Cooldown** in IRIS low (0–5 s) and turn off Telegram in IRIS to avoid duplicate messages. Tests: `tests/blueprints/`.

## Important recommendations

- Use it in areas that **also have other physical security layers**; do not make IRIS the only condition for unlocking doors or disarming alarms.
- **Test thoroughly before relying on it**, with the real camera, mounting angle and day/night lighting.
- **Do not over-train one person with too many images**, especially blurry or bad-angle ones: it tends to increase false matches.

## Known issues

- **The displayed percentage is often not high**, yet in the original author's experience false matches are rare. The number is a similarity score (cosine similarity × 100), not a probability; defaults are match 40 / auto-accept 55.
- **No liveness / anti-spoofing check yet:** a printed photo or a photo on a phone screen held in front of the camera can be accepted as the real person. This is why physical security should be combined.
- The camera fields **Min face** and **Min confidence** are stored but **not applied yet** during recognition.
- Add-on: port `8080` has no login; prefer the Home Assistant sidebar.

## Persistent data

Docker stores all persistent data under `/data`, requiring only one mounted volume:

```text
/data/
├── database/iris.sqlite3
├── models/insightface/
└── uploads/
```

Local development defaults to `backend/data/`. Override the root with `IRIS_DATA_DIR`. Legacy layouts are migrated automatically at startup.

## Run a published image

```bash
docker run -d --name iris \
  -p 8080:80 \
  -v "${PWD}/backend/data:/data" \
  ghcr.io/binhtph/facedetect:2.0.1
```

Pushing the Git tag `v2.0.1` publishes the image as `2.0.1`, `2.0`, `2` and `latest`. Pushes to `main` only update `latest`, `main` and `sha-<commit>`.

## Third-party software and model licensing

IRIS is built with [InsightFace](https://github.com/deepinsight/insightface), created by the InsightFace contributors. InsightFace source code is provided under the MIT License; see its [official Python package licensing notice](https://github.com/deepinsight/insightface/tree/master/python-package#license).

Important: pretrained models distributed by InsightFace, including manually downloaded model packs, are provided by InsightFace for **non-commercial research purposes only**. The models are not owned or relicensed by this project. Review the [InsightFace licensing notice](https://github.com/deepinsight/insightface/tree/master/python-package) and obtain appropriate authorization before commercial use.

This project also uses ONNX Runtime, OpenCV, FastAPI, React, and other open-source dependencies. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the dependency manifests for attribution and license details.

Technical documentation: [technical.md](technical.md).
