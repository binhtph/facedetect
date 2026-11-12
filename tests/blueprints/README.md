# Blueprint tests

`run.sh` starts an MQTT broker, a real Home Assistant with the blueprint from
`blueprints/automation/`, a stub TTS + speaker (`custom_components/teststub`, reports what
it is asked to say over MQTT) and a fake IRIS (`sim.py`: answers the camera trigger button
with scripted results, like IRIS does). It then checks every case: family member (unlock,
light, personal greeting), acquaintance (not allowed, "Mở cửa" button, remote unlock and
expiry), retry after "review" / no face, jammed lock, stranger, IRIS not answering, two
faces, results from another camera, idle test uploads, the two capture LEDs (on before the
shot, off after, a light already on left alone), IRIS offline/online, and the door-open
greeting (no second greeting after a face unlock, quick re-open, acquaintance let in from the
phone, guests, someone leaving, a fresh shot beating an older stranger result, motion while the door is already open with
no second greeting for the same person).

```bash
pip install homeassistant amqtt paho-mqtt pillow   # Python 3.14 for HA 2026.11
tests/blueprints/run.sh          # all scenarios, about 6 minutes
tests/blueprints/run.sh unlock   # or: greet, offline
```

It writes snapshots to `/media/snapshots`, so run it in a container or VM.
