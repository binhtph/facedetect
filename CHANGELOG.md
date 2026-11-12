# Changelog

## 2.0.1 - 2026-11-12

- **Test page:** new switch _Send to Home Assistant & Telegram_ (off by default, remembered per browser). Test uploads were always silent, which looked like MQTT not updating until settings were saved or the add-on restarted.
- Silent recognitions (Test page with the switch off) are flagged `notified = 0` and never appear in the MQTT state or latest image that IRIS republishes on reconnect or Home Assistant restart, so a test photo can no longer reach automations. Existing `Test upload` events are flagged on upgrade.

## 2.0.0 - 2026-11-12

- **Home Assistant sidebar (ingress):** the UI, API calls, uploads and router now work under `/api/hassio_ingress/<token>/` as well as on the direct port. SSR links get the ingress prefix from `X-Ingress-Path`; nginx rewrites asset URLs in HTML; chunk preloads follow the page's base path.
- **MQTT rewrite:** one persistent connection (`<device_id>_iris`) for publishing and camera commands instead of a new connection per message, which made brokers drop messages when several publishes shared the same client id. Adds Last Will (`availability` = `offline`), automatic reconnect, QoS 1 events that are delivered after a short outage, and automatic republish of discovery/state/latest image after every reconnect and when Home Assistant restarts (`homeassistant/status`). Saving MQTT settings is no longer needed to bring entities back. Errors are logged instead of silently ignored.
- **Multiple faces per image:** new setting _Faces per image_ (default 1 = old behaviour). Each face becomes its own event, unknown visitor, Telegram alert and `iris/event` message; the test page lists the other faces. Small or low-confidence background faces are skipped.
- Training a person from an event (or assigning an unknown visitor) now indexes that event's face even in group photos, and embedding rebuilds after a model change use the face crop first.
- **Analytics page:** events per day by result, busiest hours, cameras and most seen people (`GET /api/analytics`).
- **MQTT Monitor page:** connection status and a live log of sent/received MQTT messages (`GET/DELETE /api/mqtt/messages`, `GET /api/mqtt/status`).
- Camera page opened from the Home Assistant sidebar shows a usable trigger URL (direct port) instead of the session-bound ingress address.
- Docs: version 2.0.0 and `ghcr.io/binhtph/facedetect` images; links to the standalone and add-on repositories (and the original Release 1.0 by anhnvme); MQTT/model setup with an automation example; adding cameras with go2rtc still images (`/api/frame.jpeg?src=<camera>`); important recommendations and known issues (including the missing liveness/anti-spoofing check and the unused camera Min face / Min confidence fields).

## 1.0.3 - 2026-07-06

- Publish Home Assistant MQTT discovery automatically after creating a camera so its trigger button appears without manually republishing discovery.
- Republish camera trigger discovery after camera updates and clear the old retained trigger when the camera slug changes.
- Clear retained MQTT trigger discovery when a camera is deleted.

## 1.0.2 - 2026-07-06

- Use `buffalo_s` as the default InsightFace model for lower startup and CPU cost.
- Download the default `buffalo_s` model automatically on startup so fresh installs can run without a manual model download step.
- Save InsightFace runtime changes immediately when selecting model, provider, detection size, or age/gender settings.
- Automatically download a selected model before saving it if the model is not available locally.
- Update the Docker release workflow to publish matching Home Assistant add-on metadata to `anhnvme/hass-facedetect-addon`.

## 1.0.1 - 2026-07-06

- Pin NumPy below 2.4 to avoid `X86_V2` baseline crashes on Home Assistant OS add-ons running in Proxmox VMs with older or masked CPU flags.
- Keeps the published Docker image installable on x86_64 hosts where NumPy 2.4.x fails during `cv2` import.
