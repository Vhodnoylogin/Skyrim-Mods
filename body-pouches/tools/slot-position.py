"""Moves a VRIK slot to where the player's hand was, using the mod's own measurements.

    python tools/slot-position.py --log <BodyPouches.log> --ini <vrikslots.ini> [--slot 13]
                                  [--count 3] [--apply] [--force]

Every squeeze of an empty hand's grip makes the mod write a line like

    the left hand squeezed at slot 13's posX = -1.234, posY = 12.345, posZ = -8.765, ...

- the posX/posY/posZ that would put the slot exactly at the hand (src/Mod.cpp, Measure).
This takes the last --count of those for the slot, their median along each axis, and
writes it over posXN, posYN and posZN in the given vrikslots.ini. Without --apply it
only shows what it would do.

WHICH FILE. The one the game reads, which under MO2 is the copy in the build's VRIK
config mod - never the file inside VRIK itself. VRIK reads a slot's place only when
the game starts, and writes the file when a holster is moved in the game, so the file
is changed with the game closed. The old values are printed, so the change can be
put back by hand.
"""

import argparse
import re
import statistics
import subprocess
import sys

SQUEEZE = re.compile(
    r"squeezed at slot (?P<slot>\d+)'s posX = (?P<x>-?\d+(?:\.\d+)?), "
    r"posY = (?P<y>-?\d+(?:\.\d+)?), posZ = (?P<z>-?\d+(?:\.\d+)?)")

# Three squeezes at one place that disagree by more than this are not one place.
MAX_SPREAD = 6.0


def squeezes(log_path, slot):
    found = []
    with open(log_path, encoding="utf-8", errors="replace") as log:
        for line in log:
            m = SQUEEZE.search(line)
            if m and int(m.group("slot")) == slot:
                found.append((float(m.group("x")), float(m.group("y")), float(m.group("z")), line.strip()))
    return found


def game_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SkyrimVR.exe"],
                             capture_output=True, text=True).stdout
    except OSError:
        return False
    return "SkyrimVR.exe" in out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", required=True)
    ap.add_argument("--ini", required=True)
    ap.add_argument("--slot", type=int, default=13)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="write even if the squeezes disagree")
    args = ap.parse_args()

    found = squeezes(args.log, args.slot)
    if len(found) < args.count:
        print(f"{args.log}: {len(found)} squeezes for slot {args.slot}, {args.count} needed")
        return 1
    last = found[-args.count:]
    print(f"the last {len(last)} squeezes for slot {args.slot}:")
    for x, y, z, _ in last:
        print(f"  posX = {x:9.3f}  posY = {y:9.3f}  posZ = {z:9.3f}")

    median = [statistics.median(v[i] for v in last) for i in range(3)]
    spread = max(max(abs(v[i] - median[i]) for v in last) for i in range(3))
    print(f"median: posX = {median[0]:.3f}, posY = {median[1]:.3f}, posZ = {median[2]:.3f}; "
          f"furthest squeeze {spread:.1f} units off")
    if spread > MAX_SPREAD and not args.force:
        print(f"the squeezes disagree by more than {MAX_SPREAD} units - squeeze again at one place, or --force")
        return 1

    raw = open(args.ini, "rb").read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8").splitlines()
    names = [f"pos{axis}{args.slot}" for axis in "XYZ"]
    old = {}
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in names:
            old[key] = line.split("=", 1)[1].strip()
            lines[i] = f"{key} = {median[names.index(key)]:.7f}"
    missing = [n for n in names if n not in old]
    if missing:
        print(f"{args.ini} has no line for {', '.join(missing)} - is it a whole copy of vrikslots.ini?")
        return 1

    for n in names:
        print(f"  {n}: {old[n]} -> {median[names.index(n)]:.7f}")
    if not args.apply:
        print("dry run - add --apply")
        return 0
    if game_running():
        print("the game is running: VRIK would write its own values back - close it first")
        return 1

    open(args.ini, "wb").write((newline.join(lines) + newline).encode("utf-8"))
    print(f"written: {args.ini}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
