#!/usr/bin/env python3
"""
secret_scan.py — Pre-push secret/credential detection gate.

Modes:
  secret_scan.py --staged [--repo PATH]              Scan git staged files (default repo=cwd)
  secret_scan.py --range COMMIT_RANGE [--repo PATH]  Scan files changed in range (e.g., main..HEAD or abc123..def456)
  secret_scan.py --history [--repo PATH]             Scan all blobs in git history
  secret_scan.py PATH [PATH...]                      Scan files/dirs directly (recurse dirs)

Exit codes: 0=clean, 1=findings, 2=usage error
Output: one line per finding or summary (never prints full secrets)

Pragma escape hatch (STRICTLY SCOPED to doc-shaped rules):
  If the literal string 'secretscan: allow-pattern-docs' appears in a file's first 10 lines
  (any comment syntax: #, //, <!-- -->), findings from the two DOC-SHAPED rules ONLY
  (generic_secret_assignment, env_access) are reported as ALLOWED-DOC and do not cause
  exit 1. Fatal classes (PEM private keys, AWS/GitHub/Slack/OpenAI-Anthropic tokens,
  connection strings) and filename-based findings stay fatal REGARDLESS of the pragma.
  The pragma appears in git diffs and is a reviewable act.

Self-scan invariant: this file must scan CLEAN with NO pragma. Any pattern literal that
would match its own regex is runtime-assembled from fragments (see pem_private_key) so
the pattern text never appears contiguously in this source.

Scan contract (wave-25 P2 fix): --staged and --range scan committed GIT OBJECTS, not the
working-tree copy of changed files. --staged reads each path's STAGED INDEX blob
(`git show :<path>`); --range reads each changed path's blob at the TIP of the range
(`git show <tip>:<path>`). This closes two bypasses that existed when these modes read
$repo/<path> off disk: (1) stage a secret, then edit the on-disk file without
re-staging -- the dirty blob is still what gets committed/pushed; (2) commit a secret,
then edit it away in the worktree without a new commit -- the dirty blob is still what
the pushed commit carries. --history is unaffected (it already walks committed diffs).
Any git command needed to enumerate the files-to-scan that itself fails (bad ref,
unresolvable range, git error) is NOT treated as "zero files changed" -- it raises
GitScanError and the caller fails CLOSED (non-zero exit), so an unresolvable range can
never silently report CLEAN.

NOTE: Public repo version has NO vault allowlist.
"""

import argparse
import os
import re
import sys
import subprocess
from pathlib import Path


# Regex patterns for secret detection (case-insensitive where sensible)
# NOTE: pem_private_key is runtime-assembled from fragments so this source file
# never contains a contiguous PEM-header shape (self-scan invariant, no pragma).
PATTERNS = {
    "pem_private_key": (r"-----BEGIN .* " + "PRIVATE" + " KEY-----", re.IGNORECASE),
    "aws_access_key": (r"AKIA[0-9A-Z]{16}", 0),
    "aws_secret_pattern": (
        r"aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*[^\s\$\<\{]",
        re.IGNORECASE,
    ),
    "github_token": (
        r"(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}",
        0,
    ),
    "slack_token": (r"xox[baprs]-[A-Za-z0-9-]{10,}", 0),
    "openai_anthropic_key": (r"sk-[A-Za-z0-9_\-]{20,}", 0),
    "generic_secret_assignment": (
        # Unquoted branch requires 8+ contiguous chars from a bare-literal charset
        # (no '.', '(', ')' — real code expressions like `secrets.token_urlsafe(32)`,
        # `self.serve.SESSION_TOKEN`, or `headers.get(...)` all contain one of those)
        # followed by whitespace/EOL, so an assignment from a variable/attribute/call
        # doesn't false-positive as a hardcoded secret the way a bare env-file value
        # (`API_TOKEN=verylongtokenvalue123456789`) legitimately does.
        r"\b(password|passwd|secret|api[_-]?key|token|authorization)\b\s*(?::=|=)\s*(?:[\"'](?!.*(?:xxx|changeme|your-|<|$\{|example)\b).{8,}[\"']|(?!['\"]|xxx|changeme|your-|example)[^\s\$\<\{\n\(\)\.\"']{8,}(?=\s|$))",
        re.IGNORECASE,
    ),
    "connection_string": (
        (r"://"
         r"[^:]+:[^@/\s]+@"
         r"(?!"
            r"localhost(?:[:/]|$)|"
            r"127\.0\.0\.1(?:[:/]|$)|"
            r"127\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[:/]|$)|"
            r"[a-zA-Z0-9.-]*\.local(?:[:/]|$)|"
            r"[a-zA-Z0-9.-]*\.localdomain(?:[:/]|$)|"
            r"(?:[a-zA-Z0-9-]+\.)*example(?:\.[a-zA-Z]{2,})?(?:[:/]|$)|"
            r"(?:[a-zA-Z0-9-]+\.)*test(?:\.[a-zA-Z]{2,})?(?:[:/]|$)"
         r")"
         r"[^\s]+"),
        0
    ),
    "env_access": (
        r"(?i:(?:os\.getenv|os\.environ|System\.getenv|process\.env)\s*[\[\(][\"']?[A-Z_]*(?:password|secret|api[_-]?key|token|auth|key)[A-Z_0-9]*[\"']?[\)\]])",
        0,
    ),
    "env_assignment": (
        r"(?i:[A-Z_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE|CREDENTIAL|AUTH)[A-Z_0-9]*\s*=\s*)(?!.*(?:xxx|changeme|your-|example))[^\s].{8,}",
        0,
    ),
}

# File patterns that look like credentials (case-insensitive)
CREDENTIAL_FILENAMES = [
    r"\.credentials.*",
    r".*token.*",
    r".*\.pem$",
    r".*\.p12$",
    r"id_rsa.*",
]

# Placeholders that don't count as secrets
PLACEHOLDERS = {"xxx", "changeme", "your-key-here", "example", "test", "demo"}

# Rules that CAN be softened by pragma (doc-shaped rules only)
SOFTENED_BY_PRAGMA = {"generic_secret_assignment", "env_access"}

# Rules that are ALWAYS fatal, pragma never applies
FATAL_RULES = {
    "pem_private_key",
    "aws_access_key",
    "github_token",
    "slack_token",
    "openai_anthropic_key",
    "connection_string",
}


def _classify_finding(rule_name, has_file_pragma):
    """Shared fatal/softened decision, used by every scan_* variant (disk-file,
    blob, large-file-chunked) so the pragma contract can't drift between them.
    FATAL_RULES are always fatal. SOFTENED_BY_PRAGMA rules are fatal unless the
    pragma is present. Everything else (e.g. env_assignment) is always fatal."""
    if rule_name in FATAL_RULES:
        return True
    if rule_name in SOFTENED_BY_PRAGMA:
        return not has_file_pragma
    return True


class GitScanError(Exception):
    """Raised when a git command needed to enumerate files-to-scan fails.
    Callers MUST treat this as fail-CLOSED (block / exit non-zero) -- it is
    NOT equivalent to "the range/index genuinely contains zero changed
    files" (wave-25 P2 fix: get_range_files previously returned [] on ANY
    git-diff error, indistinguishable from a real empty range, so main()
    printed CLEAN and exited 0 on an unresolvable range)."""


def has_pragma(filepath):
    """Check if file has 'secretscan: allow-pattern-docs' pragma in first 10 lines."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= 10:  # Only check first 10 lines
                    break
                if "secretscan: allow-pattern-docs" in line:
                    return True
    except Exception:
        pass
    return False


def is_binary_file(filepath):
    """Check if file is binary (contains null bytes in first 8KB)."""
    try:
        with open(filepath, "rb") as f:
            return b"\x00" in f.read(8192)
    except Exception:
        return True


def should_skip_file(filepath):
    """Check if file should be skipped entirely (.git/, node_modules/, __pycache__, .pyc, .pyo)."""
    # Skip .git directories — match a path COMPONENT, not a substring
    # (".git" in str(path) also matched ".gitignore" and skipped scanning it).
    if ".git" in filepath.parts:
        return True

    # Skip node_modules — third-party deps, always git-ignored, never our code.
    # CI installs them via `npm ci` for the dashboard build, so a whole-tree
    # scan would otherwise walk thousands of package files (README example
    # connection strings, files literally named token.js → false positives).
    if "node_modules" in filepath.parts:
        return True

    # Skip __pycache__ directories
    if "__pycache__" in filepath.parts:
        return True

    # Skip compiled Python artifacts
    if filepath.name.endswith(".pyc") or filepath.name.endswith(".pyo"):
        return True

    return False


def is_placeholder(value):
    """Check if a string is a placeholder value (word-boundary aware)."""
    lower_val = value.lower()
    for p in PLACEHOLDERS:
        if re.search(r'\b' + re.escape(p) + r'\b(?!\.)', lower_val):
            return True
    # Also check for template syntax
    return bool(re.search(r"<[^>]*>|\$\{[^}]*\}", value))


def mask_secret(secret_str):
    """Mask secret: show first 4 chars + *** (or *** if <4 chars)."""
    if len(secret_str) <= 4:
        return "***"
    return f"{secret_str[:4]}***"


def is_env_file(filepath):
    r"""Check if file is .env-like (basename matches ^\.env(\..*)?$ or *.env or *.properties)."""
    name = filepath.name.lower()
    return bool(
        re.match(r"^\.env(\..*)?$", name) or
        name.endswith(".env") or
        name.endswith(".properties")
    )


def scan_file(filepath):
    """
    Scan a single file for secrets.
    Returns list of (line_num, rule, match_str, is_fatal).
    is_fatal=True for credential filenames and fatal rule categories;
    is_fatal=False only if pragma present AND rule is in SOFTENED_BY_PRAGMA.

    Large files (>1MB) and binary files are scanned for FATAL_RULES patterns:
    - Large files: scan first 1MB; emit SKIPPED-LARGE to stderr if file is larger
    - Binary files: decode as latin-1; emit SKIPPED-BINARY to stderr if not fully scanned
    """
    SIZE_THRESHOLD = 1024 * 1024  # 1MB
    MAX_READ_SIZE = 2 * 1024 * 1024  # 2MB max to read

    findings = []

    if should_skip_file(filepath):
        return findings

    # Check for pragma (applies only to specific rule-based findings, not filename findings)
    has_file_pragma = has_pragma(filepath)

    # Check if filename matches credential patterns (always fatal, pragma does NOT apply)
    filename = filepath.name.lower()
    for pattern in CREDENTIAL_FILENAMES:
        if re.match(pattern, filename, re.IGNORECASE):
            findings.append(
                (0, "credential_filename", f"File name matches credential pattern: {filepath.name}", True)
            )
            break

    try:
        # Check file size and binary status
        stat = filepath.stat()
        file_size = stat.st_size
        is_binary = is_binary_file(filepath)
        is_large = file_size > SIZE_THRESHOLD

        if is_binary:
            # Binary file (any size): scan as-is for FATAL_RULES only
            with open(filepath, "rb") as f:
                content = f.read(MAX_READ_SIZE)

            # Decode as latin-1 (preserves all bytes)
            try:
                content_str = content.decode("latin-1")
            except Exception:
                content_str = content.decode("utf-8", errors="ignore")

            # Emit skip notice to stderr
            print(f"SKIPPED-BINARY {filepath} (scanned via latin-1)", file=sys.stderr)

            # Scan content for FATAL_RULES only
            for line_num, line in enumerate(content_str.split("\n"), start=1):
                for rule_name in FATAL_RULES:
                    if rule_name not in PATTERNS:
                        continue
                    pattern, flags = PATTERNS[rule_name]
                    matches = re.finditer(pattern, line, flags)
                    for match in matches:
                        match_str = match.group(0)
                        if is_placeholder(match_str):
                            continue
                        findings.append((line_num, rule_name, match_str, True))

        elif is_large:
            # Large text file: scan entire file in chunks for all rules
            print(f"SKIPPED-LARGE {filepath} (scanned in chunks)", file=sys.stderr)
            line_num = 0
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    # Read in 1MB chunks to avoid loading entire large file into memory
                    for chunk in iter(lambda: f.read(1024 * 1024), ""):
                        for chunk_line in chunk.split("\n"):
                            line_num += 1
                            for rule_name, (pattern, flags) in PATTERNS.items():
                                # Skip env_assignment rule if not an .env-like file
                                if rule_name == "env_assignment" and not is_env_file(filepath):
                                    continue

                                matches = re.finditer(pattern, chunk_line, flags)
                                for match in matches:
                                    match_str = match.group(0)

                                    # Skip if it's a placeholder
                                    if is_placeholder(match_str):
                                        continue

                                    is_fatal = _classify_finding(rule_name, has_file_pragma)
                                    findings.append((line_num, rule_name, match_str, is_fatal))
            except (IOError, OSError) as e:
                # FAIL CLOSED: if we cannot fully scan a large text file, exit with error
                print(f"FATAL: Cannot fully scan large text file {filepath}: {e}", file=sys.stderr)
                sys.exit(1)

        else:
            # Normal small text file: scan all rules
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, start=1):
                    for rule_name, (pattern, flags) in PATTERNS.items():
                        # Skip env_assignment rule if not an .env-like file
                        if rule_name == "env_assignment" and not is_env_file(filepath):
                            continue

                        matches = re.finditer(pattern, line, flags)
                        for match in matches:
                            match_str = match.group(0)

                            # Skip if it's a placeholder
                            if is_placeholder(match_str):
                                continue

                            is_fatal = _classify_finding(rule_name, has_file_pragma)
                            findings.append((line_num, rule_name, match_str, is_fatal))

    except Exception:
        pass

    return findings


def scan_blob(label, content_bytes):
    """
    Scan raw blob bytes for secrets, reporting findings against `label` as the
    display path. Mirrors scan_file()'s rule/fatality logic, but reads content
    already fetched from a git object (via get_git_blob) instead of opening the
    working-tree disk file. Used by --staged (the STAGED INDEX blob) and
    --range (the blob at the TIP of the range) so a secret present only in the
    git object being pushed -- but absent from an out-of-sync working copy --
    is not missed (wave-25 P2 fix; see module docstring "Scan contract").

    Returns list of (line_num, rule, match_str, is_fatal), like scan_file().
    """
    filepath = Path(label)
    SIZE_THRESHOLD = 1024 * 1024  # 1MB
    MAX_READ_SIZE = 2 * 1024 * 1024  # 2MB max to read (matches scan_file's binary cap)

    findings = []

    if should_skip_file(filepath):
        return findings

    filename = filepath.name.lower()
    for pattern in CREDENTIAL_FILENAMES:
        if re.match(pattern, filename, re.IGNORECASE):
            findings.append(
                (0, "credential_filename", f"File name matches credential pattern: {filepath.name}", True)
            )
            break

    # Pragma check over the first 10 lines, mirroring has_pragma() but reading
    # from the in-memory blob instead of opening a path from disk.
    has_file_pragma = False
    try:
        probe = content_bytes.decode("utf-8", errors="ignore")
        for i, line in enumerate(probe.split("\n")):
            if i >= 10:
                break
            if "secretscan: allow-pattern-docs" in line:
                has_file_pragma = True
                break
    except Exception:
        pass

    is_binary = b"\x00" in content_bytes[:8192]
    is_large = len(content_bytes) > SIZE_THRESHOLD

    if is_binary:
        raw = content_bytes[:MAX_READ_SIZE]
        try:
            content_str = raw.decode("latin-1")
        except Exception:
            content_str = raw.decode("utf-8", errors="ignore")

        print(f"SKIPPED-BINARY {filepath} (scanned via latin-1)", file=sys.stderr)

        for line_num, line in enumerate(content_str.split("\n"), start=1):
            for rule_name in FATAL_RULES:
                pattern, flags = PATTERNS[rule_name]
                for match in re.finditer(pattern, line, flags):
                    match_str = match.group(0)
                    if is_placeholder(match_str):
                        continue
                    findings.append((line_num, rule_name, match_str, True))
        return findings

    if is_large:
        print(f"SKIPPED-LARGE {filepath} (scanned in full from git object)", file=sys.stderr)

    try:
        content_str = content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        content_str = content_bytes.decode("latin-1", errors="ignore")

    env_file = is_env_file(filepath)
    for line_num, line in enumerate(content_str.split("\n"), start=1):
        for rule_name, (pattern, flags) in PATTERNS.items():
            if rule_name == "env_assignment" and not env_file:
                continue

            for match in re.finditer(pattern, line, flags):
                match_str = match.group(0)
                if is_placeholder(match_str):
                    continue
                is_fatal = _classify_finding(rule_name, has_file_pragma)
                findings.append((line_num, rule_name, match_str, is_fatal))

    return findings


def _range_tip_ref(commit_range):
    """Extract the right-hand (tip) ref from a two-dot or three-dot commit
    range string, e.g. 'main..HEAD' -> 'HEAD', 'a...b' -> 'b'. Falls back to
    the whole string if it isn't a recognizable range (single ref/sha)."""
    if "..." in commit_range:
        tip = commit_range.split("...", 1)[1]
    elif ".." in commit_range:
        tip = commit_range.split("..", 1)[1]
    else:
        tip = commit_range
    return tip or "HEAD"


def get_git_blob(repo_path, ref_path):
    """Fetch raw blob bytes via `git show <ref_path>` -- e.g. ref_path=':foo.py'
    reads foo.py from the STAGED INDEX, 'abc123:foo.py' reads foo.py as it
    exists in commit abc123. Returns None if the object cannot be read (e.g.
    the path was deleted at that ref) -- that is NOT a git-command failure,
    just nothing left to scan there.
    """
    try:
        result = subprocess.run(
            ["git", "show", ref_path],
            cwd=repo_path,
            capture_output=True,
            timeout=15,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def get_staged_files(repo_path):
    """Get list of staged file paths (relative to repo root) from git repo.

    Raises GitScanError if the underlying `git diff --cached` invocation
    fails; callers must fail CLOSED on that, not treat it as "nothing staged".
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=d"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        raise GitScanError(f"git diff --cached raised {e!r}")

    if result.returncode != 0:
        raise GitScanError(
            f"git diff --cached failed (rc={result.returncode}): {result.stderr.strip()}"
        )

    return [f for f in result.stdout.strip().split("\n") if f.strip()]


def get_range_files(repo_path, commit_range):
    """Get list of file paths (relative to repo root) changed in commit range
    (e.g. 'main..HEAD' or 'abc123..def456').

    Raises GitScanError if the underlying `git diff` invocation fails (e.g.
    an unresolvable ref); callers must fail CLOSED on that -- it is not the
    same as a range that genuinely touches zero files.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", commit_range],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        raise GitScanError(f"git diff --name-only {commit_range!r} raised {e!r}")

    if result.returncode != 0:
        raise GitScanError(
            f"git diff --name-only {commit_range!r} failed (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )

    return [f for f in result.stdout.strip().split("\n") if f.strip()]


def get_history_files(repo_path):
    """Get all file contents from git history via git log -p."""
    files_content = []
    try:
        # Use git log -p to get full diff history
        result = subprocess.run(
            ["git", "log", "--all", "-p", "--reverse"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            # Parse the git log output: each file appears as +++ b/path/to/file followed by its content
            current_file = None
            current_content = []
            for line in result.stdout.split("\n"):
                if line.startswith("+++ b/"):
                    if current_file and current_content:
                        files_content.append((current_file, "\n".join(current_content)))
                    current_file = line[6:]  # Remove "+++ b/"
                    current_content = []
                elif current_file and line.startswith("+") and not line.startswith("+++"):
                    # Content line (added), strip the leading +
                    current_content.append(line[1:])
                elif current_file and line.startswith(" "):
                    # Context line, keep it as-is (strip leading space)
                    current_content.append(line[1:])
            if current_file and current_content:
                files_content.append((current_file, "\n".join(current_content)))
    except Exception:
        pass
    return files_content


def scan_paths(paths):
    """Recursively scan paths (files and directories)."""
    files_to_scan = []
    for path_str in paths:
        path = Path(path_str).resolve()
        if path.is_file():
            files_to_scan.append(path)
        elif path.is_dir():
            files_to_scan.extend(path.rglob("*"))
    return [p for p in files_to_scan if p.is_file()]


def scan_content(content):
    """Scan raw content for secrets (used by history scanning)."""
    findings = []
    for line_num, line in enumerate(content.split("\n"), start=1):
        for rule_name, (pattern, flags) in PATTERNS.items():
            matches = re.finditer(pattern, line, flags)
            for match in matches:
                match_str = match.group(0)
                if is_placeholder(match_str):
                    continue
                findings.append((line_num, rule_name, match_str, True))
    return findings


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan git staged files (requires --repo or uses cwd)",
    )
    parser.add_argument(
        "--range",
        metavar="COMMIT_RANGE",
        help="Scan files changed in commit range (e.g., 'main..HEAD' or 'abc123..def456')",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Scan all blobs in git history (requires --repo or uses cwd)",
    )
    parser.add_argument(
        "--repo",
        default=os.getcwd(),
        help="Git repo path (default: current directory)",
    )
    parser.add_argument(
        "paths", nargs="*", help="Paths to scan directly (files or directories)"
    )

    args = parser.parse_args()

    # Validate usage: exactly one of --staged, --range, --history, or paths
    mode_count = sum([args.staged, bool(args.range), args.history, bool(args.paths)])
    if mode_count != 1:
        print("ERROR: Use exactly one of --staged, --range, --history, or path arguments", file=sys.stderr)
        sys.exit(2)

    all_findings = []
    fatal_findings = []
    allowed_doc_count = 0
    file_count = 0

    if args.staged:
        # Scan the STAGED INDEX blob for each changed path, NOT the working-tree
        # copy -- a worktree edit made after `git add` must not be able to hide
        # a secret still sitting in the index that would actually get committed.
        try:
            relpaths = get_staged_files(args.repo)
        except GitScanError as e:
            print(f"FATAL: could not determine staged files: {e}", file=sys.stderr)
            print("Failing CLOSED: refusing to report CLEAN when the staged-file listing could not be determined.", file=sys.stderr)
            sys.exit(1)

        file_count = len(relpaths)
        for relpath in relpaths:
            content = get_git_blob(args.repo, f":{relpath}")
            if content is None:
                continue  # deleted/unreadable object -- nothing to scan
            label = str(Path(args.repo) / relpath)
            findings = scan_blob(label, content)
            for line_num, rule, match_str, is_fatal in findings:
                all_findings.append((label, line_num, rule, match_str, is_fatal))
                if is_fatal:
                    fatal_findings.append((label, line_num, rule, match_str))
                else:
                    allowed_doc_count += 1

    elif args.range:
        # Scan the COMMITTED blob at the TIP of the range for each changed
        # path, NOT the working-tree copy -- a secret committed then edited
        # away in the worktree (without a new commit) must still be caught,
        # since the pushed commit still carries the dirty blob.
        try:
            relpaths = get_range_files(args.repo, args.range)
        except GitScanError as e:
            print(f"FATAL: could not resolve commit range {args.range!r}: {e}", file=sys.stderr)
            print("Failing CLOSED: refusing to report CLEAN on an unresolvable range.", file=sys.stderr)
            sys.exit(1)

        file_count = len(relpaths)
        tip_ref = _range_tip_ref(args.range)
        for relpath in relpaths:
            content = get_git_blob(args.repo, f"{tip_ref}:{relpath}")
            if content is None:
                continue  # deleted at tip -- nothing to scan
            label = str(Path(args.repo) / relpath)
            findings = scan_blob(label, content)
            for line_num, rule, match_str, is_fatal in findings:
                all_findings.append((label, line_num, rule, match_str, is_fatal))
                if is_fatal:
                    fatal_findings.append((label, line_num, rule, match_str))
                else:
                    allowed_doc_count += 1

    elif args.history:
        # History scanning mode: unaffected by the blob-scan fix above, since
        # it already walks committed diff content via `git log -p`.
        history_files = get_history_files(args.repo)
        file_count = len(set(f for f, _ in history_files))
        for filepath, content in history_files:
            findings = scan_content(content)
            for line_num, rule, match_str, is_fatal in findings:
                all_findings.append((filepath, line_num, rule, match_str, is_fatal))
                if is_fatal:
                    fatal_findings.append((filepath, line_num, rule, match_str))

    else:
        files = scan_paths(args.paths)
        file_count = len(files)
        for filepath in files:
            findings = scan_file(filepath)
            for line_num, rule, match_str, is_fatal in findings:
                all_findings.append((filepath, line_num, rule, match_str, is_fatal))
                if is_fatal:
                    fatal_findings.append((filepath, line_num, rule, match_str))
                else:
                    allowed_doc_count += 1

    # Output findings
    for filepath, line_num, rule, match_str, is_fatal in all_findings:
        masked = mask_secret(match_str)
        if is_fatal:
            print(f"HIGH {filepath}:{line_num} {rule} ({masked})")
        else:
            print(f"ALLOWED-DOC {filepath}:{line_num} {rule} ({masked})")

    # Summary and exit
    if len(fatal_findings) == 0:
        if allowed_doc_count == 0:
            if args.history:
                print(f"CLEAN: git history scanned")
            else:
                print(f"CLEAN: {file_count} files scanned")
        else:
            pragma_file_count = len(set(f for f, _, _, _, is_fatal in all_findings if not is_fatal))
            print(f"CLEAN: scanned ({allowed_doc_count} allowed-doc findings in {pragma_file_count} pragma files)")
        sys.exit(0)
    else:
        print(f"FOUND: {len(fatal_findings)} secret(s)")
        sys.exit(1)


if __name__ == "__main__":
    main()
