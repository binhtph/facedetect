[English](technical.md) | [Tiếng Việt](technical_vi.md)

# IRIS Technical Notes

## Architecture

- Frontend: React 19, TanStack Router/Start, Vite.
- Backend: FastAPI, SQLite, InsightFace, ONNX Runtime, MQTT.
- Data root: configured by `IRIS_DATA_DIR`, containing `database/`, `uploads/`, and `models/`. Application logs are stored in SQLite.

`backend/app/insightface_engine.py` owns model initialization, detection, normalized embeddings, and cosine similarity. `person_faces.embedding` stores reference embeddings. Recognition data is not sent to an external face-recognition service.

## Recognition path

1. Decode the image and select the largest face.
2. Generate a normalized embedding with InsightFace.
3. Compare it with active reference embeddings using cosine similarity.
4. Classify it as unknown, review, or known using the configured thresholds.
5. Reuse the same inference output for face details.
6. Publish the MQTT decision immediately through the persistent connection.
7. Generate thumbnails/crops and publish the MQTT image in a background thread.

Default model is `buffalo_s` and is downloaded automatically on startup. Default match/auto-accept thresholds are 40/55. Calibrate them against the actual cameras.

## InsightFace configuration

- `model_name`: `antelopev2`, `buffalo_l`, `buffalo_m`, or `buffalo_s`;
- `provider`: ONNX CPU, CUDA, or Intel OpenVINO CPU/iGPU/NPU/Auto;
- `det_size`: 320–1280;
- `age_gender_enabled`: loads `genderage` only when enabled; defaults to `false` for lower latency.

Changing model packs rebuilds reference embeddings from `person_faces.source_image_path`. Other runtime changes clear the engine cache without rebuilding embeddings.

## Main API

- `PUT /api/settings/insightface`
- `POST /api/settings/insightface/test`
- `POST /api/recognize`
- `POST /api/people/{person_id}/faces`
- `GET|POST /api/cameras/trigger/{trigger_slug}`
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
npm run build
```

## Licensing

InsightFace code is MIT-licensed, while InsightFace-provided pretrained models are restricted by their provider to non-commercial research use. See [README.md](README.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
