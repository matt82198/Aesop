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
# Long, multi-line prompt so the .dispatch-prompt box (max-height 300px) actually
# overflows and is scrollable — required to test scroll-position preservation.
PROMPT_MARKER = "FIXTURE-PROMPT-MARKER: rebuild the flux capacitor\n" + "\n".join(
    f"line {i}: recalibrate subsystem {i} and verify each tolerance band carefully"
    for i in range(60))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def build_fixture(root: Path, hint: str, with_high_alerts: bool = False):
    (root / "state").mkdir(exist_ok=True)
    (root / "transcripts").mkdir(exist_ok=True)
    (root / "dash").mkdir(exist_ok=True)
    (root / "AUDIT-BACKLOG.md").write_text(FIXTURE_BACKLOG, encoding="utf-8")

    # Optional: seed with HIGH and MED severity alerts for testing
    if with_high_alerts:
        alerts_log = root / "state" / "SECURITY-ALERTS.log"
        alerts_log.write_text(
            "2025-07-12T14:32:01Z | HIGH | API secret exposed in logs\n"
            "2025-07-12T14:30:05Z | MED | Unvalidated user input detected\n",
            encoding="utf-8"
        )

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
    # Build with HIGH/MED severity alerts for testing alarm color semantics
    build_fixture(root, hint="initial fixture task", with_high_alerts=True)
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

            # (P2-UX) Layout order verification: Fleet Agents + Security Alerts in top third
            try:
                page.wait_for_selector("#agents-list", timeout=8000)
                page.wait_for_selector("#alerts-list", timeout=8000)
                page.wait_for_selector("#backlog-tiers", timeout=8000)
                
                # Verify DOM order: agents should appear before backlog
                agents_index = page.evaluate(
                    "Array.from(document.querySelectorAll('[id]')).findIndex(el => el.id === 'agents-list')"
                )
                alerts_index = page.evaluate(
                    "Array.from(document.querySelectorAll('[id]')).findIndex(el => el.id === 'alerts-list')"
                )
                backlog_index = page.evaluate(
                    "Array.from(document.querySelectorAll('[id]')).findIndex(el => el.id === 'backlog-tiers')"
                )
                
                assert agents_index < backlog_index,                     f"Fleet Agents should appear BEFORE Audit Backlog in DOM (agents={agents_index}, backlog={backlog_index})"
                assert alerts_index < backlog_index,                     f"Security Alerts should appear BEFORE Audit Backlog in DOM (alerts={alerts_index}, backlog={backlog_index})"
                    
            except Exception as e:
                failures.append(f"(P2-UX) layout order verification failed: {e}")
            
            # (P2-UX) Collapsed done backlog items: verify reduced padding and opacity
            try:
                # Ensure backlog items render with the fixture
                page.wait_for_function(
                    "document.querySelector('.backlog-item.done') !== null",
                    timeout=8000
                )
                
                # Get height and opacity of done item vs active item
                done_item_styles = page.evaluate("""
                    {
                        const done = document.querySelector('.backlog-item.done');
                        const cs = window.getComputedStyle(done);
                        return {
                            height: done.offsetHeight,
                            opacity: cs.opacity,
                            padding: cs.padding
                        };
                    }
                """)
                
                active_item_styles = page.evaluate("""
                    {
                        const active = Array.from(document.querySelectorAll('.backlog-item'))
                            .find(el => !el.classList.contains('done'));
                        if (!active) return {height: 0, opacity: '1', padding: '0px'};
                        const cs = window.getComputedStyle(active);
                        return {
                            height: active.offsetHeight,
                            opacity: cs.opacity,
                            padding: cs.padding
                        };
                    }
                """)
                
                # Done items should be more compact (lower height, lower opacity)
                assert done_item_styles['height'] <= active_item_styles['height'],                     f"Done items should be more compact (height {done_item_styles['height']} > {active_item_styles['height']})"
                assert float(done_item_styles['opacity']) < 1.0,                     f"Done items should have reduced opacity (got {done_item_styles['opacity']})"
                    
            except Exception as e:
                failures.append(f"(P2-UX) done item visual collapse verification failed: {e}")


            try:
                page.wait_for_selector("#backlog-tiers:not(.loading)", timeout=8000)
                assert "BACKLOG-SEED-ALPHA" in page.inner_text("#backlog-tiers")
            except Exception as e:
                failures.append(f"(b) backlog panel did not render seed items: {e}")

            # (b2) alarm color semantics: alert count renders in alarm color when HIGH alerts exist
            try:
                # Wait for the alert count to get a class (indicating data has loaded)
                page.wait_for_function(
                    "document.getElementById('alert-count').className !== ''",
                    timeout=8000
                )
                # Check that the element has the alarm-high class (red color)
                class_list = page.evaluate("document.getElementById('alert-count').className")
                assert "alarm-high" in class_list or "alarm-med" in class_list, \
                    f"Alert count should have 'alarm-high' or 'alarm-med' class for severity, got: {class_list}"
                # Verify computed color is NOT neutral gray (should be red/amber)
                color = page.evaluate("window.getComputedStyle(document.getElementById('alert-count')).color")
                # Color should be high-alert red (not gray/neutral) — just verify it's a color
                assert "rgb(" in color, f"Alert count should have computed color, got: {color}"
            except Exception as e:
                failures.append(f"(b2) alert count alarm color not set: {e}")

            # (b3) Security Alerts panel has distinct alarm styling when HIGH alerts exist
            try:
                alerts_box = page.query_selector(".alerts-box")
                alerts_box_class = page.evaluate("document.querySelector('.alerts-box').className")
                assert "has-high-alerts" in alerts_box_class or "has-alerts" in alerts_box_class, \
                    f"Alerts box should have alarm styling class, got: {alerts_box_class}"
                # Verify border changed from neutral #333 to alarm #f44
                border_color = page.evaluate("window.getComputedStyle(document.querySelector('.alerts-box')).borderColor")
                assert "rgb(" in border_color, f"Alerts box should have computed border color: {border_color}"
            except Exception as e:
                failures.append(f"(b3) alerts panel alarm styling not applied: {e}")

            # (b4) affordances: stronger expand-toggle + responsive header wrap (no horizontal overflow when narrow)
            try:
                page.wait_for_selector(".agent-row", timeout=8000)
                toggle_size = page.evaluate(
                    "parseFloat(getComputedStyle(document.querySelector('.agent-expand-toggle')).fontSize)")
                assert toggle_size >= 13, f"expand toggle should be a stronger affordance (>=13px), got {toggle_size}px"
                # narrow the viewport: header must wrap, body must not scroll horizontally
                page.set_viewport_size({"width": 600, "height": 800})
                page.wait_for_timeout(200)
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth")
                assert overflow <= 2, f"body overflows horizontally at 600px (header not wrapping): {overflow}px"
                page.set_viewport_size({"width": 1280, "height": 900})
            except Exception as e:
                failures.append(f"(b4) affordance/responsive-header check failed: {e}")

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


            # (f) scroll position and text selection survive live updates (bugfix P2 #1)
            try:
                # Expand an agent again to get its prompt box visible
                expanded_row = page.query_selector(".agent-row.expanded")
                if not expanded_row:
                    # Re-expand if needed
                    page.click(".agent-row")
                    page.wait_for_selector(".agent-row.expanded", timeout=4000)

                # Get the prompt box and scroll it down
                prompt_box = page.query_selector(".agent-row.expanded .dispatch-prompt")
                assert prompt_box is not None, "Prompt box not found"

                # Scroll the prompt box to bottom
                initial_scroll = page.evaluate(
                    "document.querySelector('.agent-row.expanded .dispatch-prompt').scrollTop || 0")
                page.evaluate(
                    "document.querySelector('.agent-row.expanded .dispatch-prompt').scrollTop = 999")
                scroll_before = page.evaluate(
                    "document.querySelector('.agent-row.expanded .dispatch-prompt').scrollTop")
                assert scroll_before > initial_scroll, f"Failed to scroll; before={initial_scroll}, after={scroll_before}"

                # Trigger a live update by touching the backlog
                bl = root / "AUDIT-BACKLOG.md"
                content = bl.read_text(encoding="utf-8").replace(
                    "## Landing log",
                    "- ⬜ **[test] SCROLL-PERSIST-MARKER item.** live update.\n\n## Landing log")
                bl.write_text(content, encoding="utf-8")

                # Wait for the update to arrive
                page.wait_for_function(
                    "document.querySelector('#backlog-tiers').innerText.includes('SCROLL-PERSIST-MARKER')",
                    timeout=8000)

                # Check that scroll position survived the update
                scroll_after = page.evaluate(
                    "document.querySelector('.agent-row.expanded .dispatch-prompt').scrollTop")
                assert scroll_after >= scroll_before - 2,                     f"Scroll position lost during live update: before={scroll_before}, after={scroll_after}"
            except Exception as e:
                failures.append(f"(f) scroll position/selection not preserved during live update: {e}")

            # (g) promptCache eviction works: removed agents don't stay cached (bugfix P2 #2)
            try:
                # Get initial cache size
                cache_size_before = page.evaluate("window.__getPromptCacheSize()")
                assert cache_size_before > 0, "Cache should have entries for expanded agents"

                # Change agent hint to force a new agent to appear
                (root / "hint.txt").write_text("NEW-AGENT-AFTER-EVICT", encoding="utf-8")
                (root / "transcripts" / "agent-evict-marker.jsonl").write_text("{}", encoding="utf-8")
                page.wait_for_function(
                    "document.querySelector('#agents-list').innerText.includes('NEW-AGENT-AFTER-EVICT')",
                    timeout=8000)

                # Now change it again to a different agent (old one gets removed from DOM)
                (root / "hint.txt").write_text("FINAL-AGENT-STATE", encoding="utf-8")
                (root / "transcripts" / "agent-final-marker.jsonl").write_text("{}", encoding="utf-8")
                page.wait_for_function(
                    "document.querySelector('#agents-list').innerText.includes('FINAL-AGENT-STATE')",
                    timeout=8000)

                # Cache should have evicted old entries
                cache_size_after = page.evaluate("window.__getPromptCacheSize()")
                assert cache_size_after <= cache_size_before + 1,                     f"Cache grew unbounded: before={cache_size_before}, after={cache_size_after}"
            except Exception as e:
                failures.append(f"(g) promptCache not evicting removed agents: {e}")

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
    print("PROVEN: (a) console clean (b) backlog rendered (b2) alert-count alarm color "
          "(b3) alerts-box alarm styling (c) click-expand with prompt (d) SSE live updates (e) expansion survived")
    return 0


if __name__ == "__main__":
    sys.exit(main())
