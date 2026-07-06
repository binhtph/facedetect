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
