"""Extract NEW fleet spawn prompts (Agent/Task) for review cycle with deduplication."""
import argparse
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timedelta


def walk_jsonl(directory):
    """Recursively find all .jsonl files in a directory."""
    result = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".jsonl"):
                result.append(os.path.join(root, f))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract new fleet spawn prompts (Agent/Task) for review, with dedup by SHA1."
    )
    parser.add_argument(
        "roots", nargs="+", help="Root directories containing .jsonl transcripts to scan"
    )
    parser.add_argument(
        "-s", "--seen-file", required=True, help="Path to seen-set JSON file for dedup (will be created/updated)"
    )
    parser.add_argument(
        "-m", "--minutes", type=int, default=30, help="Look back this many minutes (default 30)"
    )
    parser.add_argument(
        "-x", "--exclude-session", help="Exclude transcripts from this session ID substring"
    )
    parser.add_argument(
        "--max", type=int, default=20, help="Cap prompts per review cycle (default 20)"
    )

    args = parser.parse_args()

    # Load seen set
    seen_set = set()
    if os.path.exists(args.seen_file):
        try:
            with open(args.seen_file, "r", encoding="utf-8") as f:
                seen_set = set(json.load(f))
        except Exception:
            pass

    # Gather .jsonl files
    files = []
    for root in args.roots:
        if os.path.exists(root):
            files.extend(walk_jsonl(root))

    # Time filter
    since_ms = (datetime.now() - timedelta(minutes=args.minutes)).timestamp() * 1000

    out = []
    for fp in files:
        # Session exclusion
        if args.exclude_session and args.exclude_session in fp:
            continue

        try:
            st = os.stat(fp)
            if st.st_mtime_ns / 1e6 < since_ms:
                continue
        except Exception:
            continue

        try:
            with open(fp, "r", encoding="utf-8") as f:
                lines = f.read().split("\n")
        except Exception:
            continue

        base = os.path.basename(fp)
        for line in lines:
            if not line.strip() or ('"Agent"' not in line and '"Task"' not in line):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            content = obj.get("message", {}).get("content")
            if not isinstance(content, list):
                continue

            for c in content:
                if c.get("type") != "tool_use" or c.get("name") not in ["Agent", "Task"]:
                    continue

                prompt = (c.get("input", {}).get("prompt") or c.get("input", {}).get("description") or "").strip()
                if len(prompt) < 8:
                    continue

                key = hashlib.sha1(prompt.encode()).hexdigest()[:16]
                if key in seen_set:
                    continue

                seen_set.add(key)
                out.append(
                    {
                        "key": key,
                        "src": base,
                        "label": (c.get("input", {}).get("description") or "")[:80],
                        "prompt": prompt[:700],
                    }
                )

                if len(out) >= args.max:
                    break

            if len(out) >= args.max:
                break

        if len(out) >= args.max:
            break

    # Write updated seen set
    pathlib.Path(args.seen_file).parent.mkdir(parents=True, exist_ok=True)
    with open(args.seen_file, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_set)), f)

    # Output to stdout as JSON
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
