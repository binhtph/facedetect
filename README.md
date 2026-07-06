[English](README.md) | [Tiếng Việt](README_vi.md)

# IRIS Face Recognition

IRIS performs local face recognition with InsightFace. Images, embeddings, settings, and logs remain on the machine running the application; no cloud account is required.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Open `http://127.0.0.1:8080`. Download the required model from Settings → InsightFace.

Runtime options include:

- Model pack: `antelopev2`, `buffalo_l`, `buffalo_m`, or `buffalo_s`;
- Provider: ONNX CPU, Intel OpenVINO CPU/iGPU/NPU/Auto, or NVIDIA CUDA;
- Detection size: 320, 640, or 1280;
- Age/gender estimation: disabled by default for lower latency.

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
