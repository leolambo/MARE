#!/usr/bin/env python3
"""
pinterest_sync.py — Sync a Pinterest board to a flat local directory.

Uses gallery-dl's --download-archive (SQLite) to track downloaded pins and
skip duplicates on subsequent runs. New pins only, always flat output.

Usage:
    python3 pinterest_sync.py <board_url> --output <dir>
    python3 pinterest_sync.py <board_url> --output <dir> --dry-run

Examples:
    python3 pinterest_sync.py https://pin.it/4OiKPkpRf \
        --output ~/base/creative/MAREv2/reference/wear
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync a Pinterest board to a flat local directory (new pins only)."
    )
    parser.add_argument("url", help="Pinterest board URL or short link")
    parser.add_argument(
        "--output", "-o", required=True,
        help="Target directory (flat — all images land here directly)"
    )
    parser.add_argument(
        "--archive",
        help="Archive file for dedup tracking (default: <output>/.pinterest-archive.txt)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without saving"
    )
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    archive_file = args.archive or str(out_dir / ".pinterest-archive.txt")

    log(f"Board   : {args.url}")
    log(f"Output  : {out_dir}")
    log(f"Archive : {archive_file}")
    if args.dry_run:
        log("Mode    : DRY RUN — nothing will be saved")

    # Count files before
    before = set(f.name for f in out_dir.iterdir() if f.is_file() and not f.name.startswith("."))

    cmd = [
        "gallery-dl",
        "--download-archive", archive_file,
        "-d", str(out_dir),
        "-o", "directory=[]",           # flat output — no subdirectories
        "--no-part",                     # no partial files left behind
    ]
    if args.dry_run:
        cmd.append("--simulate")
    cmd.append(args.url)

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Count new files
    after = set(f.name for f in out_dir.iterdir() if f.is_file() and not f.name.startswith("."))
    new_files = sorted(after - before)

    if args.dry_run:
        # In dry-run, parse stdout for what would have downloaded
        would_download = [l.strip() for l in result.stdout.splitlines() if l.strip() and not l.startswith("#")]
        log(f"Dry run complete. Would download: {len(would_download)} new image(s).")
        for f in would_download:
            print(f"  ~ {Path(f).name}")
    elif new_files:
        log(f"Done. {len(new_files)} new image(s) downloaded:")
        for f in new_files:
            print(f"  + {f}")
    else:
        log("Done. No new images — board is up to date.")

    if result.returncode not in (0, 1) and result.stderr:
        log("gallery-dl errors:")
        print(result.stderr, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
