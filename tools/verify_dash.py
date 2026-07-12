"""Browser-level proof for the realtime SSE dashboard (ui/serve.py).

Drives a real headless Chromium (python-playwright) against a fixture fleet and
asserts the contract the unit tests can't see:
  (a) zero console errors on load and across the run
  (b) backlog panel renders the seeded tiers/items
  (c) clicking an agent row expands detail containing the actual dispatch prompt
  (d) file changes push to the page over SSE within ~5s WITHOUT reload
  (e) the expanded row is STILL expanded after those live updates

Run: python tools/verify_dash.py            (exit 0 = proven, 1 = failed)
Skips with exit 0 + SKIP message if playwright/chromium is unavailable
(so CI without browsers doesn't fail; run locally for the real proof).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVE = REPO / "ui" / "serve.py"

FIXTURE_BACKLOG = """# Audit backlog — verify_dash fixture

**Status legend:** ⬜ unclaimed · 🔵 dispatched · ✅ merged · ⏸ user call

## P0 — correctness / security

- ✅ **[sec] BACKLOG-SEED-ALPHA item.** done.
- 🔵 **[js] BACKLOG-SEED-BETA item.** in flight.

## Landing log
- fixture
"""

AGENT_FULL_ID = "verifyagent0123456789ab"
PROMPT_MARKER = "FIXTURE-PROMPT-MARKER: rebuild the flux capacitor"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def build_fixture(root: Path, hint: str):
    (root / "state").mkdir(exist_ok=True)
    (root / "transcripts").mkdir(exist_ok=True)
    (root / "dash").mkdir(exist_ok=True)
    (root / "AUDIT-BACKLOG.md").write_text(FIXTURE_BACKLOG, encoding="utf-8")
    # Fake detector: reads hint.txt so live agent updates are deterministic.
    (root / "hint.txt").write_text(hint, encoding="utf-8")
    fake = (
        "import { readFileSync } from 'node:fs';\n"
        "const hint = readFileSync(new URL('../hint.txt', import.meta.url), 'utf8').trim();\n"
        "console.log(JSON.stringify([{id:'" + AGENT_FULL_ID[:13] + "',"
        "status:'running',age_s:4,hint:hint,taskLabel:hint}]));\n"
    )
    (root / "dash" / "dash-extra.mjs").write_text(fake, encoding="utf-8")
    transcript = root / "transcripts" / f"{AGENT_FULL_ID}.output"
    lines = [
        json.dumps({"type": "user", "parentUuid": None,
                    "message": {"content": PROMPT_MARKER}}),
        json.dumps({"type": "assistant", "model": "claude-haiku-4-5",
                    "message": {"content": "working"}}),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # fingerprint seed so the collector re-invokes the fake detector on touch
    (root / "transcripts" / "agent-seed.jsonl").write_text("{}\n", encoding="utf-8")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: python-playwright not installed")
        return 0

    root = Path(tempfile.mkdtemp(prefix="aesop-verify-dash-"))
    port = free_port()
    env = dict(os.environ,
               AESOP_ROOT=str(root),
               AESOP_TRANSCRIPTS_ROOT=str(root / "transcripts"),
               AESOP_UI_COLLECT_INTERVAL="0.3",
               PORT=str(port))
    build_fixture(root, hint="initial fixture task")
    server = subprocess.Popen([sys.executable, str(SERVE)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    console_errors = []
    failures = []
    try:
        # wait for server
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            print("FAIL: server never came up")
            return 1

        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True)
            except Exception as e:
                print(f"SKIP: chromium unavailable ({e}); run: python -m playwright install chromium")
                return 0
            page = browser.new_page()
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")

            # (b) backlog panel renders seeded items
            try:
                page.wait_for_selector("#backlog-tiers:not(.loading)", timeout=8000)
                assert "BACKLOG-SEED-ALPHA" in page.inner_text("#backlog-tiers")
            except Exception as e:
                failures.append(f"(b) backlog panel did not render seed items: {e}")

            # (c) click agent row -> expands with the real dispatch prompt
            try:
                page.wait_for_selector(".agent-row", timeout=8000)
                page.click(".agent-row")
                page.wait_for_selector(".agent-row.expanded", timeout=4000)
                page.wait_for_function(
                    "document.querySelector('.agent-row.expanded .agent-details')"
                    f" && document.querySelector('.agent-row.expanded .agent-details').innerText.includes('FIXTURE-PROMPT-MARKER')",
                    timeout=8000)
            except Exception as e:
                failures.append(f"(c) click-to-expand with prompt failed: {e}")

            # (d) live updates over SSE, no reload: backlog file + agent hint change
            try:
                bl = root / "AUDIT-BACKLOG.md"
                content = bl.read_text(encoding="utf-8").replace(
                    "## Landing log",
                    "- ⬜ **[test] LIVE-BACKLOG-MARKER item.** pushed live.\n\n## Landing log")
                bl.write_text(content, encoding="utf-8")
                (root / "hint.txt").write_text("LIVE-AGENT-MARKER task", encoding="utf-8")
                (root / "transcripts" / "agent-live.jsonl").write_text("{}\n", encoding="utf-8")
                page.wait_for_function(
                    "document.querySelector('#backlog-tiers').innerText.includes('LIVE-BACKLOG-MARKER')",
                    timeout=8000)
                page.wait_for_function(
                    "document.querySelector('#agents-list').innerText.includes('LIVE-AGENT-MARKER')",
                    timeout=8000)
            except Exception as e:
                failures.append(f"(d) live SSE update did not reach the page: {e}")

            # (e) expansion survived the live updates
            try:
                assert page.query_selector(".agent-row.expanded") is not None, \
                    "expanded row lost after live updates"
            except Exception as e:
                failures.append(f"(e) {e}")

            # (a) console clean across the whole run
            time.sleep(1.0)
            real_errors = [e for e in console_errors if "favicon" not in e.lower()]
            if real_errors:
                failures.append(f"(a) console errors: {real_errors[:5]}")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(root, ignore_errors=True)

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("PROVEN: (a) console clean (b) backlog rendered (c) click-expand with prompt "
          "(d) SSE live updates without reload (e) expansion survived updates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
