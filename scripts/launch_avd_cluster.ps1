# ==============================================================================
# Script: launch_avd_cluster.ps1
# Objective: Launch Virtual Devices, Auto-Tile Windows & Activate Network Tunnels
# ==============================================================================

param(
    [string]$SdkRoot = "$env:LOCALAPPDATA\Android\Sdk",
    [int]$BasePort = 5554,
    [int]$Count = 3
)

$EmulatorExe = Join-Path $SdkRoot "emulator\emulator.exe"
$AdbExe = Join-Path $SdkRoot "platform-tools\adb.exe"

if (!(Test-Path $EmulatorExe)) {
    # Check PATH fallback
    $cmd = Get-Command emulator.exe -ErrorAction SilentlyContinue
    if ($cmd) { $EmulatorExe = $cmd.Source } else { throw "Emulator binary not found at $EmulatorExe" }
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 1] PREFLIGHT & LOCK CLEANUP" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

Get-ChildItem "$env:USERPROFILE\.android\avd\*.avd\*.lock" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
Write-Host "[OK] Stale lock files removed." -ForegroundColor Green

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 2] LAUNCHING AVD CLUSTER" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Count; $i++) {
    $port = $BasePort + ($i * 2)
    $avdName = "Pixel7_Inst$i"
    $serial = "emulator-$port"

    $running = & $AdbExe devices 2>$null | Select-String -Pattern "$serial\s+device"
    if ($running) {
        Write-Host "$avdName ($serial) is already running." -ForegroundColor Green
    } else {
        Write-Host "Launching $avdName on port $port..." -ForegroundColor Yellow
        Start-Process -FilePath $EmulatorExe -ArgumentList "-avd $avdName -port $port -gpu auto -no-snapshot-load"
        Start-Sleep -Seconds 3
    }
}

Write-Host "`nWaiting for devices to complete boot..." -ForegroundColor Yellow
for ($i = 0; $i -lt $Count; $i++) {
    $port = $BasePort + ($i * 2)
    $serial = "emulator-$port"
    Write-Host "Waiting for $serial ..." -NoNewline
    & $AdbExe -s $serial wait-for-device

    $booted = $false
    $timeout = 90
    while (-not $booted -and $timeout -gt 0) {
        $status = & $AdbExe -s $serial shell getprop sys.boot_completed 2>$null
        if ($status -match "1") { $booted = $true } else { Start-Sleep -Seconds 2; $timeout -= 2 }
    }
    Write-Host " [ONLINE]" -ForegroundColor Green
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 3] AUTO-TILING WINDOWS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
}
"@

Add-Type -AssemblyName System.Windows.Forms
$workArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea

$Procs = Get-Process -Name "qemu-system-x86_64", "emulator" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } | Sort-Object Id
$winWidth = [math]::Min(460, [int]($workArea.Width / [math]::Max($Count, 1)))
$winHeight = [math]::Min(940, $workArea.Height - 50)
$startX = [int](($workArea.Width - ($winWidth * $Procs.Count)) / 2)
if ($startX -lt 10) { $startX = 10 }

for ($i = 0; $i -lt $Procs.Count; $i++) {
    [Win32]::SetWindowPos($Procs[$i].MainWindowHandle, [IntPtr]::Zero, ($startX + ($i * $winWidth)), 40, $winWidth, $winHeight, 0x0040)
}
Write-Host "[OK] Detected $($Procs.Count) window(s) tiled across monitor." -ForegroundColor Green

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 4] ACTIVATING ISOLATED GUEST TUNNELS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Count; $i++) {
    $port = $BasePort + ($i * 2)
    $serial = "emulator-$port"
    $tunnelName = "wgcf$i"

    Write-Host "Activating tunnel '$tunnelName' on $serial..." -ForegroundColor Yellow
    & $AdbExe -s $serial shell "am broadcast -a com.wireguard.android.action.SET_TUNNEL_UP -n 'com.wireguard.android/.model.TunnelManager`$IntentReceiver' -e tunnel $tunnelName" 2>$null | Out-Null
    Start-Sleep -Seconds 1

    $state = & $AdbExe -s $serial shell "ip addr show tun0 2>/dev/null"
    if ($state -match "tun0") {
        Write-Host " -> $serial: tun0 is [ACTIVE]" -ForegroundColor Green
    } else {
        Write-Host " -> $serial: tun0 pending connection..." -ForegroundColor DarkYellow
    }
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 5] VERIFYING NETWORK ISOLATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Count; $i++) {
    $port = $BasePort + ($i * 2)
    $serial = "emulator-$port"
    & $AdbExe -s $serial shell "am start -a android.intent.action.VIEW -d https://ifconfig.me" 2>$null | Out-Null
}

Write-Host "[OK] Cluster orchestration complete. Browser verification opened on all devices." -ForegroundColor Green
