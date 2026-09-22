# Changelog

## 2.0.0 - 2026-09-23

- Added targeted BLE discovery through `LUMA_DEVICE` for E06 firmware that omits `AA12` from
  advertisements but exposes the complete Luma GATT service after connection.
- Added a reproducible Windows build script that temporarily applies the compatibility patch and
  leaves the upstream submodule clean after compilation.
- Added `.env` loading to the bridge launcher so device identifiers and API credentials remain
  outside the repository.
- Reported the application version from the health endpoint and FastAPI metadata.
- Verified a complete hardware handshake and BLE photo capture from an E06/S3 device.
- Added repository setup, configuration, smoke-test, and validation documentation.

## 1.0.0 - 2026-09-22

- Added the initial FastAPI bridge, local interaction page, SQLite session store, media validation,
  model adapter, Reachy adapter, and Luma CLI adapter.
- Pinned the Luma Core and Reachy Mini upstream repositories as Git submodules.
