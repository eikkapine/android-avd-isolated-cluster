#!/usr/bin/env python3
"""AVD Fleet Provisioner — bulk-create the cluster's AVDs.

- ANDROID_AVD_HOME from fleet.json (redirect for disk headroom)
- avdmanager create with a pixel device baseline
- config.ini overrides: low RAM / 2 vCPU / swiftshader GPU / no frame
- lean data partition (enough for apps + media across N units)

Usage: python provision_avds.py [count]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET_CFG = ROOT / "cluster" / "config" / "fleet.json"

CFG = json.loads(FLEET_CFG.read_text(encoding="utf-8-sig"))
SDK = Path(CFG["sdk_root"])
AVD_HOME = Path(CFG["avd_home"])
SYSTEM_IMAGE = CFG["system_image"]
# JAVA_HOME is only needed if avdmanager can't find a JDK on its own;
# override via environment when required.

CONFIG_OVERRIDES = {
    "hw.ramSize": CFG["boot"]["ram_mb"],
    "vm.heapSize": CFG["boot"]["vm_heap_mb"],
    "hw.cpu.ncore": CFG["boot"]["vcores"],
    "hw.lcd.width": CFG["boot"]["lcd"]["width"],
    "hw.lcd.height": CFG["boot"]["lcd"]["height"],
    "hw.lcd.density": CFG["boot"]["lcd"]["density"],
    "hw.gpu.mode": CFG["boot"]["gpu_mode"],
    "hw.gpu.enabled": "yes",
    "showDeviceFrame": "no",
    "disk.dataPartition.size": "4G",
    "image.sysdir.1": SYSTEM_IMAGE.replace(";", "/") + "/",
}


def run(cmd, **kw):
    env = {**os.environ, "ANDROID_AVD_HOME": str(AVD_HOME)}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, **kw)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    avdmanager = SDK / "cmdline-tools" / "latest" / "bin" / "avdmanager.bat"

    AVD_HOME.mkdir(parents=True, exist_ok=True)

    created, skipped = 0, 0
    for i in range(count):
        name = f"PxCluster_{i:02d}"
        avd_dir = AVD_HOME / f"{name}.avd"
        if avd_dir.exists():
            skipped += 1
            print(f"[{i:02d}] {name} exists — ensuring config only")
        else:
            r = run(["cmd", "/c", str(avdmanager), "create", "avd",
                     "-n", name, "-k", SYSTEM_IMAGE, "--device", "pixel_7", "--force"])
            if r.returncode != 0:
                print(f"[{i:02d}] create FAILED: {(r.stdout + r.stderr)[:300]}")
                continue
            created += 1

        # config.ini tuning
        ini = avd_dir / "config.ini"
        if ini.exists():
            lines = ini.read_text(encoding="utf-8-sig").splitlines()
            new, seen = [], set()
            for l in lines:
                if "=" in l:
                    k = l.split("=", 1)[0].strip()
                    if k in CONFIG_OVERRIDES:
                        new.append(f"{k}={CONFIG_OVERRIDES[k]}")
                        seen.add(k)
                    else:
                        new.append(l)
                else:
                    new.append(l)
            for k, v in CONFIG_OVERRIDES.items():
                if k not in seen:
                    new.append(f"{k}={v}")
            ini.write_text("\n".join(new) + "\n", encoding="utf-8")
            print(f"[{i:02d}] {name} provisioned at {avd_dir}")
        else:
            print(f"[{i:02d}] {name}: config.ini missing!")

    print(f"done — created {created}, skipped {skipped} (already provisioned)")


if __name__ == "__main__":
    main()
