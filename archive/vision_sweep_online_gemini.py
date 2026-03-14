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

# ── Queue definitions (from ONLINE-GEMINI-STRATEGY.md) ────────────────────────
QUEUE_A_TYPES = {"product_photo", "on_model", "packaging"}   # Trust Qwen, skip
QUEUE_B_TYPES = {"graphic", "logo", "render_3d", "detail_shot", "texture_swatch", "unknown"}  # Verify
QUEUE_C_TYPES = {"graphic", "sketch", "mood_board", "fabric_photo", "technical_drawing",       # Rescue
                 "reference_photo", "pattern_piece"}

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
def build_queue(state: dict, queue_mode: str = "all") -> list[str]:
    """
    Return absolute paths that have Qwen results but no Gemini pass yet.

    queue_mode:
      "A"   — Verify: Qwen=high AND visual_type in QUEUE_A_TYPES (on_model, product_photo, etc.)
      "B"   — Verify: Qwen=high AND visual_type in QUEUE_B_TYPES
      "C"   — Rescue: Qwen=low/medium AND visual_type in QUEUE_C_TYPES
      "BC"  — B + C combined
      "ABC" — All three queues
      "all" — All entries without Gemini pass
    """
    queue = []
    for path, data in state.get("processed", {}).items():
        if not isinstance(data, dict):
            continue
        if data.get("gemini"):
            continue
        rel = data.get("result", {}).get("relevance", "low")
        vt  = data.get("result", {}).get("visual_type", "unknown")

        if queue_mode == "A":
            if rel in ("high", "critical") and vt in QUEUE_A_TYPES:
                queue.append(path)
        elif queue_mode == "B":
            if rel in ("high", "critical") and vt in QUEUE_B_TYPES:
                queue.append(path)
        elif queue_mode == "C":
            if rel in ("low", "medium") and vt in QUEUE_C_TYPES:
                queue.append(path)
        elif queue_mode == "BC":
            is_b = rel in ("high", "critical") and vt in QUEUE_B_TYPES
            is_c = rel in ("low", "medium") and vt in QUEUE_C_TYPES
            if is_b or is_c:
                queue.append(path)
        elif queue_mode == "ABC":
            is_a = rel in ("high", "critical") and vt in QUEUE_A_TYPES
            is_b = rel in ("high", "critical") and vt in QUEUE_B_TYPES
            is_c = rel in ("low", "medium") and vt in QUEUE_C_TYPES
            if is_a or is_b or is_c:
                queue.append(path)
        else:  # "all"
            queue.append(path)
    return queue


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    global API_KEY

    parser = argparse.ArgumentParser(description="MARE Online Archive — Gemini Pass")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=DAILY_LIMIT)
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--queue", choices=["A","B","C","BC","ABC","all"], default="all",
                        help="B=verify weak categories, C=rescue low/med, BC=Day1 (default: all)")
    args = parser.parse_args()

    if not args.dry_run and not args.status:
        API_KEY = _get_api_key()

    state = load_state()
    processed = state.get("processed", {})

    # ── Status mode ──────────────────────────────────────────────────────────
    if args.status:
        total = len(processed)
        done  = sum(1 for v in processed.values() if isinstance(v,dict) and v.get("gemini"))
        print(f"Total entries  : {total}")
        print(f"Gemini done    : {done}")
        print(f"Pending        : {total - done}")
        print(f"  Queue A      : {len(build_queue(state, 'A'))}  (Qwen high: on_model, product_photo, packaging)")
        print(f"  Queue B      : {len(build_queue(state, 'B'))}  (verify: high+weak categories)")
        print(f"  Queue C      : {len(build_queue(state, 'C'))}  (rescue: low/med miscat categories)")
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
    queue = build_queue(state, queue_mode=args.queue)
    remaining_budget = min(args.limit, DAILY_LIMIT) - daily_used(state)

    log(f"Queue: {len(queue)} images  |  mode: --queue {args.queue}  |  budget: {remaining_budget}")

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
