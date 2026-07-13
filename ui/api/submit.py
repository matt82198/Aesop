#!/usr/bin/env python3
"""
Aesop UI API — inbox-submit logic (wave-10 P0 split from handler.py).

Free function: given already-validated, non-empty text, append it to the UI
inbox file. UTF-8/LF-safe (matches the encoding used to read the file back
elsewhere) and guarded against a symlinked inbox file (TOCTOU defense --
reject rather than follow a symlink another local user/process may have
planted at config.INBOX_FILE).

Reads config.INBOX_FILE live via `import config` at call time, never
`from config import INBOX_FILE` -- a frozen import goes stale after
config.reload() (breaks test-fixture isolation). See ui/CLAUDE.md.
"""
import os
from datetime import datetime

import config


def append_to_inbox(text):
    """Append one inbox line for `text` to config.INBOX_FILE.

    Creates the file (with a header comment) if it doesn't exist yet.

    Args:
        text: non-empty, already-stripped text to record (caller is
            responsible for validating it's non-empty -- this function does
            not re-check).

    Returns:
        (True, None) on success.
        (False, (400, {"error": "..."})) if config.INBOX_FILE exists and is
            a symlink (rejected for security).
    """
    inbox_content = f"- [{datetime.now().isoformat()}] {text}\n"

    if config.INBOX_FILE.exists():
        # Security: reject symlinks (TOCTOU defense)
        if os.path.islink(str(config.INBOX_FILE)):
            return False, (400, {"error": "Inbox file is a symlink (rejected for security)"})
    else:
        config.INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Must match the encoding (utf-8) AND newline convention (LF) of the
        # append below -- text-mode write_text() with no encoding= falls back
        # to the locale-preferred encoding (cp1252 on Windows), which mangles
        # non-ASCII bytes like the em-dash and leaves the file as a whole not
        # valid UTF-8 for anything that reads it with encoding="utf-8".
        with open(config.INBOX_FILE, 'w', encoding='utf-8', newline='\n') as f:
            f.write("# UI Inbox — orchestrator reads each turn / on /power\n\n")

    with open(config.INBOX_FILE, 'a', encoding='utf-8') as f:
        f.write(inbox_content)

    return True, None
