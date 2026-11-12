"""Multi-face recognition check with the real buffalo_s model and InsightFace sample images.

Usage: python -I tests/test_multiface.py <repo> <buffalo_s.zip>
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

REPO, MODEL_ZIP = sys.argv[1], sys.argv[2]
data_dir = Path(tempfile.mkdtemp(prefix="iris-mf-"))
os.environ["IRIS_DATA_DIR"] = str(data_dir)
model_dir = data_dir / "models" / "insightface" / "models" / "buffalo_s"
model_dir.mkdir(parents=True)
with zipfile.ZipFile(MODEL_ZIP) as archive:
    for member in archive.namelist():
        if member.endswith((".onnx",)) and ("det_500m" in member or "w600k_mbf" in member):
            (model_dir / Path(member).name).write_bytes(archive.read(member))
sys.path.insert(0, REPO)

import insightface  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from backend.app import main  # noqa: E402

from io import BytesIO  # noqa: E402

from PIL import Image  # noqa: E402

from backend.app import insightface_engine  # noqa: E402

samples = Path(insightface.__file__).parent / "data" / "images"
group = (samples / "t1.jpg").read_bytes()

# Reference: a generous crop around the largest face of the group photo.
_cfg = insightface_engine.InsightFaceConfig()
_img = insightface_engine._decode(group)  # noqa: SLF001
_faces = sorted(insightface_engine._engine(_cfg).get(_img), key=lambda f: -(f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))  # noqa: SLF001
print(f"detector sees {len(_faces)} faces in t1.jpg")
x1, y1, x2, y2 = [int(v) for v in _faces[0].bbox]
pad_x, pad_y = (x2 - x1), (y2 - y1)
pil = Image.open(BytesIO(group)).convert("RGB")
crop = pil.crop((max(0, x1 - pad_x), max(0, y1 - pad_y), min(pil.width, x2 + pad_x), min(pil.height, y2 + pad_y)))
crop = crop.resize((crop.width * 2, crop.height * 2))
buffer = BytesIO()
crop.save(buffer, format="PNG")
single = buffer.getvalue()


def ok(label: str) -> None:
    print(f"PASS  {label}", flush=True)


with TestClient(main.app) as api:
    person = api.post("/api/people", json={"name": "Tom Hanks", "role": "Guest"}).json()
    face = api.post(f"/api/people/{person['id']}/faces", files={"file": ("tom.png", single, "image/png")})
    assert face.status_code == 200, face.text
    ok("reference face indexed")

    # Default (max_faces = 1): same behaviour as before
    result = api.post("/api/recognize", files={"file": ("group.jpg", group, "image/jpeg")}, data={"notify": "false"}).json()
    assert result["additional_events"] == [], result.get("additional_events")
    assert result["person_id"] == person["id"] and result["type"] == "known", (result["person_name"], result["type"])
    ok("max_faces=1 -> one event for the group photo (old behaviour), largest face matched")

    single_result = api.post("/api/recognize", files={"file": ("tom.png", single, "image/png")}, data={"notify": "false"}).json()
    assert single_result["person_id"] == person["id"] and single_result["type"] == "known", single_result
    ok(f"known face still matched ({single_result['confidence']:.1f}%)")

    settings = api.get("/api/settings").json()
    saved = api.put(
        "/api/settings/insightface",
        json={"model_name": "buffalo_s", "provider": "CPUExecutionProvider", "det_size": settings["det_size"],
              "age_gender_enabled": False, "max_faces": 5},
    )
    assert saved.status_code == 200 and saved.json()["max_faces"] == 5, saved.text
    ok("max_faces setting saved")

    started = time.perf_counter()
    result = api.post("/api/recognize", files={"file": ("group.jpg", group, "image/jpeg")}, data={"notify": "false"}).json()
    elapsed = time.perf_counter() - started
    extra = result["additional_events"]
    assert 1 <= len(extra) <= 4, len(extra)
    all_events = [result, *extra]
    boxes = [e["face_bounding_box"] for e in all_events]
    assert len(set(map(str, boxes))) == len(all_events), "each event must have its own face box"
    assert all(e["image_path"] == result["image_path"] for e in extra), "events share the original image"
    ok(f"max_faces=5 -> {len(all_events)} events from one group photo in {elapsed:.2f}s")

    time.sleep(1.5)  # thumbnails/crops are produced in background threads
    for event_id in [e["id"] for e in all_events]:
        detail = api.get(f"/api/events/{event_id}").json()
        assert detail.get("face_crop_path"), detail
    ok("every face event gets its own face crop")

    unknowns = api.get("/api/unknowns").json()
    expected_unknown = sum(1 for e in all_events if e["type"] == "unknown")
    assert expected_unknown == len(all_events) - 1, [e["type"] for e in all_events]
    assert len(unknowns) == expected_unknown, (len(unknowns), expected_unknown)
    ok("unknown faces from the group photo are queued for review")

    # Training a person from an *extra* face must index that face, not the largest one.
    trained = {}
    for index, event in enumerate(extra[:2]):
        other = api.post("/api/people", json={"name": f"Guest {index}", "role": "Guest"}).json()
        response = api.post(f"/api/events/{event['id']}/train/{other['id']}")
        assert response.status_code == 200, response.text
        trained[other["id"]] = event["id"]
    again = api.post("/api/recognize", files={"file": ("group.jpg", group, "image/jpeg")}, data={"notify": "false"}).json()
    matched = {e["person_id"] for e in [again, *again["additional_events"]] if e.get("person_id")}
    assert set(trained) | {person["id"]} <= matched, (matched, trained)
    ok("training from extra faces indexes the right people (3 people recognized in one photo)")

    # Re-indexing stored reference faces (what a model change does) keeps each person's face.
    import json as _json
    import numpy as _np
    from backend.app.db import connect as _connect, rows_to_dicts as _rows
    with _connect() as conn:
        stored = _rows(conn.execute("SELECT person_id, image_path, source_image_path, embedding FROM person_faces").fetchall())
    cfg = main.insightface_config()
    for row in stored:
        fresh = main.index_stored_face(cfg, row)
        similarity = float(_np.dot(_np.array(_json.loads(row["embedding"])), _np.array(_json.loads(fresh["embedding"]))))
        assert similarity > 0.8, (row["person_id"], similarity)
    ok(f"model-change rebuild re-indexes the same face for all {len(stored)} references")

    stats = api.get("/api/analytics?days=7&tz_offset_minutes=420").json()
    summary = stats["summary"]
    assert summary["known"] >= 2 + 1 + 3, summary
    assert len(stats["daily"]) == 7 and stats["daily"][-1]["total"] == summary["total"], stats["daily"][-1]
    assert sum(h["count"] for h in stats["hourly"]) == summary["total"]
    assert stats["top_people"][0]["person_id"] == person["id"] and stats["top_people"][0]["count"] == 4, stats["top_people"]
    ok(f"analytics: {summary['total']} events, top person seen {stats['top_people'][0]['count']}x")
    assert api.get("/api/analytics?days=0").status_code == 422
    ok("analytics validates its range")

print("all multi-face checks passed")
