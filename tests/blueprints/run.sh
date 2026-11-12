#!/bin/bash
# Run the IRIS front-door blueprint in a real Home Assistant against a fake IRIS.
# Needs: Home Assistant (pip install homeassistant), amqtt, paho-mqtt, pillow, and a
# writable /media (snapshots go to /media/snapshots). Use a throwaway container/VM.
# Usage: tests/blueprints/run.sh [all|unlock|greet|offline]
set -u
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
HASS=${HASS:-hass}
WORK=$(mktemp -d)
cp -r config "$WORK/config"
mkdir -p "$WORK/config/blueprints/automation/binhtph" /media/snapshots
cp ../../blueprints/automation/*.yaml "$WORK/config/blueprints/automation/binhtph/"
rm -f /media/snapshots/iris_cua.jpg
"$PY" broker.py > "$WORK/broker.log" 2>&1 &
BROKER=$!
sleep 2
"$PY" sim.py setup
"$HASS" -c "$WORK/config" --skip-pip > "$WORK/hass.log" 2>&1 &
HA=$!
trap 'kill $HA $BROKER 2>/dev/null' EXIT
sleep 20
grep -iE "error|invalid" "$WORK/hass.log" | grep -vE "turbojpeg|RuntimeError" || true
"$PY" sim.py run "${1:-all}"
