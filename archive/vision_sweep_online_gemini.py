#!/usr/bin/env python3
"""
MARE Online Archive — Gemini Pass
Runs Gemini 2.5 Flash detail pass on high-relevance entries from the online archive.

State file: ~/workspace/creative/MARE ONLINE ARCHIVE/dss/crawl/vision_state_online.json
Paths in state file are ABSOLUTE (full filesystem paths).

Usage:
    python3 vision_sweep_online_gemini.py [--dry-run] [--limit N] [--status]
"""

import argparse
import base64
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
CRAWL_DIR   = Path.home() / ".openclaw/workspace/creative/MARE ONLINE ARCHIVE/dss/crawl"
STATE_FILE  = CRAWL_DIR / "vision_state_online.json"
LOG_FILE    = CRAWL_DIR / "vision_gemini_online.log"
LOCK_FILE   = CRAWL_DIR / "vision_gemini_online.lock"
OPENCLAW_CONFIG = Path.home() / ".openclaw/openclaw.json"

# ── Gemini config ──────────────────────────────────────────────────────────────
GEMINI_MODEL    = "gemini-2.5-flash"
DAILY_LIMIT     = 9_500          # paid tier
DELAY_SECS      = 2.0            # between requests
REQUEST_TIMEOUT = 30             # seconds

# ── Get API key from OpenClaw config ──────────────────────────────────────────
def _get_api_key() -> str:
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        return env_key
    try:
        config = json.loads(OPENCLAW_CONFIG.read_text())
        return config["skills"]["entries"]["nano-banana-pro"]["apiKey"]
    except Exception as e:
        print(f"Error: Could not get Gemini API key: {e}", file=sys.stderr)
        sys.exit(1)

API_KEY  = ""  # set in main()
GEMINI_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={key}"
)

CATEGORIZATION_PROMPT = """You are analyzing images from MARE, a streetwear brand (2018-2022) with techwear and sportswear influences, being prepared for relaunch.

Analyze this image and return a JSON object with:
- "visual_type": one of ["product_photo", "flat_lay", "on_model", "detail_shot", "sketch", "technical_drawing", "pattern_piece", "render_3d", "texture_swatch", "fabric_photo", "lookbook", "mood_board", "logo", "graphic", "packaging", "label_tag", "construction_detail", "wip_shot", "reference_photo", "unknown"]
- "garment_category": if a garment is visible, one of ["outerwear", "tops", "bottoms", "accessories", "footwear", "bags", "headwear", "sets", null]
- "description": 1-2 sentence description of what you see
- "design_elements": list of notable design elements (e.g. ["cargo pockets", "contrast stitching", "modular panel"])
- "colors": list of dominant colors
- "relevance": "high" | "medium" | "low" for brand relaunch (high = actual MARE product/design, medium = useful reference, low = generic/unclear)
- "notes": anything notable for a designer reviewing this archive

Output ONLY valid JSON. No explanation, no markdown."""


# ── Logging ────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── State I/O ──────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"State file not found: {STATE_FILE}", file=sys.stderr)
        sys.exit(1)
    for _ in range(5):
        try:
            with open(STATE_FILE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (IOError, json.JSONDecodeError):
            time.sleep(0.1)
    print("Failed to load state file after retries", file=sys.stderr)
    sys.exit(1)


def save_state(state: dict):
    with open(STATE_FILE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            json.dump(state, f, indent=2)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def daily_used(state: dict) -> int:
    return state.get("daily_counts", {}).get(get_today(), 0)


# ── Image encoding ─────────────────────────────────────────────────────────────
def encode_image(path: str) -> tuple[str, str]:
    ext = Path(path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


# ── Gemini call ────────────────────────────────────────────────────────────────
def call_gemini(image_path: str) -> dict:
    b64, mime = encode_image(image_path)
    payload = json.dumps({
        "contents": [{"parts": [
            {"text": CATEGORIZATION_PROMPT},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048,
                             "responseMimeType": "application/json"},
    }).encode()

    req = urllib.request.Request(
        GEMINI_URL_TMPL.format(key=API_KEY),
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        result = json.loads(resp.read())

    text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# ── Queue builder ──────────────────────────────────────────────────────────────
def build_queue(state: dict, high_only: bool = True) -> list[str]:
    """Return absolute paths that have Qwen results but no Gemini pass yet."""
    queue = []
    for path, data in state.get("processed", {}).items():
        if not isinstance(data, dict):
            continue
        if data.get("gemini"):
            continue
        rel = data.get("result", {}).get("relevance", "low")
        if high_only and rel not in ("high", "critical"):
            continue
        queue.append(path)
    return queue


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    global API_KEY

    parser = argparse.ArgumentParser(description="MARE Online Archive — Gemini Pass")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=DAILY_LIMIT)
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--all-relevance", action="store_true",
                        help="Process medium/low too (default: high only)")
    args = parser.parse_args()

    if not args.dry_run and not args.status:
        API_KEY = _get_api_key()

    state = load_state()
    processed = state.get("processed", {})

    # ── Status mode ──────────────────────────────────────────────────────────
    if args.status:
        total   = len(processed)
        done    = sum(1 for v in processed.values() if isinstance(v,dict) and v.get("gemini"))
        pending = total - done
        high    = sum(1 for v in processed.values()
                      if isinstance(v,dict) and not v.get("gemini")
                      and v.get("result",{}).get("relevance") in ("high","critical"))
        print(f"Total entries  : {total}")
        print(f"Gemini done    : {done}")
        print(f"Pending        : {pending}  (high-relevance: {high})")
        print(f"Today's usage  : {daily_used(state)}/{DAILY_LIMIT}")
        return

    # ── Lock ──────────────────────────────────────────────────────────────────
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print("Another sweep is already running. Exiting.")
        sys.exit(0)
    lock_fd.write(str(os.getpid()))
    lock_fd.flush()

    # ── Build queue ───────────────────────────────────────────────────────────
    high_only = not args.all_relevance
    queue = build_queue(state, high_only=high_only)
    remaining_budget = min(args.limit, DAILY_LIMIT) - daily_used(state)

    log(f"Queue: {len(queue)} images  |  budget: {remaining_budget}  |  high-only: {high_only}")

    if remaining_budget <= 0:
        log("Daily budget exhausted. Run again tomorrow.")
        return

    done = 0
    errors = 0

    for path in queue:
        if done >= remaining_budget:
            log(f"Budget reached ({remaining_budget}). Stopping.")
            break

        if not Path(path).exists():
            log(f"MISSING: {path}")
            continue

        file_size = Path(path).stat().st_size
        if file_size > 5 * 1024 * 1024:
            log(f"SKIP (>5MB): {path}")
            continue

        log(f"[{done+1}/{len(queue)}] {Path(path).name}")

        if args.dry_run:
            log("  [DRY-RUN] Would call Gemini")
            done += 1
            continue

        try:
            result = call_gemini(path)
            state = load_state()
            if path in state["processed"]:
                state["processed"][path]["gemini"] = {
                    "analyzed_at": datetime.now().isoformat(),
                    "model": GEMINI_MODEL,
                    "result": result,
                }
                counts = state.setdefault("daily_counts", {})
                counts[get_today()] = counts.get(get_today(), 0) + 1
                save_state(state)
            done += 1
            time.sleep(DELAY_SECS)

        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else str(e)
            if e.code == 429:
                log(f"  RATE LIMITED — sleeping 60s")
                time.sleep(60)
            else:
                log(f"  HTTP {e.code}: {body[:120]}")
                errors += 1
        except Exception as e:
            log(f"  ERROR: {e}")
            errors += 1

    log(f"Done. Processed: {done}  Errors: {errors}  Remaining in queue: {len(queue)-done}")

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
