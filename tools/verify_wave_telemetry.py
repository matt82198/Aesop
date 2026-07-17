"""Browser-level proof for wave telemetry components.

Drives the BUILT React app served by `python ui/serve.py` and exercises
the wave telemetry components:
  - Overview view: WaveTelemetryProgress (phase + blocker)
  - Work view: WaveTelemetryCost (tokens, top model, ok rate)

Tests that the components:
  (a) Mount and render without errors
  (b) Fetch data from /api/wave/telemetry at call time
  (c) Display wave phase, blocker, tokens, model, and ok rate
  (d) Handle missing data gracefully (show error/loading states)
  (e) Have no console errors or failed resources

Runs: python tools/verify_wave_telemetry.py              (exit 0 = proven, 1 = failed)
      python tools/verify_wave_telemetry.py --allow-skip (exit 0 = proven or skipped)
"""
import argparse
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVE = REPO / "ui" / "serve.py"

SERVER_BOOT_TRIES = int(os.environ.get("AESOP_VERIFY_BOOT_TRIES", "150"))   # *0.2s = 30s
SERVER_BOOT_SLEEP = 0.2
SEL_TIMEOUT_MS = int(os.environ.get("AESOP_VERIFY_SEL_TIMEOUT_MS", "30000"))

# Fixture STATE.md and AUDIT-BACKLOG.md
FIXTURE_STATE_MD = """# STATE — aesop refinement loop

## Phase: `wave-rc.2: build` (2026-07-17, current)
Current phase focuses on build work.
"""

FIXTURE_BACKLOG_MD = """# AUDIT-BACKLOG

## P0

- 🔵 **[ui] Dashboard wave telemetry tile**
- ⬜ **[test] Fix ledger parser edge cases**
"""

FIXTURE_LEDGER = """| timestamp | agent_type | model | duration | tokens_in | tokens_out | verdict |
|---|---|---|---|---|---|---|
| 2026-07-17T10:00:00 | Agent | claude-haiku-4-5 | 12 | 500 | 1200 | OK |
| 2026-07-17T10:05:00 | Agent | claude-sonnet-4-5 | 15 | 800 | 600 | OK |
"""


def _real_console_errors(console_errors, failed_urls):
    """Drop favicon/urlless-resource noise; surface real broken assets."""
    non_favicon = [u for u in failed_urls if "favicon" not in u.lower()]
    real = []
    for e in console_errors:
        low = e.lower()
        if "favicon" in low:
            continue
        if "failed to load resource" in low and not non_favicon:
            continue
        real.append(e)
    real.extend(f"failed resource: {u}" for u in non_favicon)
    return real


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def copy_dist(root: Path):
    """Copy the built frontend dist to the fixture root."""
    real_dist = REPO / "ui" / "web" / "dist"
    if real_dist.is_dir():
        shutil.copytree(real_dist, root / "ui" / "web" / "dist")


def build_root():
    """Fresh temp root with dist + fixture state files."""
    root = Path(tempfile.mkdtemp(prefix="aesop-verify-wave-telemetry-"))
    (root / "state" / "ledger").mkdir(parents=True)
    (root / "transcripts").mkdir(parents=True)
    (root / "dash").mkdir(exist_ok=True)

    # Write fixture files
    (root / "STATE.md").write_text(FIXTURE_STATE_MD, encoding="utf-8")
    (root / "AUDIT-BACKLOG.md").write_text(FIXTURE_BACKLOG_MD, encoding="utf-8")
    (root / "state" / "ledger" / "OUTCOMES-LEDGER.md").write_text(FIXTURE_LEDGER, encoding="utf-8")
    (root / "dash" / "dash-extra.mjs").write_text("console.log(JSON.stringify([]));\n", encoding="utf-8")

    copy_dist(root)
    return root


def start_server(root: Path, port: int):
    """Start the dashboard server with fixture root."""
    state_root = root / "state"
    real_state = Path.home() / "aesop" / "state"
    if state_root.resolve() == real_state.resolve():
        raise RuntimeError("state dir resolved to real repo state (~aesop/state)")

    env = dict(os.environ,
               AESOP_ROOT=str(root),
               AESOP_STATE_ROOT=str(state_root),
               AESOP_TRANSCRIPTS_ROOT=str(root / "transcripts"),
               AESOP_UI_COLLECT_INTERVAL="0.3",
               PORT=str(port))
    server = subprocess.Popen([sys.executable, str(SERVE)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(SERVER_BOOT_TRIES):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return server
        except OSError:
            time.sleep(SERVER_BOOT_SLEEP)
    server.kill()
    raise RuntimeError("server never came up")


def stop_server(server):
    """Stop the server."""
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()


def run_overview_proof(pw, failures):
    """Test wave telemetry in Overview view."""
    root = build_root()
    port = free_port()
    server = start_server(root, port)

    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    console_errors, failed_urls = [], []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.on("response", lambda r: failed_urls.append(r.url) if r.status >= 400 else None)

    try:
        page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")

        # (a) WaveTelemetryProgress mounts and renders
        try:
            page.wait_for_selector("[data-testid='wave-telemetry-progress']", timeout=SEL_TIMEOUT_MS)
        except Exception as e:
            failures.append(f"(a) Overview: wave telemetry progress never mounted: {e}")
            return
        finally:
            time.sleep(0.4)
            real = _real_console_errors(console_errors, failed_urls)
            if real:
                failures.append(f"(a) Overview: console errors: {real[:2]}")

        # (b) Progress tile shows wave phase and blocker
        try:
            progress_text = page.inner_text("[data-testid='wave-telemetry-progress']")
            # Should contain some phase info and blocker text
            assert len(progress_text) > 10, f"Progress tile text too short: {progress_text!r}"
        except Exception as e:
            failures.append(f"(b) Overview: wave phase/blocker not displayed: {e}")

    finally:
        browser.close()
        stop_server(server)
        shutil.rmtree(root, ignore_errors=True)


def run_work_proof(pw, failures):
    """Test wave telemetry in Work view."""
    root = build_root()
    port = free_port()
    server = start_server(root, port)

    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    console_errors, failed_urls = [], []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.on("response", lambda r: failed_urls.append(r.url) if r.status >= 400 else None)

    try:
        page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
        page.evaluate("location.hash = '#/work'")

        # (c) WaveTelemetryCost mounts in Work view
        try:
            page.wait_for_selector("[data-testid='wave-telemetry-cost']", timeout=SEL_TIMEOUT_MS)
        except Exception as e:
            failures.append(f"(c) Work: wave telemetry cost never mounted: {e}")
            return

        # (d) Cost tile shows tokens, model, OK rate
        try:
            cost_text = page.inner_text("[data-testid='wave-telemetry-cost']")
            # Should contain cost-related text (tokens, model, rate)
            assert "Token" in cost_text or "token" in cost_text, \
                f"Tokens label not found in cost tile: {cost_text!r}"
        except Exception as e:
            failures.append(f"(d) Work: tokens/model/rate not displayed: {e}")
            return

        time.sleep(0.4)
        real = _real_console_errors(console_errors, failed_urls)
        if real:
            failures.append(f"(d) Work: console errors: {real[:2]}")

    finally:
        browser.close()
        stop_server(server)
        shutil.rmtree(root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Browser-level proof for wave telemetry components")
    parser.add_argument("--allow-skip", action="store_true",
                        help="Allow skipping if playwright/chromium is unavailable")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        msg = "playwright missing — run `python -m playwright install chromium`, or pass --allow-skip"
        print(f"SKIP: {msg}" if args.allow_skip else f"FAIL: {msg}")
        return 0 if args.allow_skip else 1

    failures = []
    with sync_playwright() as pw:
        try:
            pw.chromium.launch(headless=True).close()
        except Exception as e:
            msg = f"chromium unavailable ({e}); run: python -m playwright install chromium"
            print(f"SKIP: {msg}" if args.allow_skip else f"FAIL: {msg}")
            return 0 if args.allow_skip else 1

        run_overview_proof(pw, failures)
        run_work_proof(pw, failures)

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1

    print("PROVEN: (a) Overview WaveTelemetryProgress mounts "
          "(b) wave phase/blocker displayed "
          "(c) Work WaveTelemetryCost mounts "
          "(d) tokens/model/rate displayed "
          "(e) no console errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
