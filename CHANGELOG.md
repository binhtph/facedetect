# Changelog

## 1.0.1 - 2026-07-06

- Pin NumPy below 2.4 to avoid `X86_V2` baseline crashes on Home Assistant OS add-ons running in Proxmox VMs with older or masked CPU flags.
- Keeps the published Docker image installable on x86_64 hosts where NumPy 2.4.x fails during `cv2` import.
