# ==============================================================================
# Script: manage_tunnels.ps1
# Objective: Programmatic Control of WireGuard Tunnels via ADB Broadcast Intents
# ==============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$Serial,

    [Parameter(Mandatory=$true)]
    [string]$TunnelName,

    [ValidateSet("UP", "DOWN", "STATUS")]
    [string]$Action = "STATUS",

    [string]$SdkRoot = "$env:LOCALAPPDATA\Android\Sdk"
)

$AdbCmd = Get-Command adb -ErrorAction SilentlyContinue
$AdbExe = if ($AdbCmd) { $AdbCmd.Source } else { Join-Path $SdkRoot "platform-tools\adb.exe" }

if (!(Test-Path $AdbExe)) {
    throw "adb binary not found at $AdbExe"
}

switch ($Action) {
    "UP" {
        Write-Host "Bringing tunnel '$TunnelName' UP on $Serial..." -ForegroundColor Yellow
        & $AdbExe -s $Serial shell "am broadcast -a com.wireguard.android.action.SET_TUNNEL_UP -n 'com.wireguard.android/.model.TunnelManager`$IntentReceiver' -e tunnel $TunnelName"
        Start-Sleep -Seconds 1
        & $AdbExe -s $Serial shell "ip addr show tun0 2>/dev/null"
    }
    "DOWN" {
        Write-Host "Bringing tunnel '$TunnelName' DOWN on $Serial..." -ForegroundColor Yellow
        & $AdbExe -s $Serial shell "am broadcast -a com.wireguard.android.action.SET_TUNNEL_DOWN -n 'com.wireguard.android/.model.TunnelManager`$IntentReceiver' -e tunnel $TunnelName"
        Start-Sleep -Seconds 1
        & $AdbExe -s $Serial shell "ip addr show tun0 2>/dev/null"
    }
    "STATUS" {
        Write-Host "Checking tunnel status on $Serial..." -ForegroundColor Yellow
        $ipInfo = & $AdbExe -s $Serial shell "ip addr show tun0 2>/dev/null"
        $vpnInfo = & $AdbExe -s $Serial shell "dumpsys connectivity | grep -E 'sessionId=$TunnelName'" 2>/dev/null
        if ($ipInfo -match "tun0") {
            Write-Host "[ONLINE] tun0 interface active:`n$ipInfo" -ForegroundColor Green
        } else {
            Write-Host "[OFFLINE] tun0 interface not present" -ForegroundColor Red
        }
    }
}
