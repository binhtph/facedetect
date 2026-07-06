FROM node:24-bookworm-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:24-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IRIS_DATA_DIR=/data \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-dejavu-core libgl1 libglib2.0-0 libxcb1 nginx python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf \
    && python3 -m venv /opt/venv

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && if [ "$(uname -m)" = "x86_64" ]; then pip install --no-cache-dir --force-reinstall --no-deps onnxruntime-openvino; fi

COPY package.json package-lock.json ./
COPY --from=frontend-build /app/node_modules /app/node_modules
COPY --from=frontend-build /app/dist /app/dist
COPY backend/app /app/backend/app
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/start.sh /app/docker/start.sh
COPY docker/web-server.mjs /app/docker/web-server.mjs

RUN mkdir -p /data /run/nginx \
    && chmod +x /app/docker/start.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1/healthz || exit 1

CMD ["/app/docker/start.sh"]
