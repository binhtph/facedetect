from __future__ import annotations

import json
import shutil
import threading
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort
from insightface.app import FaceAnalysis
from PIL import Image

from .db import MODEL_DIR


class InsightFaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class InsightFaceConfig:
    model_name: str = "buffalo_s"
    provider: str = "CPUExecutionProvider"
    det_size: int = 640
    age_gender_enabled: bool = False

    @property
    def configured(self) -> bool:
        return True


_lock = threading.Lock()
_engines: dict[tuple[str, str, int, bool], FaceAnalysis] = {}
_model_root = MODEL_DIR
_supported_models = ("antelopev2", "buffalo_l", "buffalo_m", "buffalo_s")
_model_download_sizes = {
    "antelopev2": 360_662_982,
    "buffalo_l": 288_621_354,
    "buffalo_m": 275_951_529,
    "buffalo_s": 127_607_557,
}
_download_lock = threading.Lock()
_download_status: dict[str, dict[str, Any]] = {
    name: {
        "model_name": name,
        "status": "idle",
        "progress": 0,
        "size_bytes": _model_download_sizes[name],
        "error": None,
    }
    for name in _supported_models
}


def _is_model_downloaded(model_name: str) -> bool:
    model_dir = _model_root / "models" / model_name
    return model_dir.is_dir() and any(model_dir.glob("*.onnx"))


def model_download_status() -> list[dict[str, Any]]:
    with _download_lock:
        return [
            {
                **_download_status[name],
                "downloaded": _is_model_downloaded(name),
                "size_bytes": _model_download_sizes[name],
            }
            for name in _supported_models
        ]


def _download_model(model_name: str) -> None:
    archive = _model_root / "models" / f"{model_name}.zip.part"
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/deepinsight/insightface/releases/download/v0.7/{model_name}.zip"
        with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:  # noqa: S310
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                progress = min(90, int(downloaded * 90 / total)) if total else 0
                with _download_lock:
                    _download_status[model_name]["progress"] = progress

        target = _model_root / "models" / model_name
        temp_target = _model_root / "models" / f".{model_name}.extracting"
        shutil.rmtree(temp_target, ignore_errors=True)
        temp_target.mkdir(parents=True)
        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                destination = (temp_target / item.filename).resolve()
                if temp_target.resolve() not in destination.parents and destination != temp_target.resolve():
                    raise InsightFaceError("Invalid model archive.")
            package.extractall(temp_target)
        extracted = temp_target / model_name
        source = extracted if extracted.is_dir() else temp_target
        shutil.rmtree(target, ignore_errors=True)
        if source == temp_target:
            temp_target.rename(target)
        else:
            source.rename(target)
            shutil.rmtree(temp_target, ignore_errors=True)
        if not _is_model_downloaded(model_name):
            raise InsightFaceError("Downloaded archive does not contain ONNX models.")
        with _download_lock:
            _download_status[model_name].update(status="completed", progress=100, error=None)
    except Exception as error:  # noqa: BLE001
        with _download_lock:
            _download_status[model_name].update(status="error", error=str(error))
    finally:
        archive.unlink(missing_ok=True)


def start_model_download(model_name: str) -> dict[str, Any]:
    if model_name not in _supported_models:
        raise InsightFaceError("Unsupported model pack.")
    with _download_lock:
        state = _download_status[model_name]
        if state["status"] == "downloading":
            return {**state, "downloaded": False}
        if _is_model_downloaded(model_name):
            state.update(status="completed", progress=100, error=None)
            return {**state, "downloaded": True}
        state.update(status="downloading", progress=0, error=None)
    threading.Thread(target=_download_model, args=(model_name,), daemon=True).start()
    return {**state, "downloaded": False}


def delete_model(model_name: str) -> dict[str, Any]:
    if model_name not in _supported_models:
        raise InsightFaceError("Unsupported model pack.")
    with _download_lock:
        state = _download_status[model_name]
        if state["status"] == "downloading":
            raise InsightFaceError("Cannot delete a model while it is downloading.")
        clear_engine_cache()
        shutil.rmtree(_model_root / "models" / model_name, ignore_errors=True)
        state.update(status="idle", progress=0, error=None)
        return {**state, "downloaded": False}


def _provider_spec(provider: str) -> tuple[str, dict[str, str]]:
    openvino_devices = {
        "OpenVINOAUTO": "AUTO",
        "OpenVINOCPU": "CPU",
        "OpenVINOGPU": "GPU",
        "OpenVINONPU": "NPU",
    }
    if provider in openvino_devices:
        return "OpenVINOExecutionProvider", {"device_type": openvino_devices[provider]}
    return provider, {}


def _engine(config: InsightFaceConfig) -> FaceAnalysis:
    key = (config.model_name, config.provider, config.det_size, config.age_gender_enabled)
    with _lock:
        if key not in _engines:
            try:
                if not _is_model_downloaded(config.model_name):
                    raise InsightFaceError(
                        f"Model {config.model_name} is not downloaded yet. It can be downloaded from Settings."
                    )
                runtime_provider, provider_options = _provider_spec(config.provider)
                if runtime_provider not in ort.get_available_providers():
                    raise InsightFaceError(
                        f"{config.provider} is unavailable. Available providers: {', '.join(ort.get_available_providers())}"
                    )
                _model_root.mkdir(parents=True, exist_ok=True)
                app = FaceAnalysis(
                    name=config.model_name,
                    root=str(_model_root),
                    allowed_modules=[
                        "detection",
                        "recognition",
                        *(["genderage"] if config.age_gender_enabled else []),
                    ],
                    providers=[runtime_provider],
                    provider_options=[provider_options],
                )
                app.prepare(
                    ctx_id=0 if config.provider == "CUDAExecutionProvider" else -1,
                    det_size=(config.det_size, config.det_size),
                )
                _engines[key] = app
            except InsightFaceError:
                raise
            except Exception as error:  # noqa: BLE001
                raise InsightFaceError(f"Cannot initialize InsightFace: {error}") from error
    return _engines[key]


def _decode(image_bytes: bytes) -> np.ndarray:
    try:
        rgb = np.asarray(Image.open(BytesIO(image_bytes)).convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as error:  # noqa: BLE001
        raise InsightFaceError("Invalid image.") from error


def _largest_face(config: InsightFaceConfig, image_bytes: bytes):
    image = _decode(image_bytes)
    try:
        faces = _engine(config).get(image)
    except Exception as error:  # noqa: BLE001
        raise InsightFaceError(f"Face analysis failed: {error}") from error
    if not faces:
        return image, None
    return image, max(faces, key=lambda face: float((face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])))


def _bounding_box(face: Any, image: np.ndarray) -> dict[str, float]:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = [float(value) for value in face.bbox]
    return {
        "Left": max(0.0, x1 / width),
        "Top": max(0.0, y1 / height),
        "Width": max(0.0, min(1.0, (x2 - x1) / width)),
        "Height": max(0.0, min(1.0, (y2 - y1) / height)),
    }


def _face_details(
    config: InsightFaceConfig,
    face: Any,
    image: np.ndarray,
    inference_id: str,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    points = getattr(face, "kps", None)
    landmarks = [
        {"X": float(point[0]) / width, "Y": float(point[1]) / height}
        for point in (points if points is not None else [])
    ]
    details = {
        "confidence": round(float(face.det_score) * 100, 2),
        "bounding_box": _bounding_box(face, image),
        "landmarks": landmarks,
        "model": config.model_name,
        "provider": config.provider,
        "inference_id": inference_id,
    }
    if config.age_gender_enabled:
        age = getattr(face, "age", None)
        gender = getattr(face, "gender", None)
        details["age"] = int(age) if age is not None else None
        details["gender"] = "male" if gender == 1 else "female" if gender == 0 else None
    return details


def index_face(config: InsightFaceConfig, image_bytes: bytes, person_id: str) -> dict[str, Any]:
    image, face = _largest_face(config, image_bytes)
    if face is None:
        raise InsightFaceError("No usable face was detected in this image.")
    embedding = np.asarray(face.normed_embedding, dtype=np.float32)
    return {
        "face_id": uuid.uuid4().hex,
        "person_id": person_id,
        "embedding": json.dumps(embedding.tolist(), separators=(",", ":")),
        "confidence": round(float(face.det_score) * 100, 2),
        "bounding_box": _bounding_box(face, image),
        "inference_id": uuid.uuid4().hex,
    }


def search_face(
    config: InsightFaceConfig,
    image_bytes: bytes,
    references: list[dict[str, Any]],
    threshold: float,
    max_faces: int = 1,
) -> dict[str, Any]:
    image, face = _largest_face(config, image_bytes)
    inference_id = uuid.uuid4().hex
    if face is None:
        return {"matches": [], "bounding_box": None, "inference_id": inference_id, "face_detected": False}
    query = np.asarray(face.normed_embedding, dtype=np.float32)
    matches: list[dict[str, Any]] = []
    for reference in references:
        try:
            embedding = np.asarray(json.loads(reference["embedding"]), dtype=np.float32)
            similarity = max(0.0, float(np.dot(query, embedding))) * 100
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if similarity >= threshold:
            matches.append({
                "face_id": reference["face_id"],
                "person_id": reference["person_id"],
                "similarity": round(similarity, 2),
            })
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return {
        "matches": matches[:max_faces],
        "bounding_box": _bounding_box(face, image),
        "face_details": _face_details(config, face, image, inference_id),
        "inference_id": inference_id,
        "face_detected": True,
    }


def clear_engine_cache() -> None:
    with _lock:
        _engines.clear()


def reset_model_storage() -> None:
    with _download_lock:
        if any(state["status"] == "downloading" for state in _download_status.values()):
            raise InsightFaceError("Cannot clear data while a model is downloading.")
        clear_engine_cache()
        shutil.rmtree(_model_root, ignore_errors=True)
        _model_root.mkdir(parents=True, exist_ok=True)
        for state in _download_status.values():
            state.update(status="idle", progress=0, error=None)


def validate_config(config: InsightFaceConfig) -> None:
    _engine(config)
