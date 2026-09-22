# Multi-Instance Android Virtual Device (AVD) Network Isolation Cluster

> [!CAUTION]
> ### ⚠️ Educational & Research Disclaimer
> This project is a technical reference and experimental harness for systems research, hypervisor orchestration, and guest-level network isolation testing.
>
> **Important:**
> This repository is not designed or intended for:
> - Automated account registration or botting on third-party services.
> - Circumventing platform access controls, security verification systems, or rate limits.
> - Scraping, bulk data harvesting, or any activity that violates third-party Terms of Service.
>
> The author does not endorse or support unauthorized platform automation or terms-of-service violations. Users are responsible for ensuring their usage complies with all relevant legal requirements and service terms.

---

## 1. Architectural Overview

Running multiple concurrent mobile virtual machines on a single workstation without hardware virtualization conflicts or cross-instance networking leaks requires coordination across the hypervisor, compositor, and networking layers.

```
+-------------------------------------------------------------+
|                      Host Workstation                       |
|          Windows 11 + Windows Hypervisor Platform           |
+-------------------------------------------------------------+
       |                               |
       +--- WHPX Hypervisor Sync       +--- Window Compositor (Win32)
       |                               |
+---------------+              +---------------+              +---------------+
|   AVD Inst0   |              |   AVD Inst1   |              |   AVD Inst2   |
| (QEMU x86_64) |              | (QEMU x86_64) |              | (QEMU x86_64) |
+---------------+              +---------------+              +---------------+
|  Android 13   |              |  Android 13   |              |  Android 13   |
|  4GB RAM / 4C |              |  4GB RAM / 4C |              |  4GB RAM / 4C |
| 720x1600 320d |              | 720x1600 320d |              | 720x1600 320d |
+---------------+              +---------------+              +---------------+
|   tun0 (WG)   |              |   tun0 (WG)   |              |   tun0 (WG)   |
| Crypto Egress |              | Crypto Egress |              | Crypto Egress |
+---------------+              +---------------+              +---------------+
       |                               |                              |
  Unique Public IP 0             Unique Public IP 1             Unique Public IP 2
```

### Engineering Details
- **Hypervisor Acceleration (WHPX):** Modern Windows 11 systems with Core Isolation and Hyper-V enabled can deadlock or freeze legacy emulator engines (such as older VirtualBox builds running under NEM fallback). Running official Google AVDs on QEMU with Windows Hypervisor Platform (WHPX) acceleration provides native, stable virtualization.
- **Memory & ANR Mitigation:** Default AVD profiles (1080×2400 @ 420 DPI) cause heavy memory thrashing under Android 13 when running multiple instances at once, triggering "System UI is not responding" freezes. Downscaling each virtual display to 720×1600 @ 320 DPI and allocating 4 GB RAM / 512 MB VM heap cuts compositor load by over 50% while keeping apps fully compatible.
- **Guest-Level Network Isolation:** Rather than running proxy clients on the Windows host (which can trigger endpoint security or leak host DNS), each Android VM runs its own userspace WireGuard tunnel (`tun0`). Traffic from all apps within the VM is forced through the guest's VPN interface, giving each emulator an independent public egress IP.

---

## 2. Prerequisites

- **OS:** Windows 10/11 (x64) with **Windows Hypervisor Platform** and **Hyper-V** enabled in Windows Features.
- **Hardware:** AMD Ryzen or Intel Core CPU with hardware virtualization (SVM/VT-x) enabled in BIOS; 16+ GB RAM recommended.
- **Tooling:** Android Studio (or standalone Android SDK Command-Line Tools) with platform-tools and emulator packages installed.

---

## 3. Provisioning & Setup

### Step 1: Provision Virtual Devices
The initialization script accepts SDK licenses, pulls the Android 13 system image, and generates 3 AVDs with optimized hardware profiles:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init_avd_cluster.ps1
```

### Step 2: Virtual Hardware Configuration
Each AVD's `config.ini` (located at `$env:USERPROFILE\.android\avd\<InstanceName>.avd\config.ini`) is pre-tuned with the following settings:
```ini
hw.ramSize = 4G
vm.heapSize = 512M
hw.cpu.ncore = 4
hw.lcd.width = 720
hw.lcd.height = 1600
hw.lcd.density = 320
hw.gpu.mode = auto
showDeviceFrame = no
```

### Step 3: Configure Guest WireGuard Tunnels
Copy a valid WireGuard configuration (see [`configs/wireguard_sample.conf`](configs/wireguard_sample.conf)) into each virtual device. Tunnels can be controlled programmatically using ADB broadcast intents:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manage_tunnels.ps1 -Serial "emulator-5554" -TunnelName "wgcf0" -Action "UP"
```

### Step 4: Launch Cluster & Auto-Tile Windows
Boot all instances concurrently, wait for ADB readiness, and auto-tile phone windows across your monitor:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_avd_cluster.ps1
```

---

## 4. Verification & Diagnostics

Verify that each emulator routes traffic through its own tunnel and does not leak the host IP:

1. **Check the `tun0` interface inside the guest:**
   ```powershell
   adb -s emulator-5554 shell "ip addr show tun0"
   ```
2. **Check active VPN session in Android Connectivity Service:**
   ```powershell
   adb -s emulator-5554 shell "dumpsys connectivity | grep -E 'sessionId='"
   ```
3. **Check egress IP in the guest browser:**
   ```powershell
   adb -s emulator-5554 shell "am start -a android.intent.action.VIEW -d https://ifconfig.me"
   ```

---

## 5. Network Isolation Notes
- **Host Isolation:** Network tunneling occurs strictly inside the virtualized guest OS; host network adapters and routing tables remain untouched.
- **WebRTC Leak Prevention:** The Android OS routes application-layer WebRTC traffic through the active default VPN interface (`tun0`), preventing host IP exposure.

---

## License
Distributed under the MIT License. See [LICENSE](LICENSE) for details.
