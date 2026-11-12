[English](README.md) | [Tiếng Việt](README_vi.md)

# IRIS Face Recognition

IRIS nhận diện khuôn mặt cục bộ bằng InsightFace. Ảnh, embedding, cấu hình và log đều nằm trên máy chạy ứng dụng; không cần tài khoản cloud.

## Phiên bản và kho mã

Phiên bản hiện tại: **2.0.1** (image `ghcr.io/binhtph/facedetect:2.0.1`). Xem [CHANGELOG.md](CHANGELOG.md).

| Cách chạy             | Kho mã                                                                          |
| --------------------- | ------------------------------------------------------------------------------- |
| Docker độc lập        | [binhtph/facedetect](https://github.com/binhtph/facedetect) (repo này)          |
| Home Assistant add-on | [binhtph/ha-addons](https://github.com/binhtph/ha-addons), thư mục `facedetect` |

Dự án phát triển tiếp từ bản Release 1.0 của tác giả gốc:

- [anhnvme/facedetect](https://github.com/anhnvme/facedetect): chạy Docker độc lập.
- [anhnvme/hass-facedetect-addon](https://github.com/anhnvme/hass-facedetect-addon): add-on cho Home Assistant.

Theo tác giả gốc, đây là ứng dụng nhận diện khuôn mặt ở mức cơ bản và đã được triển khai cho nhiều nhà bạn bè hơn 1 năm.

## Chạy bằng Docker Compose

```bash
docker compose up -d --build
```

Mở `http://127.0.0.1:8080`. Model nhẹ `buffalo_s` sẽ tự tải trong lần khởi chạy đầu tiên.

Các tùy chọn runtime:

- Model pack: `antelopev2`, `buffalo_l`, `buffalo_m` hoặc `buffalo_s`;
- Provider: ONNX CPU, Intel OpenVINO CPU/iGPU/NPU/Auto hoặc NVIDIA CUDA;
- Detection size: 320, 640 hoặc 1280;
- Dự đoán tuổi/giới tính: mặc định tắt để giảm latency.

## Ghi chú model và tốc độ

Các model pack của InsightFace đánh đổi giữa độ chính xác, thời gian khởi động, RAM và tải CPU:

- `buffalo_s`: nhanh nhất và nhẹ nhất. Khuyến nghị cho máy chỉ có CPU, mini PC, Raspberry Pi-class host hoặc luồng MQTT cần latency thấp.
- `buffalo_m`: lựa chọn cân bằng cho CPU nếu `buffalo_s` chưa đủ chính xác.
- `buffalo_l`: nặng hơn và thường chính xác hơn, phù hợp hơn khi có GPU/iGPU hoặc CPU mạnh.
- `antelopev2`: pack thiên về độ chính xác, nhưng không phải lựa chọn đầu tiên cho máy CPU yếu.

Cấu hình khuyến nghị cho CPU:

- Model: bắt đầu với `buffalo_s`.
- Detection size: bắt đầu với `320`; chỉ tăng lên `640` nếu bị miss mặt.
- Tuổi/giới tính: tắt nếu không thật sự cần.
- MQTT: kết quả nhận diện được gửi trước; thumbnail gửi sau.

Gợi ý chọn Detection size:

- `320`: nhanh nhất. Dùng cho camera gần, rõ mặt, ít người.
- `640`: cân bằng. Dùng khi mặt nhỏ hơn hoặc detect bị miss.
- `1280`: chậm nhất. Chỉ dùng cho mặt ở xa, góc rộng hoặc khung hình đông người.

Để dùng Intel iGPU/OpenVINO trong Docker, mount DRM device vào container:

```yaml
services:
  iris:
    image: ghcr.io/binhtph/facedetect:latest
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

Sau đó chọn provider OpenVINO trong Settings, ví dụ OpenVINO CPU/iGPU/Auto. Máy host cần có Intel graphics driver hoạt động và có `/dev/dri`.

## Cấu hình MQTT và model

Cấu hình MQTT và model tùy theo máy và cách dùng:

- **Model:** chọn theo phần [Ghi chú model và tốc độ](#ghi-chú-model-và-tốc-độ) ở trên. Máy yếu bắt đầu với `buffalo_s`.
- **MQTT:** điền broker trong **Settings → MQTT**. IRIS giữ một kết nối thường trực, tự kết nối lại và tự gửi lại Home Assistant discovery sau khi IRIS, broker hoặc Home Assistant khởi động lại. Trang **MQTT Monitor** hiển thị trạng thái kết nối và các tin đã gửi/nhận.
- **Nhiều người trong một khung hình:** chỉnh **Settings → Faces per image** (mặc định 1 = chỉ mặt lớn nhất).
- **Trang Test:** ảnh upload mặc định **không** gửi MQTT/Telegram để không kích hoạt automation. Bật **Send to Home Assistant & Telegram** khi muốn thử cả chuỗi (sensor, `iris/event`, Telegram).

Mỗi lần nhận diện, IRIS gửi một tin lên `iris/event` (mỗi khuôn mặt một tin) và cập nhật các sensor như `Latest Person`, `Latest Recognition Event`. Khi IRIS mất kết nối, thiết bị trong Home Assistant chuyển sang _Unavailable_.

Ví dụ automation báo khi nhận ra người quen:

```yaml
automation:
  - alias: IRIS - báo người quen
    triggers:
      - trigger: mqtt
        topic: iris/event
    conditions:
      - condition: template
        value_template: "{{ trigger.payload_json.latest_type == 'known' }}"
    actions:
      - action: notify.notify
        data:
          message: "{{ trigger.payload_json.latest_person }} vừa tới {{ trigger.payload_json.latest_camera }}"
```

## Thêm camera bằng go2rtc

IRIS không xem video liên tục. Mỗi khi có **trigger**, IRIS tải **một ảnh tĩnh** từ camera rồi nhận diện ảnh đó. Cách đơn giản nhất để có ảnh tĩnh từ camera RTSP là dùng [go2rtc](https://github.com/AlexxIT/go2rtc):

1. Thêm camera vào go2rtc, ví dụ trong `go2rtc.yaml`:

   ```yaml
   streams:
     cong_truoc: rtsp://user:pass@192.168.1.50:554/stream1
   ```

2. Link ảnh tĩnh của camera có dạng:

   ```text
   http://<máy-go2rtc>:1984/api/frame.jpeg?src=<tên_camera>
   ```

   Ví dụ: `http://192.168.1.10:1984/api/frame.jpeg?src=cong_truoc`. Mở thử link trên trình duyệt, phải thấy ảnh JPEG.

3. Trong IRIS vào **Cameras → Add camera**, dán link vào **Still image URL**. Chỉnh **Cooldown** để tránh nhận diện lặp lại liên tục.

4. Kích hoạt nhận diện bằng một trong hai cách:
   - **Nút MQTT** `Trigger <tên camera>` mà IRIS tạo sẵn trong Home Assistant (tên entity lấy theo tên camera trong IRIS), ví dụ trong automation khi có chuyển động hoặc bấm chuông:

     ```yaml
     actions:
       - action: button.press
         target:
           entity_id: button.iris_face_recognition_trigger_cong_truoc
     ```

   - **HTTP:** `GET` hoặc `POST` tới `http://<máy-IRIS>:8080/api/cameras/trigger/<slug>` (link đầy đủ có trong trang camera).

## Khuyến nghị quan trọng

- Nên dùng ở khu vực **có thêm các lớp an ninh vật lý khác**; không dùng IRIS làm điều kiện duy nhất để mở cửa hay tắt báo động.
- **Test kỹ trước khi đưa vào thực tế**, với đúng camera, góc đặt và ánh sáng ngày/đêm.
- **Không train nhồi nhét quá nhiều ảnh cho một người**, nhất là ảnh mờ hoặc góc xấu: dễ làm tăng tỷ lệ nhận nhầm (false match).

## Những vấn đề đã biết

- **Tỷ lệ % hiển thị thường không cao**, nhưng theo kinh nghiệm của tác giả gốc rất ít khi nhận nhầm. Con số này là độ tương đồng (cosine similarity × 100), không phải xác suất đúng; ngưỡng mặc định là match 40 / auto-accept 55.
- **Chưa có kiểm tra người thật (liveness/anti-spoofing):** ảnh in hoặc ảnh trên màn hình điện thoại đưa trước camera có thể được nhận là người thật. Đây là lý do cần kết hợp an ninh vật lý.
- Các ô **Min face** và **Min confidence** của camera hiện chỉ được lưu, **chưa được áp dụng** khi nhận diện.
- Bản add-on: cổng `8080` không có đăng nhập; nên truy cập qua sidebar Home Assistant.

## Dữ liệu bền vững

Docker lưu toàn bộ dữ liệu bền vững dưới `/data`, chỉ cần mount một volume:

```text
/data/
├── database/iris.sqlite3
├── models/insightface/
└── uploads/
```

Chạy local mặc định dùng `backend/data/`. Có thể đổi data root bằng `IRIS_DATA_DIR`. Layout cũ được tự động migrate khi khởi động.

## Chạy image đã phát hành

```bash
docker run -d --name iris \
  -p 8080:80 \
  -v "${PWD}/backend/data:/data" \
  ghcr.io/binhtph/facedetect:2.0.1
```

Khi push Git tag `v2.0.1`, image được phát hành với các tag `2.0.1`, `2.0`, `2` và `latest`. Push lên `main` chỉ cập nhật `latest`, `main` và `sha-<commit>`.

## Phần mềm bên thứ ba và giấy phép model

IRIS sử dụng [InsightFace](https://github.com/deepinsight/insightface), được phát triển bởi các cộng tác viên InsightFace. Mã nguồn InsightFace được phát hành theo MIT License; xem [thông báo giấy phép chính thức của Python package](https://github.com/deepinsight/insightface/tree/master/python-package#license).

Quan trọng: các pretrained model do InsightFace cung cấp, bao gồm model tải thủ công, chỉ được InsightFace cung cấp cho **mục đích nghiên cứu phi thương mại**. Dự án này không sở hữu hoặc cấp lại giấy phép cho các model đó. Hãy đọc [thông tin giấy phép InsightFace](https://github.com/deepinsight/insightface/tree/master/python-package) và xin quyền phù hợp trước khi sử dụng thương mại.

Dự án còn sử dụng ONNX Runtime, OpenCV, FastAPI, React và các dependency mã nguồn mở khác. Xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) và các manifest dependency để biết thông tin credit và giấy phép.

Tài liệu kỹ thuật: [technical_vi.md](technical_vi.md).
