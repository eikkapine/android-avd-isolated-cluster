#!/usr/bin/env python3
"""Browser Setup — post-boot device preparation for UI automation.

Prepares a freshly booted emulator for hands-off browser automation:
- suppresses system-wide ANR/crash dialogs (kiosk mode), so app crash
  bursts never block the UI — the app recovers on its own
- walks Chrome's first-run screens (terms, account choice, notification
  card) by tapping their buttons via UI dumps, under a temporary English
  app locale so card labels match, then restores the slot's locale
- dismisses crash ("keeps stopping") and ANR ("isn't responding") dialogs
  by stable resource-ids — locale-proof, never relaunches mid-storm
- success requires two consecutive clean screens plus a settle pass
  inside the crash-burst window before writing the done-marker

Usage: python browser_setup.py --serial emulator-5554 [--locale en-US] [--force]
"""
import argparse
import re
import subprocess
import sys
import time

MARKER = "/data/local/tmp/browser_ready"


def adb(serial, *args, timeout=30):
    sdk = subprocess.run(["where", "adb"], capture_output=True, text=True)
    adb_path = sdk.stdout.strip().splitlines()[0] if sdk.stdout.strip() else "adb"
    return subprocess.run([adb_path, "-s", serial, *args],
                          capture_output=True, text=True, timeout=timeout)


def shell(serial, cmd, timeout=45):
    try:
        return adb(serial, "shell", cmd, timeout=timeout).stdout
    except Exception:
        return ""


def suppress_error_dialogs(serial):
    """Kiosk mode: hide crash/ANR popups system-wide."""
    shell(serial, "settings put global hide_error_dialogs 1")


def set_app_locale(serial, locale, pkg="com.android.chrome"):
    """Per-app locale: the runtime system locale doesn't follow persist
    props on all images; set it where apps actually read it."""
    r = shell(serial, f"cmd locale set-app-locales {pkg} --locales {locale}")
    return "ok" if "error" not in r.lower() or not r else r.strip()[:60]


def prime_browser(serial, force=False):
    """One-time Chrome setup per device: walks the first-run screens and
    dismisses system dialogs by tapping their buttons via UI dumps, so
    later automation sessions open straight to the start page.
    The walk runs under a temporary English app locale so the card labels
    match, then the caller switches the slot's real locale back in.
    A marker file makes this a once-per-device step."""
    marker = shell(serial, f"test -f {MARKER} && echo yes")
    if marker.strip() == "yes" and not force:
        return False
    # English UI for the setup walk so the known labels match
    shell(serial, "cmd locale set-app-locales com.android.chrome --locales en-US")
    shell(serial, "am start -a android.intent.action.VIEW -d about:blank")
    time.sleep(8)

    bounds_pat = r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    card_labels = ("Use without an account", "Accept & continue",
                   "No thanks", "Decline", "Not now", "Continue")

    def _tap(d, pattern):
        m = re.search(pattern, d)
        if not m:
            return None
        return ((int(m.group(1)) + int(m.group(3))) // 2,
                (int(m.group(2)) + int(m.group(4))) // 2)

    clean_streak = 0
    anr_seen = 0
    for _ in range(14):
        d = shell(serial, "uiautomator dump /sdcard/pu.xml >/dev/null 2>&1; cat /sdcard/pu.xml")
        # system dialogs first — ANR ("isn't responding") has a Wait button:
        # keep the system alive, only tap Wait. App crashes get Close app.
        # Both match by stable resource-ids, locale-proof.
        if 'resource-id="android:id/aerr_wait"' in d:
            anr_seen += 1
            if anr_seen >= 3:
                # System UI wedged by the crash-dialog storm — restart it
                shell(serial, "killall com.android.systemui")
                anr_seen = 0
                time.sleep(8)
                clean_streak = 0
                continue
            pos = _tap(d, r'resource-id="android:id/aerr_wait"[^>]*' + bounds_pat)
            if pos:
                shell(serial, f"input tap {pos[0]} {pos[1]}")
            time.sleep(3)
            clean_streak = 0
            continue
        pos = _tap(d, r'resource-id="android:id/aerr_close"[^>]*' + bounds_pat)
        if pos:
            # crash dialog — tap Close app; never relaunch mid-storm, the
            # burst exhausts itself and the app falls back to software
            shell(serial, f"input tap {pos[0]} {pos[1]}")
            time.sleep(2)
            clean_streak = 0
            continue
        pos = None
        # first-run cards — uiautomator XML-escapes text, match escaped form
        for label in card_labels:
            pos = _tap(d, rf'text="{label.replace("&", "&" + "amp;")}"[^>]*' + bounds_pat)
            if pos:
                break
        if pos:
            shell(serial, f"input tap {pos[0]} {pos[1]}")
            time.sleep(3)
            clean_streak = 0
            continue
        clean_streak += 1
        if clean_streak >= 2:
            break  # two consecutive clean screens — browser is stable
        time.sleep(3)
    if clean_streak < 2:
        return False  # dialogs or cards keep coming — retry next boot
    # the crash burst fires a few seconds AFTER chrome's first clean paint —
    # one final settle pass inside that window before trusting the state
    time.sleep(8)
    d = shell(serial, "uiautomator dump /sdcard/pu.xml >/dev/null 2>&1; cat /sdcard/pu.xml")
    if 'resource-id="android:id/aerr_close"' in d or 'resource-id="android:id/aerr_wait"' in d:
        return False  # burst landed late — retry next boot
    shell(serial, "am force-stop com.android.chrome")
    shell(serial, f"touch {MARKER}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Post-boot browser setup for one emulator")
    ap.add_argument("--serial", required=True, help="adb serial, e.g. emulator-5554")
    ap.add_argument("--locale", default="en-US", help="app locale to set (default en-US)")
    ap.add_argument("--force", action="store_true", help="re-run the first-run walk even if done")
    args = ap.parse_args()

    suppress_error_dialogs(args.serial)
    print(f"error dialogs suppressed on {args.serial}")
    print(f"app locale {args.locale}: {set_app_locale(args.serial, args.locale)}")
    ok = prime_browser(args.serial, force=args.force)
    print("browser setup: first-run walked" if ok else "browser setup: skipped or incomplete")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
