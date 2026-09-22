# Multi-Instance Android Virtual Device (AVD) Network Isolation Cluster

> [!CAUTION]
> ### ⚠️ FOR EDUCATIONAL AND SYSTEMS RESEARCH PURPOSES ONLY
> This project is provided strictly as a technical reference and experimental harness for systems research, hypervisor orchestration study, and guest-network isolation testing.
>
> **Strict Restrictions on Use:**
> Under no circumstances may this software, documentation, or architecture be used for:
> - Automated mass account registration or bot creation on third-party platforms.
> - Bypassing platform access controls, security verification systems, rate-limiting engines, or anti-abuse mechanisms.
> - Scraping, bulk data harvesting, impersonation, or actions in violation of any platform's Terms of Service.
> 
> The author explicitly rejects and condemns any form of unauthorized platform automation, policy circumvention, or malicious activity. Users assume all responsibility for compliance with relevant laws and service terms.

---

## 1. Architectural Overview

Running multiple concurrent mobile virtual machines on a single workstation without hardware virtualization conflicts or cross-instance networking leaks requires careful coordination across the hypervisor, compositor, and networking subsystems.

### Core Architecture Stack
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

### Key Technical Pillars
1. **Hypervisor Acceleration via WHPX:** Eliminates legacy VirtualBox/NEM engine deadlocks on modern Windows 11 systems with Core Isolation and Hyper-V enabled.
2. **Resource Throttling & ANR Mitigation:** Default emulator skins (1080x2400 @ 420 DPI) thrash Android's `lowmemorykiller` when run in parallel. Downscaling to 720x1600 @ 320 DPI with 4 GB RAM and 512 MB VM heap cuts compositor load by >55% while maintaining full application compatibility.
3. **Guest-Level TUN Isolation:** Rather than modifying the host's networking or running proxy software on Windows, each Android guest establishes an isolated userspace VPN tunnel (`tun0`), directing egress traffic through separate gateways.

---

## 2. Prerequisites & Toolchain Setup

### Host Requirements
- Windows 10/11 (x64) with **Windows Hypervisor Platform** and **Hyper-V** enabled.
- AMD Ryzen or Intel Core processor with nested hardware virtualization enabled in BIOS.
- 16+ GB RAM recommended (4 GB allocated per virtual device).

### Toolchain Components
1. **Google Android SDK Command-Line Tools (`cmdline-tools`):**
   - Provides `sdkmanager`, `avdmanager`, `emulator`, and `adb`.
2. **Android 13 System Image (`system-images;android-33;google_apis;x86_64`):**
   - High-compatibility 64-bit image optimized for hypervisor acceleration.
3. **WireGuard for Android:**
   - Deployed within guest VMs to manage TUN interface routing.

---

## 3. Step-by-Step Provisioning

### Step 1: Initialize Android Virtual Devices
Run the provisioning script to install SDK components and create the virtual devices:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init_avd_cluster.ps1
```

This generates 3 distinct AVD configurations (`Pixel7_Inst0`, `Pixel7_Inst1`, `Pixel7_Inst2`) with customized hardware definitions.

### Step 2: Configure Virtual Hardware (`config.ini`)
Ensure each AVD's `config.ini` in `$env:USERPROFILE\.android\avd\<Instance>.avd\` is configured for cluster stability:
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

### Step 3: Launch Cluster & Auto-Tile
Launch the cluster script to boot instances, wait for ADB availability, and arrange windows side-by-side:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_avd_cluster.ps1
```

### Step 4: Provision Guest-Level Tunnels
Each instance requires an independent tunnel profile. Deploy WireGuard and import unique `.conf` configurations via ADB broadcast intents or configuration injection into the application datastore.

---

## 4. Verification & Diagnostics

To verify IP isolation and assert zero host residential leaks:
1. Verify active `tun0` interface status:
   ```powershell
   adb -s emulator-5554 shell "ip addr show tun0"
   ```
2. Verify active VPN session in Android Connectivity Service:
   ```powershell
   adb -s emulator-5554 shell "dumpsys connectivity | grep sessionId="
   ```
3. Check browser public egress IP across all running instances:
   ```powershell
   adb -s emulator-5554 shell "am start -a android.intent.action.VIEW -d https://ifconfig.me"
   ```

---

## 5. Network Isolation Notes
- **Host Isolation:** All network tunneling occurs strictly inside the virtualized guest OS; host network adapters and routing tables remain untouched.
- **WebRTC Leak Prevention:** The Android OS routes application-layer WebRTC traffic through the active default VPN interface (`tun0`), preventing host IP exposure.

---

## License
Distributed under the MIT License. See [LICENSE](LICENSE) for details.
