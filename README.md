<div align="center">

```
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║    📱  A N D R O I D   A V D   C L U S T E R  📱         ║
║                                                           ║
║    Windows 11 · WHPX Hypervisor · 3x Pixel 7              ║
║    In-Guest WireGuard TUN · Zero-Leak Public IP           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
```

[![License: MIT](https://img.shields.io/badge/License-MIT-2f9e62?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%20Android%2013-blue?style=flat-square)
![Hypervisor](https://img.shields.io/badge/Hypervisor-WHPX-success?style=flat-square)
![Status](https://img.shields.io/badge/Status-Battle--Tested-ff4d6d?style=flat-square)

<p align="center"><strong>A battle-tested Windows harness for running multiple isolated Android Studio Virtual Devices simultaneously with independent public egress IPs.</strong></p>

*Built from real failures — not documentation.*

</div>

---

## What this is

An automated harness for running 3 isolated Android 13 virtual devices concurrently on Windows 11 with independent public IP addresses at $0 cost.

Consumer emulators (LDPlayer 9, Nox, Bluestacks) rely on an ancient VirtualBox 6.1 engine that hangs at 94% on modern Windows 11 systems running Hyper-V / Core Isolation. Default Android Studio AVDs crash with continuous "System UI is not responding" ANRs due to aggressive memory thrashing at 1080p. 

This repository provides the exact hypervisor, display geometry, and in-guest networking configurations required to run a smooth, stable multi-device cluster on a single workstation.

> [!CAUTION]
> ### ⚠️ EDUCATIONAL & RESEARCH PURPOSES ONLY
> This repository is provided strictly for educational reference and systems virtualization testing.
> 
> It is **NOT** maintained and must **NOT** be used for:
> - Automating account creation or botting on any platform
> - Bypassing security, verification, or CAPTCHA systems
> - Scraping, fraud, impersonation, or any activity that violates platform Terms of Service
> 
> The author does not support or endorse any form of platform abuse or policy circumvention.

## What you'll have at the end

- 3 concurrent Android 13 (Pixel 7) instances running side-by-side on your desktop
- Each device with its own distinct public IPv4/IPv6 address ($0 cost via in-guest WireGuard TUN)
- Zero ANR freezes or "System UI not responding" popups (tuned 720p @ 320 DPI display pipeline)
- Automated preflight, lock cleanup, dynamic window auto-tiling, and tunnel orchestration scripts

## Quick overview of the stack

```
Host Workstation (Windows 11)
├── Hyper-V & Windows Hypervisor Platform (WHPX)
└── Win32 Desktop Compositor (Dynamic Screen Tiling)
    │
    ├── Pixel7_Inst0 (Port 5554)
    │   ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
    │   └── tun0 (WireGuard) ───► Distinct Egress Public IP 0
    │
    ├── Pixel7_Inst1 (Port 5556)
    │   ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
    │   └── tun0 (WireGuard) ───► Distinct Egress Public IP 1
    │
    └── Pixel7_Inst2 (Port 5558)
        ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
        └── tun0 (WireGuard) ───► Distinct Egress Public IP 2
```

## Key lessons & gotchas (the short version)

- **Consumer emulators fail on modern Windows 11** — LDPlayer 9 and similar tools use VirtualBox 6.1, which deadlocks at 94% under Hyper-V NEM fallback on modern AMD/Intel chips. Google's official QEMU with native WHPX acceleration is mandatory.
- **1080p crashes Android 13 under multi-instance load** — The default 1080×2400 (420 DPI) skin thrashes Android's `lowmemorykiller` when run in parallel, resulting in continuous ANRs and frame drops. Downscaling to 720×1600 @ 320 DPI with 4 GB RAM and 512 MB VM heap cuts compositor load by >55% with zero crash overhead.
- **Dual-stack IPv6 DNS hangs on Windows** — On IPv4-only broadband connections, PowerShell `Invoke-WebRequest` hangs indefinitely on domains with `AAAA` DNS records. Always use `curl.exe -4 -L` for CLI downloads.
- **Tunnel inside the VM, not the host** — Running proxies or VPN clients on the Windows host risks WebRTC leaks, process collisions, and false-positive antivirus triggers. In-guest WireGuard (`tun0`) forces all app-level traffic through the virtual interface without touching host network adapters.
- **Stale QEMU locks must be purged** — If an emulator process terminates abruptly, left-behind `*.lock` files in the `.android/avd/*.avd/` directory will prevent instances from booting. The launcher automatically cleans these up.

## Get started

### 1. Prerequisites
- Windows 10/11 (x64) with **Windows Hypervisor Platform** and **Hyper-V** enabled.
- AMD Ryzen or Intel Core CPU with virtualization enabled in BIOS.
- Android Studio or standalone Android SDK Command-Line Tools (`cmdline-tools`).

### 2. Provision the Virtual Devices
Run the provisioning script to accept SDK licenses, install the Android 13 x86_64 system image, and create 3 pre-configured AVDs:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init_avd_cluster.ps1
```

### 3. Configure Guest WireGuard Profiles
Each virtual device routes through its own tunnel. Copy a WireGuard configuration (refer to [`configs/wireguard_sample.conf`](configs/wireguard_sample.conf)) into each device and activate via ADB:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage_tunnels.ps1 -Serial "emulator-5554" -TunnelName "wgcf0" -Action "UP"
```

### 4. Launch Cluster & Auto-Tile
Launch all instances, auto-tile them side-by-side across your monitor, and open browser verification:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_avd_cluster.ps1
```
*(Or double-click `START_CLUSTER.bat`)*

## Verification & Diagnostics

Verify that each virtual device is routing through its tunnel and has an isolated egress IP:

| Check | Command |
|---|---|
| In-guest TUN status | `adb -s emulator-5554 shell "ip addr show tun0"` |
| Active VPN session | `adb -s emulator-5554 shell "dumpsys connectivity \| grep sessionId="` |
| Browser egress IP | `adb -s emulator-5554 shell "am start -a android.intent.action.VIEW -d https://ifconfig.me"` |

## Public package boundary

The repository does **not** contain:
- pre-compiled binaries or external tools (`emulator.exe`, `wgcf.exe`, `curl`)
- third-party or proprietary APKs (`wireguard.apk`)
- private WireGuard configuration files, keys, or account tokens
- host residential IP addresses, personal configs, or machine-specific paths

## License

Distributed under the [MIT License](LICENSE).
