[English](technical.md) | [Tiếng Việt](technical_vi.md)

# Ghi chú kỹ thuật IRIS

## Kiến trúc

- Frontend: React 19, TanStack Router/Start, Vite.
- Backend: FastAPI, SQLite, InsightFace, ONNX Runtime, MQTT.
- Data root: cấu hình bằng `IRIS_DATA_DIR`, gồm `database/`, `uploads/` và `models/`. Log ứng dụng nằm trong SQLite.

`backend/app/insightface_engine.py` quản lý model, phát hiện mặt, embedding chuẩn hóa và cosine similarity. `person_faces.embedding` lưu embedding tham chiếu. Dữ liệu nhận diện không được gửi tới dịch vụ nhận diện bên ngoài.

## Luồng nhận diện

1. Decode ảnh, phát hiện mặt và lấy tối đa `max_faces` khuôn mặt, lớn nhất trước. Mặt phụ quá nhỏ (< 40 px) hoặc độ tin cậy detect < 0.6 bị bỏ qua.
2. InsightFace tạo normalized embedding cho từng mặt.
3. So cosine similarity với các embedding đang hoạt động.
4. Phân loại unknown, review hoặc known theo ngưỡng cấu hình. Mỗi mặt là một event riêng; mặt lớn nhất giữ `event_id` của request, các mặt khác trả về trong `additional_events`.
5. Tái sử dụng kết quả inference cho face details.
6. Publish MQTT decision ngay qua kết nối thường trực (mặt phụ trước, mặt lớn nhất sau cùng để sensor `Latest Person` dừng ở mặt chính).
7. Tạo thumbnail/crop và publish ảnh MQTT trong thread nền.

Model mặc định là `buffalo_s` và được tự tải khi khởi động. Ngưỡng match/auto-accept mặc định là 40/55. Cần hiệu chỉnh theo camera thực tế.

## Cấu hình InsightFace

- `model_name`: `antelopev2`, `buffalo_l`, `buffalo_m` hoặc `buffalo_s`;
- `provider`: ONNX CPU, CUDA hoặc Intel OpenVINO CPU/iGPU/NPU/Auto;
- `det_size`: 320–1280;
- `age_gender_enabled`: chỉ load `genderage` khi bật; mặc định `false` để giảm latency.
- `max_faces`: 1–10 mặt mỗi ảnh; mặc định 1.

Đổi model pack sẽ rebuild embedding tham chiếu, ưu tiên ảnh crop `person_faces.image_path` rồi mới tới `source_image_path` (ảnh gốc có thể là ảnh nhóm). Train từ một event chọn đúng mặt của event đó theo bounding box gốc trong `face_details_json`. Các thay đổi runtime khác chỉ clear engine cache, không rebuild embedding.

## MQTT

- Một client thường trực `<device_id>_iris` cho cả publish lẫn nhận lệnh (`MqttBridge` trong `mqtt_homeassistant.py`).
- Last Will: `<base>/availability` = `offline` (retained). Khi kết nối: `online`, subscribe `<base>/camera/+/trigger/set` và `<discovery_prefix>/status`, rồi publish lại discovery, state và ảnh mới nhất.
- `homeassistant/status` = `online` (HA khởi động lại) cũng kích hoạt publish lại discovery.
- Event và state dùng QoS 1 (paho giữ tối đa 500 tin khi mất kết nối); ảnh `latest_image` dùng QoS 0.
- Debug: `GET /api/mqtt/status`, `GET|DELETE /api/mqtt/messages`, trang **MQTT Monitor**.

## Home Assistant ingress

Supervisor phục vụ add-on dưới `/api/hassio_ingress/<token>/` và bỏ prefix này trước khi chuyển request vào container, kèm header `X-Ingress-Path`.

- `docker/web-server.mjs` gắn lại prefix vào URL trước khi SSR.
- `src/router.tsx` dùng `rewrite` của TanStack Router để thêm/bỏ prefix (TanStack Start luôn ghi đè `basepath` lúc build).
- `src/lib/http.ts` thêm prefix vào API base; `src/lib/basepath.ts` có `appPath()` cho link tuyệt đối.
- `docker/nginx.conf` dùng `sub_filter` sửa `"/assets/` trong HTML; `vite.config.ts` (`renderBuiltUrl`) cho chunk preload theo đường dẫn trang.

## API chính

- `PUT /api/settings/insightface`
- `POST /api/settings/insightface/test`
- `POST /api/recognize` (trả thêm `additional_events` khi có nhiều mặt)
- `POST /api/people/{person_id}/faces`
- `GET|POST /api/cameras/trigger/{trigger_slug}`
- `GET /api/analytics?days=7&tz_offset_minutes=420`
- `GET /api/mqtt/status`, `GET|DELETE /api/mqtt/messages`
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
npm run lint
npm run build
```

Kiểm tra MQTT, nhiều khuôn mặt và ingress: xem [tests/README.md](tests/README.md).

## Giấy phép

Mã nguồn InsightFace dùng MIT License; pretrained model do InsightFace cung cấp bị giới hạn cho mục đích nghiên cứu phi thương mại. Xem [README_vi.md](README_vi.md) và [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
