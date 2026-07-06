# Changelog

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
