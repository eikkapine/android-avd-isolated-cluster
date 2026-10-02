#!/usr/bin/env python3
"""AVD Fleet Orchestrator — boot, kill, rotate, and status for the cluster.

Fleet lifecycle on a single Windows host:
- Parallel-friendly staggered boot with a memory-safe live budget
- Kill with port + adb verification (never reports success on a lie)
- Hot-swap rotate for worker replacement
- Optional per-device post-boot setup (browser_setup.py) when present

All paths resolve from cluster/config/fleet.json so the repo runs anywhere.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET_CFG = ROOT / "cluster" / "config" / "fleet.json"
LIVE_STATE = ROOT / "fleet-state" / "live.json"


def _cfg():
    if not FLEET_CFG.exists():
        sys.exit(f"fleet.json missing at {FLEET_CFG} — copy cluster/config/fleet.json "
                 "into place and point avd_home/sdk_root at your machine")
    return json.loads(FLEET_CFG.read_text(encoding="utf-8-sig"))


def adb(serial, *args, timeout=30):
    """adb invocation; path resolves from ANDROID_SDK_ROOT, then fleet.json,
    then PATH."""
    import os, shutil
    c = _cfg()
    candidates = [
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb.exe",
        Path(c["sdk_root"]) / "platform-tools" / "adb.exe",
    ]
    adb_path = next((str(p) for p in candidates if p.exists()), None) \
        or shutil.which("adb")
    if not adb_path:
        sys.exit("adb not found — set ANDROID_SDK_ROOT or sdk_root in "
                 "cluster/config/fleet.json to your SDK location")
    return subprocess.run([adb_path, "-s", serial, *args],
                          capture_output=True, text=True, timeout=timeout)


def adb_devices():
    """Global `adb devices` output via the shared path resolver."""
    import os, shutil
    c = _cfg()
    candidates = [
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb.exe",
        Path(c["sdk_root"]) / "platform-tools" / "adb.exe",
    ]
    adb_path = next((str(p) for p in candidates if p.exists()), None) \
        or shutil.which("adb")
    if not adb_path:
        sys.exit("adb not found — set ANDROID_SDK_ROOT or sdk_root in "
                 "cluster/config/fleet.json to your SDK location")
    return subprocess.run([adb_path, "devices"],
                          capture_output=True, text=True, timeout=15).stdout


def adb_shell(serial, cmd, timeout=30):
    return adb(serial, "shell", cmd, timeout=timeout).stdout.strip()


def boot_cmd(avd_name, port, headless=True):
    """Emulator launch command from fleet.json boot settings.

    Plain virtualization flags only — the guest identifies as the emulator
    it is. No identity, prop, or network masking happens here.
    """
    b = _cfg()["boot"]
    import os
    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or _cfg()["sdk_root"]
    emu = Path(sdk_root) / "emulator" / "emulator.exe"
    if not emu.exists():
        sys.exit(f"emulator not found at {emu} — set ANDROID_SDK_ROOT or "
                 "sdk_root in cluster/config/fleet.json to your SDK location")
    cmd = [
        str(emu),
        "-avd", avd_name,
        "-port", str(port),
        "-gpu", b["gpu_mode"],
        "-no-boot-anim",
        "-no-metrics",
        "-cores", str(b["vcores"]),
        "-memory", str(b["ram_mb"]),
        "-no-snapshot-load",
    ]
    if headless:
        cmd.append("-no-window")
    return cmd


def live_state():
    if LIVE_STATE.exists():
        return json.loads(LIVE_STATE.read_text(encoding="utf-8-sig"))
    return {"live": [], "booting": []}


def save_live_state(s):
    LIVE_STATE.parent.mkdir(parents=True, exist_ok=True)
    LIVE_STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def wait_boot(serial, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = adb_shell(serial, "getprop sys.boot_completed", timeout=10)
        except Exception:
            r = ""  # device offline / adb hiccup during early boot — keep polling
        if r == "1":
            return True
        time.sleep(3)
    return False


def _wait_port_closed(port, iterations=45):
    """Block until the emulator console port actually closes — relaunching
    too early trips the FATAL multi-instance AVD lock."""
    for _ in range(iterations):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(1)
        except OSError:
            return
    raise RuntimeError(f"emulator port {port} never closed")


def boot_one(index, wait=True):
    """Boot phone by index. Returns serial on success."""
    c = _cfg()
    serial = f"emulator-{c['base_port'] + index * 2}"
    avd = f"PxCluster_{index:02d}"
    env = {**os.environ, "ANDROID_AVD_HOME": c["avd_home"]}
    subprocess.Popen(boot_cmd(avd, c["base_port"] + index * 2), env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state = live_state()
    if index not in state["booting"]:
        state["booting"].append(index)
    save_live_state(state)
    if not wait:
        return serial
    if not wait_boot(serial):
        return None
    # optional post-boot device setup, if the operator installed it
    setup = ROOT / "cluster" / "scripts" / "browser_setup.py"
    if setup.exists():
        r = subprocess.run([sys.executable, str(setup), "--serial", serial],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"  setup warn: {(r.stderr or r.stdout)[-200:]}")
    state = live_state()
    state["booting"] = [x for x in state["booting"] if x != index]
    if index not in state["live"]:
        state["live"].append(index)
    save_live_state(state)
    return serial


def kill_one(index):
    """Kill phone by index with full verification. Returns True if gone."""
    c = _cfg()
    serial = f"emulator-{c['base_port'] + index * 2}"
    port = c["base_port"] + index * 2
    adb(serial, "emu", "kill")
    # verify: the console kill can fail silently — poll the port
    gone = False
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(1)
        except OSError:
            gone = True
            break
    if not gone:
        # hard fallback: stop the emulator process listening on this port
        try:
            subprocess.run(["powershell", "-NoProfile", "-c",
                            f"$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue; "
                            "if ($c) { Stop-Process -Id ($c | Select-Object -First 1).OwningProcess -Force }"],
                           capture_output=True, timeout=60)
            for _ in range(15):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        time.sleep(1)
                except OSError:
                    gone = True
                    break
        except Exception:
            pass
    # wait for the serial to vanish from adb too, so fleet.status reads
    # truthfully the moment this call returns
    for _ in range(15):
        devices = adb_devices()
        if serial not in devices:
            break
        time.sleep(1)
    state = live_state()
    state["live"] = [x for x in state["live"] if x != index]
    state["booting"] = [x for x in state["booting"] if x != index]
    save_live_state(state)
    return gone


def status():
    c = _cfg()
    devices = adb_devices()
    print(f"#   AVD           SERIAL          STATE")
    for i in range(c["max_instances"]):
        serial = f"emulator-{c['base_port'] + i * 2}"
        live = serial + "\tdevice" in devices
        print(f"{i:<3} {f'PxCluster_{i:02d}':<13} {serial:<15} {'LIVE' if live else 'off'}")


def rotate():
    """Hot-swap: kill the oldest live phone, boot the next off one."""
    c = _cfg()
    devices = adb_devices()
    live = [i for i in range(c["max_instances"])
            if f"emulator-{c['base_port'] + i * 2}\tdevice" in devices]
    if not live:
        print("no live phones to rotate")
        return
    victim = live[0]
    kill_one(victim)
    print(f"rotated out PxCluster_{victim:02d}")
    for i in range(c["max_instances"]):
        if i not in live:
            serial = boot_one(i, wait=True)
            print(f"rotated in PxCluster_{i:02d}" + (f" as {serial}" if serial else " — BOOT FAILED"))
            return


def main():
    ap = _argparse()
    args = ap.parse_args()
    if args.cmd == "boot":
        if args.index is not None:
            serial_i = f"emulator-{_cfg()['base_port'] + args.index * 2}"
            devices = adb_devices()
            if serial_i + "\tdevice" in devices:
                print(f"[{args.index:02d}] already live — skip")
            else:
                print(f"[{args.index:02d}] launching PxCluster_{args.index:02d}")
                serial = boot_one(args.index, wait=True)
                print(f"[{args.index:02d}] {'LIVE as ' + serial if serial else 'BOOT FAILED'}")
            return 0
        n = args.count or _cfg()["default_live_budget"]
        print(f"Booting {n} phones (staggered)...")
        for i in range(n):
            serial_i = f"emulator-{_cfg()['base_port'] + i * 2}"
            devices = adb_devices()
            if serial_i + "\tdevice" in devices:
                print(f"[{i:02d}] already live — skip")
                continue
            print(f"[{i:02d}] launching PxCluster_{i:02d}")
            serial = boot_one(i, wait=True)
            print(f"[{i:02d}] {'LIVE as ' + serial if serial else 'BOOT FAILED'}")
        return 0

    if args.cmd == "boot-one":
        if args.index is None:
            print("--index required"); return 1
        serial = boot_one(args.index, wait=args.wait)
        print(f"LIVE as {serial}" if serial else "BOOT FAILED")
        return 0 if serial else 1

    if args.cmd == "kill":
        if args.index is None:
            print("--index required"); return 1
        ok = kill_one(args.index)
        name = f"PxCluster_{args.index:02d}"
        print(f"killed {name}" if ok
              else f"kill FAILED for {name} — emulator still alive, port {_cfg()['base_port'] + args.index * 2} open")
        return 0 if ok else 1

    if args.cmd == "kill-all":
        c = _cfg()
        devices = adb_devices()
        for i in range(c["max_instances"]):
            if f"emulator-{c['base_port'] + i * 2}\tdevice" in devices:
                kill_one(i)
                print(f"killed PxCluster_{i:02d}")
        return 0

    if args.cmd == "status":
        status()
        return 0

    if args.cmd == "rotate":
        rotate()
        return 0

    print("unknown command"); return 1


def _argparse():
    import argparse
    ap = argparse.ArgumentParser(description="AVD fleet orchestrator")
    ap.add_argument("cmd", choices=["boot", "boot-one", "kill", "kill-all", "status", "rotate"])
    ap.add_argument("--index", type=int, help="phone index for boot-one/kill/boot")
    ap.add_argument("--count", type=int, help="how many phones to boot")
    ap.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True,
                    help="wait for full boot (default true)")
    return ap


if __name__ == "__main__":
    sys.exit(main())
