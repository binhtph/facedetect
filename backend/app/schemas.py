from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InsightFaceSettingsIn(BaseModel):
    model_name: str = Field(default="buffalo_l", min_length=1)
    provider: Literal[
        "CPUExecutionProvider",
        "CUDAExecutionProvider",
        "OpenVINOAUTO",
        "OpenVINOCPU",
        "OpenVINOGPU",
        "OpenVINONPU",
    ] = "CPUExecutionProvider"
    det_size: int = Field(default=640, ge=320, le=1280)
    age_gender_enabled: bool = False


class PersonIn(BaseModel):
    name: str = Field(min_length=1)
    alias: str = ""
    role: Literal["Family", "Friend", "Employee", "Guest"] = "Guest"
    notes: str = ""
    status: Literal["Active", "Disabled"] = "Active"


class CameraIn(BaseModel):
    name: str = Field(min_length=1)
    model: str = ""
    status: Literal["online", "offline"] = "online"
    stream_url: str = ""
    still_url: str = ""
    face_detection: bool = True
    motion: bool = True
    cooldown: int = 60
    min_face: int = 8
    min_confidence: int = 80


class ThresholdsIn(BaseModel):
    match: int = Field(ge=0, le=100)
    auto_accept: int = Field(ge=0, le=100)


class LogsSettingsIn(BaseModel):
    max_rows: int = Field(ge=50, le=10000)


class StorageSettingsIn(BaseModel):
    max_storage_mb: int = Field(ge=256, le=102400)


class MqttSettingsIn(BaseModel):
    host: str = ""
    port: int = Field(default=1883, ge=1, le=65535)
    username: str = ""
    password: str = ""
    discovery_prefix: str = "homeassistant"
    base_topic: str = "iris"
    device_id: str = "iris_face_recognition"
    device_name: str = "IRIS Face Recognition"
    use_tls: bool = False


class TelegramSettingsIn(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
