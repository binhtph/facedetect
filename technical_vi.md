[English](technical.md) | [Tiếng Việt](technical_vi.md)

# Ghi chú kỹ thuật IRIS

## Kiến trúc

- Frontend: React 19, TanStack Router/Start, Vite.
- Backend: FastAPI, SQLite, InsightFace, ONNX Runtime, MQTT.
- Data root: cấu hình bằng `IRIS_DATA_DIR`, gồm `database/`, `uploads/` và `models/`. Log ứng dụng nằm trong SQLite.

`backend/app/insightface_engine.py` quản lý model, phát hiện mặt, embedding chuẩn hóa và cosine similarity. `person_faces.embedding` lưu embedding tham chiếu. Dữ liệu nhận diện không được gửi tới dịch vụ nhận diện bên ngoài.

## Luồng nhận diện

1. Decode ảnh và chọn khuôn mặt lớn nhất.
2. InsightFace tạo normalized embedding.
3. So cosine similarity với các embedding đang hoạt động.
4. Phân loại unknown, review hoặc known theo ngưỡng cấu hình.
5. Tái sử dụng kết quả inference cho face details.
6. Publish MQTT decision ngay qua kết nối thường trực.
7. Tạo thumbnail/crop và publish ảnh MQTT trong thread nền.

Ngưỡng match/auto-accept mặc định là 40/55. Cần hiệu chỉnh theo camera thực tế.

## Cấu hình InsightFace

- `model_name`: `antelopev2`, `buffalo_l`, `buffalo_m` hoặc `buffalo_s`;
- `provider`: ONNX CPU, CUDA hoặc Intel OpenVINO CPU/iGPU/NPU/Auto;
- `det_size`: 320–1280;
- `age_gender_enabled`: chỉ load `genderage` khi bật; mặc định `false` để giảm latency.

Đổi model pack sẽ rebuild embedding tham chiếu từ `person_faces.source_image_path`. Các thay đổi runtime khác chỉ clear engine cache, không rebuild embedding.

## API chính

- `PUT /api/settings/insightface`
- `POST /api/settings/insightface/test`
- `POST /api/recognize`
- `POST /api/people/{person_id}/faces`
- `GET|POST /api/cameras/trigger/{trigger_slug}`
- `POST /api/settings/data/clear`

## Quy tắc kỹ thuật

- Giữ inference trong `insightface_engine.py`.
- Giữ MQTT trong `mqtt_homeassistant.py`.
- Không lưu raw image trong embedding.
- Publish MQTT decision trước khi xử lý ảnh.
- Không sửa tay `src/routeTree.gen.ts`.

## Kiểm tra

```bash
python -m py_compile backend/app/*.py
npm run build
```

## Giấy phép

Mã nguồn InsightFace dùng MIT License; pretrained model do InsightFace cung cấp bị giới hạn cho mục đích nghiên cứu phi thương mại. Xem [README_vi.md](README_vi.md) và [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
