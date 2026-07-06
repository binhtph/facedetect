[English](README.md) | [Tiếng Việt](README_vi.md)

# IRIS Face Recognition

IRIS performs local face recognition with InsightFace. Images, embeddings, settings, and logs remain on the machine running the application; no cloud account is required.

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
    image: ghcr.io/anhnvme/facedetect:latest
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
  ghcr.io/anhnvme/facedetect:latest
```

Versioned images are also published as `1.2.3`, `1.2`, and `1` when a `v1.2.3` Git tag is pushed.

## Third-party software and model licensing

IRIS is built with [InsightFace](https://github.com/deepinsight/insightface), created by the InsightFace contributors. InsightFace source code is provided under the MIT License; see its [official Python package licensing notice](https://github.com/deepinsight/insightface/tree/master/python-package#license).

Important: pretrained models distributed by InsightFace, including manually downloaded model packs, are provided by InsightFace for **non-commercial research purposes only**. The models are not owned or relicensed by this project. Review the [InsightFace licensing notice](https://github.com/deepinsight/insightface/tree/master/python-package) and obtain appropriate authorization before commercial use.

This project also uses ONNX Runtime, OpenCV, FastAPI, React, and other open-source dependencies. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the dependency manifests for attribution and license details.

Technical documentation: [technical.md](technical.md).
