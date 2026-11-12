# Developer checks

These scripts are not part of the image; run them on a dev machine.

## Backend (Python)

Needs the backend requirements plus `amqtt httpx`:

```bash
pip install -r backend/requirements.txt amqtt httpx
# MQTT bridge against a local amqtt broker (port 18830): reconnect, Last Will,
# HA restart republish, concurrent publishes, camera triggers, message log.
IRIS_DATA_DIR=$(mktemp -d) python -I tests/backend/test_mqtt_bridge.py .
# Multi-face recognition, training from extra faces, analytics. Needs buffalo_s.zip from
# https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip
python -I tests/backend/test_multiface.py . /path/to/buffalo_s.zip
# Test-page uploads with/without "Send to Home Assistant" vs. MQTT state and republish.
python -I tests/backend/test_notify.py . /path/to/buffalo_s.zip
```

## Home Assistant ingress (UI)

Emulates HA ingress (`:8123/api/hassio_ingress/<token>/…`) and the add-on nginx (`:8080`),
then drives Chrome through every page on both paths.

```bash
npm run build
python -m uvicorn backend.app.main:app --port 8000 &
PORT=3000 node docker/web-server.mjs &
node tests/ingress/ingress-sim.mjs ./dist &
npm i --no-save puppeteer-core
node tests/ingress/browser-check.mjs        # CHROME_PATH=/path/to/chrome if needed
```

## Home Assistant blueprints

See [blueprints/README.md](blueprints/README.md): the front-door blueprint in a real Home
Assistant against a fake IRIS, 90 checks.
