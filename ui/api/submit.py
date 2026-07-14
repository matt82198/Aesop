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

Detects both POSIX symlinks and Windows junctions/reparse points.
"""
import os
import stat
from datetime import datetime

import config


def _is_link_or_reparse(path):
    """Check if path is a symlink or Windows reparse point (junction/etc).

    Returns True if:
    - On all platforms: path is a POSIX symlink (detected via st_mode)
    - On Windows: path has the FILE_ATTRIBUTE_REPARSE_POINT attribute
      (which includes junctions, symlinks, and other reparse points)

    Uses os.lstat() to detect without following links (includes dangling ones).
    On error (e.g., path doesn't exist), returns False to let caller's
    exists() check handle it normally.
    """
    try:
        stat_result = os.lstat(str(path))

        # On POSIX, check the symlink bit in st_mode
        if stat.S_ISLNK(stat_result.st_mode):
            return True

        # On Windows, check for reparse point attribute (junctions, symlinks, etc)
        # FILE_ATTRIBUTE_REPARSE_POINT = 0x400 (1024 decimal)
        # st_file_attributes only exists on Windows
        if hasattr(stat_result, 'st_file_attributes'):
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            if stat_result.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                return True

        return False
    except (OSError, AttributeError):
        # If we can't stat it, let it fall through to the exists() check
        # (file doesn't exist, which is fine)
        return False


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

    # Security: reject symlinks and Windows junctions (TOCTOU defense) FIRST —
    # check link/reparse INDEPENDENT of exists(). Path.exists() follows the link,
    # so a DANGLING symlink (target not yet created) returns False and would
    # otherwise skip this check, then open(...,'w') would follow the link and
    # create the attacker's target. Windows junctions are not detected by
    # os.path.islink(), so we use _is_link_or_reparse() instead.
    if _is_link_or_reparse(config.INBOX_FILE):
        return False, (400, {"error": "Inbox file is a symlink (rejected for security)"})

    if not config.INBOX_FILE.exists():
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
