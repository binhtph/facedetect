from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from .db import UPLOAD_DIR, new_id


def save_upload(upload: UploadFile, folder: str) -> tuple[str, bytes]:
    suffix = Path(upload.filename or "").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Only JPG and PNG images are supported.")
    path = UPLOAD_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{new_id('img')}{suffix}"
    with file_path.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    normalize_saved_image_orientation(file_path)
    data = file_path.read_bytes()
    return file_path.relative_to(UPLOAD_DIR).as_posix(), data


def save_image_bytes(data: bytes, folder: str, suffix: str = ".jpg") -> str:
    suffix = suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        suffix = ".jpg"
    path = UPLOAD_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{new_id('img')}{suffix}"
    file_path.write_bytes(data)
    normalize_saved_image_orientation(file_path)
    return file_path.relative_to(UPLOAD_DIR).as_posix()


def safe_upload_path(rel_path: str) -> Path | None:
    if not rel_path:
        return None
    normalized = rel_path.replace("\\", "/")
    file_path = (UPLOAD_DIR / normalized).resolve()
    try:
        file_path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return file_path


def save_image_variant(img: Image.Image, folder: str, prefix: str, quality: int = 82) -> str:
    path = UPLOAD_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{new_id(prefix)}.jpg"
    img.convert("RGB").save(file_path, format="JPEG", quality=quality, optimize=True)
    return file_path.relative_to(UPLOAD_DIR).as_posix()


def normalize_saved_image_orientation(file_path: Path) -> None:
    try:
        with Image.open(file_path) as img:
            oriented = ImageOps.exif_transpose(img)
            if oriented is img:
                return
            if file_path.suffix.lower() == ".png":
                oriented.save(file_path, format="PNG", optimize=True)
            else:
                oriented.convert("RGB").save(file_path, format="JPEG", quality=92, optimize=True)
    except Exception:
        return


def crop_box_from_bounding_box(
    bounding_box: dict,
    image_width: int,
    image_height: int,
    padding_px: int = 50,
) -> tuple[int, int, int, int] | None:
    left = float(bounding_box.get("Left", 0)) * image_width
    top = float(bounding_box.get("Top", 0)) * image_height
    box_width = float(bounding_box.get("Width", 0)) * image_width
    box_height = float(bounding_box.get("Height", 0)) * image_height
    if box_width <= 0 or box_height <= 0:
        return None

    x1 = max(0, int(left - padding_px))
    y1 = max(0, int(top - padding_px))
    x2 = min(image_width, int(left + box_width + padding_px))
    y2 = min(image_height, int(top + box_height + padding_px))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def adjusted_bounding_box(
    bounding_box: dict,
    image_width: int,
    image_height: int,
    crop_box: tuple[int, int, int, int],
) -> dict:
    x1, y1, x2, y2 = crop_box
    left = float(bounding_box.get("Left", 0)) * image_width
    top = float(bounding_box.get("Top", 0)) * image_height
    box_width = float(bounding_box.get("Width", 0)) * image_width
    box_height = float(bounding_box.get("Height", 0)) * image_height
    cropped_width = x2 - x1
    cropped_height = y2 - y1
    return {
        "Left": max(0, (left - x1) / cropped_width),
        "Top": max(0, (top - y1) / cropped_height),
        "Width": min(1, box_width / cropped_width),
        "Height": min(1, box_height / cropped_height),
    }


def create_event_images(rel_path: str, bounding_box: dict | None) -> tuple[str, str, dict | None]:
    file_path = safe_upload_path(rel_path)
    if not file_path or not file_path.exists():
        return "", "", bounding_box
    thumb_path = ""
    face_crop_path = ""
    adjusted_box = bounding_box
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            thumb = img.copy()
            thumb.thumbnail((420, 420), Image.Resampling.LANCZOS)
            thumb_path = save_image_variant(thumb, "thumbs", "thumb", quality=78)

            if bounding_box:
                width, height = img.size
                crop_box = crop_box_from_bounding_box(bounding_box, width, height)
                if crop_box:
                    cropped = img.crop(crop_box)
                    cropped.thumbnail((720, 720), Image.Resampling.LANCZOS)
                    face_crop_path = save_image_variant(cropped, "faces", "face", quality=85)
                    adjusted_box = adjusted_bounding_box(bounding_box, width, height, crop_box)
    except Exception:  # noqa: BLE001
        return thumb_path, face_crop_path, adjusted_box
    return thumb_path, face_crop_path, adjusted_box


def crop_saved_image_to_face(rel_path: str, bounding_box: dict | None, padding_px: int = 50) -> dict | None:
    if not rel_path or not bounding_box:
        return None
    file_path = safe_upload_path(rel_path)
    if not file_path or not file_path.exists():
        return None
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            width, height = img.size
            crop_box = crop_box_from_bounding_box(bounding_box, width, height, padding_px)
            if not crop_box:
                return None

            cropped = img.crop(crop_box)
            cropped.thumbnail((720, 720), Image.Resampling.LANCZOS)
            cropped.save(file_path, format="JPEG", quality=85, optimize=True)
            return adjusted_bounding_box(bounding_box, width, height, crop_box)
    except Exception:  # noqa: BLE001
        return None
    return None


def fetch_still_image(url: str) -> tuple[bytes, str]:
    if not url:
        raise HTTPException(status_code=400, detail="Camera still image URL is empty.")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "IRIS-Face-Recognition/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(status_code=502, detail=f"Could not fetch camera still image: {error}") from error
    suffix = ".png" if "png" in content_type else ".jpg"
    if not data:
        raise HTTPException(status_code=502, detail="Camera returned an empty image.")
    return data, suffix
