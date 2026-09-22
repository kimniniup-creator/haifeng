# Robot Glasses Bridge V2

Robot Glasses Bridge connects Luma-compatible smart glasses, a Reachy Mini robot, and an
OpenAI-compatible vision model through one local FastAPI service.

Version 2 adds verified Windows support for E06/S3 glasses whose firmware exposes the Luma
`AA12` GATT service after connection but does not include that service in BLE advertisements.
The bridge can select a specific device by Bluetooth name or address, capture the small AI JPEG
over BLE, and pass it into the existing vision and robot workflow.

## Verified hardware

- Glasses name: `E06-0055`
- Project: `S3`
- Hardware revision: `2`
- Bluetooth firmware: `1.4.9`
- ISP firmware: `1.3.5`
- BLE photo: verified, `368 x 480` JPEG

The individual device address is intentionally not stored in this public repository. Configure
your own name or address in `.env`.

## Requirements

- Windows 11 with Bluetooth LE
- Python 3.12
- Rust stable with the MSVC toolchain
- Git with submodule support
- A powered and awake E06/E09-compatible pair of glasses

## Setup

Clone the repository with its submodules:

```powershell
git clone --recurse-submodules https://github.com/timesbye/Robot_glasses.git
Set-Location Robot_glasses
Copy-Item .env.example .env
```

Set at least the bridge token and the glasses selector in `.env`:

```dotenv
BRIDGE_TOKEN=replace-with-a-random-local-token
LUMA_DEVICE=E06-0055
```

`LUMA_DEVICE` accepts the advertised Bluetooth name or a stable device address. An address is
more reliable when the device advertises only briefly. Keep `.env` local; it is ignored by Git.

Build the patched Luma client and start the bridge:

```powershell
.\build_luma.ps1
.\run_bridge.ps1
```

The first `run_bridge.ps1` invocation also builds the client automatically when it is absent.
Open `http://127.0.0.1:8088/` after the service starts.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `BRIDGE_HOST` | HTTP listen address | `127.0.0.1` |
| `BRIDGE_PORT` | HTTP listen port | `8088` |
| `BRIDGE_TOKEN` | Bearer token used by the API and UI | local development token |
| `LUMA_DEVICE` | Glasses Bluetooth name or address | automatic `AA12` scan |
| `LUMA_CLI_PATH` | Path to the compiled Luma CLI | repository release build |
| `REACHY_HOST` | Reachy daemon host | `127.0.0.1` |
| `REACHY_PORT` | Reachy daemon port | `8000` |
| `MODEL_BASE_URL` | OpenAI-compatible API base URL | unset |
| `MODEL_API_KEY` | Model API key | unset |
| `VISION_MODEL` | Vision-capable model name | unset |

Environment variables already present in the shell take precedence over `.env` values.

## Hardware smoke test

Wake the glasses and ensure a phone application is not holding the BLE connection, then run:

```powershell
$env:LUMA_DEVICE = 'E06-0055'
.\upstream\luma-core\target\release\examples\luma.exe info
.\upstream\luma-core\target\release\examples\luma.exe photo --ai .\data\smoke-test.jpg
```

`info` should report firmware, battery, volume, settings, and `handshake complete: true`.

## Validation

The V2 hardware run completed a full handshake and received a valid JPEG from the glasses.
The Luma library test suite also passes with the compatibility patch:

```powershell
cargo test --locked --release --lib --features ble --manifest-path .\upstream\luma-core\Cargo.toml -j 1
```

Result: `198 passed; 0 failed`.

See [CHANGELOG.md](CHANGELOG.md) for release notes and
[Luma_Reachy_部署交互指南.md](Luma_Reachy_部署交互指南.md) for the broader deployment design.
