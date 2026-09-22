# ==============================================================================
# Script: init_avd_cluster.ps1
# Objective: Automated Provisioning of Multi-Instance Android Studio AVDs
# ==============================================================================

param(
    [string]$SdkRoot = "$env:LOCALAPPDATA\Android\Sdk",
    [string]$SystemImage = "system-images;android-33;google_apis;x86_64",
    [int]$InstanceCount = 3
)

$ErrorActionPreference = "Stop"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 1] ANDROID SDK DISCOVERY & LICENSES" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# Locate cmdline-tools (support 'latest' or versioned subdirectories)
$CmdlineTools = Join-Path $SdkRoot "cmdline-tools\latest\bin"
if (!(Test-Path $CmdlineTools)) {
    $parent = Join-Path $SdkRoot "cmdline-tools"
    if (Test-Path $parent) {
        $found = Get-ChildItem $parent -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
        if ($found) { $CmdlineTools = Join-Path $found.FullName "bin" }
    }
}

$SdkManager = Join-Path $CmdlineTools "sdkmanager.bat"
$AvdManager = Join-Path $CmdlineTools "avdmanager.bat"

if (!(Test-Path $SdkManager)) {
    throw "sdkmanager not found at '$SdkManager'. Please install Android Studio or SDK Command-Line Tools."
}

Write-Host "[OK] SDK Tools detected at $CmdlineTools" -ForegroundColor Green

# Accept all SDK licenses automatically
Write-Host "Accepting SDK licenses..." -ForegroundColor Yellow
& cmd.exe /c "echo y | `"$SdkManager`" --licenses" | Out-Null

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 2] SYSTEM IMAGE & CORE PACKAGES" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

& $SdkManager "platform-tools" "emulator" $SystemImage

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " [PHASE 3] PROVISIONING VIRTUAL DEVICES" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $InstanceCount; $i++) {
    $avdName = "Pixel7_Inst$i"
    Write-Host "Creating AVD: $avdName..." -ForegroundColor Yellow
    
    & cmd.exe /c "echo no | `"$AvdManager`" create avd -n $avdName -k `"$SystemImage`" --device `"pixel_7`" --force"
    
    # Tune hardware parameters for cluster stability and ANR prevention
    $avdIni = Join-Path $env:USERPROFILE ".android\avd\$avdName.avd\config.ini"
    if (Test-Path $avdIni) {
        $content = Get-Content $avdIni
        $updates = @{
            "hw.ramSize"        = "4G"
            "vm.heapSize"       = "512M"
            "hw.cpu.ncore"      = "4"
            "hw.lcd.width"      = "720"
            "hw.lcd.height"     = "1600"
            "hw.lcd.density"    = "320"
            "hw.gpu.mode"       = "auto"
            "showDeviceFrame"   = "no"
        }
        
        foreach ($key in $updates.Keys) {
            $val = $updates[$key]
            if ($content -match "^$key\s*=") {
                $content = $content -replace "^$key\s*=.*", "$key = $val"
            } else {
                $content += "$key = $val"
            }
        }
        $content | Set-Content $avdIni -Encoding UTF8
        Write-Host " -> Hardware configuration optimized for $avdName" -ForegroundColor Green
    }
}

Write-Host "`n[OK] All $InstanceCount virtual devices successfully provisioned." -ForegroundColor Green
