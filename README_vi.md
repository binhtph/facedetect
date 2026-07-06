[English](README.md) | [Tiếng Việt](README_vi.md)

# IRIS Face Recognition

IRIS nhận diện khuôn mặt cục bộ bằng InsightFace. Ảnh, embedding, cấu hình và log đều nằm trên máy chạy ứng dụng; không cần tài khoản cloud.

## Chạy bằng Docker Compose

```bash
docker compose up -d --build
```

Mở `http://127.0.0.1:8080`. Tải model cần dùng tại Settings → InsightFace.

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

Sau đó chọn provider OpenVINO trong Settings, ví dụ OpenVINO CPU/iGPU/Auto. Máy host cần có Intel graphics driver hoạt động và có `/dev/dri`.

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
  ghcr.io/anhnvme/facedetect:latest
```

Khi push Git tag `v1.2.3`, image cũng được phát hành với các tag `1.2.3`, `1.2` và `1`.

## Phần mềm bên thứ ba và giấy phép model

IRIS sử dụng [InsightFace](https://github.com/deepinsight/insightface), được phát triển bởi các cộng tác viên InsightFace. Mã nguồn InsightFace được phát hành theo MIT License; xem [thông báo giấy phép chính thức của Python package](https://github.com/deepinsight/insightface/tree/master/python-package#license).

Quan trọng: các pretrained model do InsightFace cung cấp, bao gồm model tải thủ công, chỉ được InsightFace cung cấp cho **mục đích nghiên cứu phi thương mại**. Dự án này không sở hữu hoặc cấp lại giấy phép cho các model đó. Hãy đọc [thông tin giấy phép InsightFace](https://github.com/deepinsight/insightface/tree/master/python-package) và xin quyền phù hợp trước khi sử dụng thương mại.

Dự án còn sử dụng ONNX Runtime, OpenCV, FastAPI, React và các dependency mã nguồn mở khác. Xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) và các manifest dependency để biết thông tin credit và giấy phép.

Tài liệu kỹ thuật: [technical_vi.md](technical_vi.md).
