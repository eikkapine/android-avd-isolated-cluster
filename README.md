# Android AVD Cluster

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/License-MIT-2f9e62?style=for-the-badge"></a>
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows_11_%7C_Android_13-1c2430?style=for-the-badge">
  <img alt="Hypervisor" src="https://img.shields.io/badge/Hypervisor-WHPX-0078d4?style=for-the-badge">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-native-8a5cf6?style=for-the-badge">
  <img alt="Cost" src="https://img.shields.io/badge/Cost-%240_Free-brightgreen?style=for-the-badge">
</p>

<p align="center"><strong>A Windows automation harness for running isolated Android Virtual Device (AVD) clusters, driven over native MCP by any agent.</strong></p>

Android AVD Cluster combines Google's official QEMU/WHPX emulator engine, an orchestrated fleet manager, and a native MCP server so an AI agent can boot, drive, and manage up to 20 virtual phones concurrently on a single Windows 11 machine — each phone individually addressable for UI automation and app testing.

## What it does

| Area | Features |
| --- | --- |
| **Virtualization** | Official Google AVD engine accelerated via Windows Hypervisor Platform (WHPX); low-RAM per-instance tuning (1.5 GB / 2 vCPU) so more phones fit per host. |
| **Fleet Manager** | Staggered boot with a memory-safe live budget, single-slot boot by index, kill with full port + adb verification (never reports success on a lie), hot-swap rotate, capacity reporting. |
| **MCP Server** | Native stdio server: `fleet.*` lifecycle tools and `phone.*` per-device control (tap, type, swipe, screenshot, uidump, shell, install, apps, wake, scrcpy) — drive each phone individually from the same agent session. |
| **Verified Typing** | `phone.type` waits for the focused editor, verifies the text actually landed, and self-heals on input-dispatcher races (leading-character loss) — reports `(verified)` only when the field truly contains the text. |
| **Browser Setup** | Post-boot preparation: walks Chrome's first-run screens by UI-dump taps, dismisses crash and ANR dialogs by stable resource-ids (locale-proof), suppresses system error dialogs so app crash bursts never block automation. |
| **Diagnostics & CLI** | `fleet.py status/boot/kill/rotate`, host memory snapshot, per-phone shell access, live scrcpy windows for human-in-the-loop moments. |

## Requirements

- **OS:** Windows 10 or 11 (64-bit) with **Windows Hypervisor Platform** and **Hyper-V** enabled.
- **Hardware:** AMD Ryzen or Intel Core CPU with virtualization enabled in BIOS; 32 GB RAM recommended for 12+ concurrent phones (~1.9 GB each).
- **SDK Tools:** Android SDK Command-Line Tools providing `sdkmanager`, `avdmanager`, `emulator`, and `adb` (platform-tools).
- **Runtime:** Python 3.12+ (fleet manager), Node.js 18+ or Bun (MCP server).

## Quick start

```
# 1. Clone
git clone https://github.com/eikkapine/android-avd-isolated-cluster.git
cd android-avd-isolated-cluster

# 2. Point cluster/config/fleet.json at your SDK and AVD home
#    (avd_home, sdk_root, base_port, max_instances)

# 3. Provision the AVDs (skips ones that already exist)
python cluster/scripts/provision_avds.py 20

# 4. Boot the fleet (staggered, memory-safe budget from fleet.json)
python cluster/scripts/fleet.py boot

# 5. Check the fleet
python cluster/scripts/fleet.py status
```

### Wire the MCP server into your agent

Claude Code (user scope):

```
claude mcp add android-fleet -s user -- bun /path/to/android-avd-isolated-cluster/mcp-server/src/index.js
```

Claude Desktop / any stdio MCP client (config):

```
{
  "mcpServers": {
    "android-fleet": {
      "command": "bun",
      "args": ["/path/to/android-avd-isolated-cluster/mcp-server/src/index.js"]
    }
  }
}
```

Environment overrides (optional): `ANDROID_FLEET_ROOT` (repo checkout), `ANDROID_SDK_ROOT`, `ANDROID_FLEET_PYTHON`, `ANDROID_FLEET_SCRCPY`.

### Drive a phone

Once connected, the agent gets `fleet.*` and `phone.*` tools. Examples:

- `fleet.status` — every slot's live/booting/off state
- `fleet.boot {index: 11}` — boot exactly slot 11
- `phone.tap {index: 0, x: 340, y: 192}` — tap slot 0's screen
- `phone.type {index: 0, text: "hello farm"}` — type with verified delivery
- `phone.uidump {index: 0}` — element bounds/text/IDs for targeting taps
- `phone.screenshot {index: 0}` — capture + inline image
- `phone.shell {index: 0, command: "..."}` — any adb shell command

## Architecture

```
Host Workstation (Windows 11)
├── Hyper-V & Windows Hypervisor Platform (WHPX)
│
├── PxCluster_00 (Port 5554)
│   └── Android 13 (API 33) · 1.5GB RAM · 2 vCPU · 720x1600 @ 320 DPI
├── PxCluster_01 (Port 5556)
│   └── Android 13 (API 33) · 1.5GB RAM · 2 vCPU · 720x1600 @ 320 DPI
├── ...
└── PxCluster_19 (Port 5592)
    └── Android 13 (API 33) · 1.5GB RAM · 2 vCPU · 720x1600 @ 320 DPI

        ▲
        │ native MCP (stdio)
        │
   Agent (Claude Code / Claude Desktop / any MCP client)
   fleet.* lifecycle + phone.* per-device control
```

## Verification & diagnostics

| Check | Command |
| --- | --- |
| Fleet state | `python cluster/scripts/fleet.py status` |
| Boot one slot | `python cluster/scripts/fleet.py boot --index 3` |
| Kill with verification | `python cluster/scripts/fleet.py kill --index 3` |
| In-guest shell | `adb -s emulator-5554 shell "getprop sys.boot_completed"` |
| Live visual window | `phone.scrcpy {index: 0}` (human-in-the-loop moments) |

## Post-boot device setup (optional)

`cluster/scripts/browser_setup.py` prepares a freshly booted phone for
hands-off browser automation:

```
python cluster/scripts/browser_setup.py --serial emulator-5554 --locale en-US
```

It suppresses system error dialogs (kiosk mode), walks Chrome's first-run
screens by UI-dump taps under a temporary English locale (restoring the
slot's locale afterwards), dismisses crash/ANR dialogs by stable
resource-ids, and only reports success after verifying the browser opens
clean. The fleet orchestrator runs it automatically after every boot when
present.

## Scope

This repository is a **local device-farm lab**: it boots emulators that
identify as the emulators they are, and drives them over adb and MCP for
UI automation, app testing, and development workflows.

The repository does **not** contain or provide:
- device identity spoofing, fingerprint pools, or emulator-hiding layers
- account creation, multi-account management, or platform posting connectors
- pre-compiled binaries, third-party APKs, or installers
- private keys, tokens, tunnel configurations, or machine-specific paths

Operators are responsible for how they use their own lab and for complying
with the terms of any platform they interact with.

## License

Original project code and scripts are released under the [MIT License](LICENSE). Android and Google APIs are trademarks of Google LLC.
