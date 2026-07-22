#!/usr/bin/env python3
"""test_battery.py -- run the local union test battery, parallel by default.

Runs the four harnesses (python unittest discover, node --test, shell suites,
ui vitest+tsc) as concurrent subprocesses with per-harness rc capture, stdin
closed (the hook suite hangs on never-EOF stdin), and an explicit summary
table. Exit 0 only when every harness exits 0.

Usage:
  python tools/test_battery.py [--serial] [--skip ui|sh|node|py ...] [--json]

--serial runs harnesses one at a time (the pre-wave-29 behavior; fallback if
parallel runs prove load-fragile on a box). Logs land in the state scratch dir
(AESOP_BATTERY_LOGDIR or the system temp dir) as battery-<harness>.log.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

HARNESSES = {
    "py": [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    "node": ["npm", "run", "test:node"],
    "sh": ["npm", "run", "test:sh"],
    "ui": None,  # composite: tsc + vitest, run via _ui_command
}


def _ui_command():
    # ui/web needs node_modules; npx resolves local binaries.
    return "npx tsc --noEmit && npx vitest run --silent"


def run_harness(name, logdir, parallel=True):
    """Spawn one harness with stdin closed; return (name, Popen, logfile)."""
    log = Path(logdir) / f"battery-{name}.log"
    f = open(log, "w", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    if parallel and name == "node" and "AESOP_TEST_CHILD_TIMEOUT_MS" not in env:
        # Under 4-harness parallel load, scaffold child processes legitimately
        # exceed the 30s solo ceiling; the tests honor this knob (wave-29).
        env["AESOP_TEST_CHILD_TIMEOUT_MS"] = "90000"
    if name == "ui":
        proc = subprocess.Popen(
            _ui_command(), shell=True, cwd=str(REPO / "ui" / "web"),
            stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, env=env,
        )
    else:
        # npm needs shell resolution on Windows.
        use_shell = os.name == "nt" and HARNESSES[name][0] == "npm"
        cmd = " ".join(HARNESSES[name]) if use_shell else HARNESSES[name]
        proc = subprocess.Popen(
            cmd, shell=use_shell, cwd=str(REPO),
            stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, env=env,
        )
    return name, proc, f, log


def main():
    ap = argparse.ArgumentParser(description="Run the local union test battery")
    ap.add_argument("--serial", action="store_true", help="run harnesses sequentially")
    ap.add_argument("--skip", action="append", default=[], choices=list(HARNESSES),
                    help="skip a harness (repeatable)")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    logdir = os.environ.get("AESOP_BATTERY_LOGDIR") or tempfile.mkdtemp(prefix="aesop-battery-")
    names = [n for n in HARNESSES if n not in args.skip]
    started = time.time()
    results = {}

    if args.serial:
        for n in names:
            name, proc, f, log = run_harness(n, logdir, parallel=False)
            rc = proc.wait()
            f.close()
            results[name] = {"rc": rc, "log": str(log)}
    else:
        procs = [run_harness(n, logdir) for n in names]
        for name, proc, f, log in procs:
            rc = proc.wait()
            f.close()
            results[name] = {"rc": rc, "log": str(log)}

    wall = round(time.time() - started, 1)
    ok = all(r["rc"] == 0 for r in results.values())
    if args.json:
        print(json.dumps({"ok": ok, "wall_s": wall, "mode": "serial" if args.serial else "parallel",
                          "results": results}))
    else:
        print(f"battery mode={'serial' if args.serial else 'parallel'} wall={wall}s")
        for n, r in results.items():
            verdict = "PASS" if r["rc"] == 0 else "FAIL"
            print(f"  {n:5s} rc={r['rc']}  {verdict}  log={r['log']}")
        print("BATTERY:", "GREEN" if ok else "RED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
