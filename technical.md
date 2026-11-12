[English](technical.md) | [Tiếng Việt](technical_vi.md)

# IRIS Technical Notes

## Architecture

- Frontend: React 19, TanStack Router/Start, Vite.
- Backend: FastAPI, SQLite, InsightFace, ONNX Runtime, MQTT.
- Data root: configured by `IRIS_DATA_DIR`, containing `database/`, `uploads/`, and `models/`. Application logs are stored in SQLite.

`backend/app/insightface_engine.py` owns model initialization, detection, normalized embeddings, and cosine similarity. `person_faces.embedding` stores reference embeddings. Recognition data is not sent to an external face-recognition service.

## Recognition path

1. Decode the image, detect faces and keep up to `max_faces` of them, largest first. Extra faces that are tiny (< 40 px) or have a detection score < 0.6 are skipped.
2. Generate a normalized embedding with InsightFace for each face.
3. Compare it with active reference embeddings using cosine similarity.
4. Classify it as unknown, review, or known using the configured thresholds. Each face is its own event; the largest face keeps the request's `event_id`, the others are returned in `additional_events`.
5. Reuse the same inference output for face details.
6. Publish the MQTT decision immediately through the persistent connection (extra faces first, the largest face last so the `Latest Person` sensor ends on the main face).
7. Generate thumbnails/crops and publish the MQTT image in a background thread.

Default model is `buffalo_s` and is downloaded automatically on startup. Default match/auto-accept thresholds are 40/55. Calibrate them against the actual cameras.

## InsightFace configuration

- `model_name`: `antelopev2`, `buffalo_l`, `buffalo_m`, or `buffalo_s`;
- `provider`: ONNX CPU, CUDA, or Intel OpenVINO CPU/iGPU/NPU/Auto;
- `det_size`: 320–1280;
- `age_gender_enabled`: loads `genderage` only when enabled; defaults to `false` for lower latency.
- `max_faces`: 1–10 faces per image; defaults to 1.

Changing model packs rebuilds reference embeddings, preferring the face crop `person_faces.image_path` over `source_image_path` (the original can be a group photo). Training from an event picks that event's face using the original bounding box stored in `face_details_json`. Other runtime changes clear the engine cache without rebuilding embeddings.

## MQTT

- One persistent client `<device_id>_iris` for both publishing and commands (`MqttBridge` in `mqtt_homeassistant.py`).
- Last Will: `<base>/availability` = `offline` (retained). On connect: `online`, subscribe to `<base>/camera/+/trigger/set` and `<discovery_prefix>/status`, then republish discovery, state and the latest image.
- `homeassistant/status` = `online` (Home Assistant restart) also republishes discovery.
- Only events with `notified = 1` feed the retained state and latest image; Test-page uploads without _Send to Home Assistant_ are stored with `notified = 0`.
- Events and state use QoS 1 (paho keeps up to 500 messages while disconnected); `latest_image` uses QoS 0.
- Debugging: `GET /api/mqtt/status`, `GET|DELETE /api/mqtt/messages`, and the **MQTT Monitor** page.

## Home Assistant ingress

The Supervisor serves the add-on under `/api/hassio_ingress/<token>/` and strips that prefix before forwarding into the container, adding an `X-Ingress-Path` header.

- `docker/web-server.mjs` puts the prefix back on the URL before SSR.
- `src/router.tsx` uses a TanStack Router `rewrite` to add/strip the prefix (TanStack Start always overrides `basepath` with its build-time value).
- `src/lib/http.ts` adds the prefix to the API base; `src/lib/basepath.ts` provides `appPath()` for absolute links.
- `docker/nginx.conf` rewrites `"/assets/` in HTML with `sub_filter`; `vite.config.ts` (`renderBuiltUrl`) makes chunk preloads follow the page path.

## Main API

- `PUT /api/settings/insightface`
- `POST /api/settings/insightface/test`
- `POST /api/recognize` (also returns `additional_events` when several faces are found)
- `POST /api/people/{person_id}/faces`
- `GET|POST /api/cameras/trigger/{trigger_slug}`
- `GET /api/analytics?days=7&tz_offset_minutes=420`
- `GET /api/mqtt/status`, `GET|DELETE /api/mqtt/messages`
- `POST /api/settings/data/clear`

## Engineering rules

- Keep inference in `insightface_engine.py`.
- Keep MQTT in `mqtt_homeassistant.py`.
- Do not store raw images in embeddings.
- Publish the MQTT decision before image processing.
- Do not edit `src/routeTree.gen.ts` manually.

## Verification

```bash
python -m py_compile backend/app/*.py
npm run lint
npm run build
```

MQTT, multi-face and ingress checks: see [tests/README.md](tests/README.md).

## Licensing

InsightFace code is MIT-licensed, while InsightFace-provided pretrained models are restricted by their provider to non-commercial research use. See [README.md](README.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
