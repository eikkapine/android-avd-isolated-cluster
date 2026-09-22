# Android AVD Cluster

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/License-MIT-2f9e62?style=for-the-badge"></a>
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows_11_%7C_Android_13-1c2430?style=for-the-badge">
  <img alt="Hypervisor" src="https://img.shields.io/badge/Hypervisor-WHPX-0078d4?style=for-the-badge">
  <img alt="Cost" src="https://img.shields.io/badge/Cost-%240_Free-brightgreen?style=for-the-badge">
</p>

<p align="center"><strong>A Windows automation harness for running isolated Android Virtual Device (AVD) clusters with independent public egress IPs.</strong></p>

Android AVD Cluster combines Google's official QEMU/WHPX emulator engine, automated Win32 window tiling, and guest-level WireGuard TUN routing to run multiple virtual phones concurrently on a single Windows 11 machine without cross-instance IP leaks or memory thrashing.

> [!CAUTION]
> **Educational & Research Purposes Only**
>
> This repository is provided strictly for systems virtualization research and educational reference.
>
> It is **not** maintained and must **not** be used for:
> - Automating account creation on any platform
> - Bypassing security, verification, or CAPTCHA systems
> - Scraping, fraud, impersonation, or any activity that violates platform Terms of Service
>
> The author does not support or endorse any form of platform abuse or policy circumvention.

## What it does

| Area | Features |
| --- | --- |
| **Virtualization** | Official Google AVD engine accelerated via Windows Hypervisor Platform (WHPX); avoids VirtualBox/NEM 94% deadlocks under Windows 11 Hyper-V. |
| **Stability & ANR Fix** | Tuned 720×1600 (320 DPI) display buffers, 4 GB RAM, and 512 MB VM heap per instance; prevents `lowmemorykiller` thrashing and "System UI not responding" popups. |
| **Network Isolation** | In-guest userspace WireGuard (`tun0`) routing; forces all guest application traffic through independent egress gateways without modifying the Windows host network. |
| **Desktop Tiling** | Win32 API window manager automatically calculates monitor working area and tiles phone frames side-by-side across your screen. |
| **Diagnostics & CLI** | Real-time `tun0` interface verification, Android Connectivity Service session inspection, and automated browser IP checks. |

## Requirements

- **OS:** Windows 10 or 11 (64-bit) with **Windows Hypervisor Platform** and **Hyper-V** enabled.
- **Hardware:** AMD Ryzen or Intel Core CPU with virtualization enabled in BIOS; 16+ GB RAM recommended (4 GB allocated per virtual device).
- **SDK Tools:** Android Studio (or standalone Android SDK Command-Line Tools) providing `sdkmanager`, `avdmanager`, `emulator`, and `adb`.

## Quick start

### 1. Provision virtual devices
Run from PowerShell to verify SDK licenses, pull the Android 13 x86_64 system image, and configure 3 AVDs with cluster-optimized hardware profiles:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init_avd_cluster.ps1
```

### 2. Configure WireGuard profiles
Place your tunnel `.conf` files into each virtual device (reference template in [`configs/wireguard_sample.conf`](configs/wireguard_sample.conf)), then bring up the tunnels via ADB:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage_tunnels.ps1 -Serial "emulator-5554" -TunnelName "wgcf0" -Action "UP"
```

### 3. Launch cluster & auto-tile
Start all instances, tile windows side-by-side across your monitor, and open browser verification:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_avd_cluster.ps1
```
*(Or double-click `START_CLUSTER.bat` in the repository root).*

## Architecture

```
Host Workstation (Windows 11)
├── Hyper-V & Windows Hypervisor Platform (WHPX)
└── Win32 Window Manager (Dynamic Desktop Tiling)
    │
    ├── Pixel7_Inst0 (Port 5554)
    │   ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
    │   └── tun0 (WireGuard) ───► Isolated Egress IP 0
    │
    ├── Pixel7_Inst1 (Port 5556)
    │   ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
    │   └── tun0 (WireGuard) ───► Isolated Egress IP 1
    │
    └── Pixel7_Inst2 (Port 5558)
        ├── Android 13 (API 33) · 4GB RAM · 4 vCPUs · 720x1600 @ 320 DPI
        └── tun0 (WireGuard) ───► Isolated Egress IP 2
```

## Verification & diagnostics

| Check | Command |
| --- | --- |
| In-guest TUN status | `adb -s emulator-5554 shell "ip addr show tun0"` |
| Active VPN session | `adb -s emulator-5554 shell "dumpsys connectivity \| grep sessionId="` |
| Browser egress IP | `adb -s emulator-5554 shell "am start -a android.intent.action.VIEW -d https://ifconfig.me"` |

## Public package boundary

The repository does **not** contain:
- pre-compiled binaries, installers, or external executables (`emulator.exe`, `wgcf.exe`, `curl`)
- third-party or proprietary APKs (`wireguard.apk`)
- private WireGuard configuration files, keys, or account tokens
- host residential IP addresses, personal configs, or machine-specific paths

## License

Original project code and scripts are released under the [MIT License](LICENSE). Android and Google APIs are trademarks of Google LLC.
