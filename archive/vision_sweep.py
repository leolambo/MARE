#!/usr/bin/env python3
"""
MARE Archive — Pass 2 (Gemini Vision Sweep)
Sends high-value images to Gemini for visual categorization.
Supports --tail mode to follow Qwen local processing in parallel.

Usage: python3 vision_sweep.py [--dry-run] [--limit N] [--folder FOLDER] [--high-only] [--tail] [--status] [--export]
"""

import json, os, sys, time, base64, glob, argparse, fcntl, atexit, random
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error

MARE_ROOT = Path.home() / "base" / "creative" / "MARE"
CRAWL_DIR = Path.home() / ".openclaw" / "workspace" / "creative" / "MARE" / "dss" / "crawl"
VISION_STATE = CRAWL_DIR / "vision_state.json"
VISION_LOG = CRAWL_DIR / "vision.log"
QWEN_LOCK_FILE = CRAWL_DIR / "vision.lock"
GEMINI_LOCK_FILE = CRAWL_DIR / "vision_gemini.lock"

# Gemini API config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# gemini-2.5-flash endpoint
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
QWEN_MODEL = "qwen2.5vl:7b"
GEMINI_MODEL = "gemini-2.5-flash"

# Rate limiting (Gemini 2.5 Flash Paid: 10,000 RPD, ~? RPM. Using safe limits)
# Requirement: 9500 daily limit, 450 RPM (approx 7.5 req/sec), 0.15s delay
DAILY_LIMIT = 9500
REQUESTS_PER_MINUTE = 450
DELAY_BETWEEN_REQUESTS = 2  # Fast pace, paid tier  # seconds

# High-value folders for vision analysis (from triage)
HIGH_VALUE_FOLDERS = [
    "PRODUCTS", "PATTERNS", "FABRIC - MATERIALS", "SHIRTS", "RENDERS",
    "FALL WINTER 19", "ARCHIVE", "INSPIRATION", "3D", "WORK", "M'S", "ART",
    "LOGOS", "MARKETING", "PHOTOGRAPHY"
]

# Subfolders to SKIP within MARKETING
MARKETING_SKIP = {"HIRING", "MEMES", "IG"}

# Subfolders to SKIP within PHOTOGRAPHY
PHOTOGRAPHY_SKIP = {"EVENTS", "PHOTOSHOP ACTIONS", "photoscape"}

# Image extensions we can send to Gemini
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Max image size to send (10MB Gemini limit, we cap at 5MB)
MAX_IMAGE_SIZE = 5 * 1024 * 1024

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


def log(msg: str):
    """Append to vision log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(VISION_LOG, "a") as f:
        f.write(line + "\n")


def atomic_load_state() -> dict:
    """Thread/Process-safe state load."""
    if not VISION_STATE.exists():
        return {
            "processed": {},
            "daily_counts": {},
            "errors": [],
            "started_at": None,
            "last_run": None,
            "miscat_count": 0,
            "spot_check_count": 0
        }
    
    # Retry loop for acquiring lock
    for _ in range(5):
        try:
            with open(VISION_STATE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    return data
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (IOError, json.JSONDecodeError):
            time.sleep(0.1)
    
    # Fallback/Fail
    return {"processed": {}, "errors": []}


def atomic_save_state(state: dict):
    """Thread/Process-safe state save."""
    # Ensure file exists first to allow r+ mode
    if not VISION_STATE.exists():
        VISION_STATE.write_text("{}")
        
    with open(VISION_STATE, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            json.dump(state, f, indent=2)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def daily_remaining(state: dict) -> int:
    today = get_today()
    used = state.get("daily_counts", {}).get(today, 0)
    return max(0, DAILY_LIMIT - used)


def encode_image(filepath: str) -> tuple[str, str]:
    """Read and base64-encode an image. Returns (b64_data, mime_type)."""
    ext = Path(filepath).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(ext, "image/jpeg")

    with open(filepath, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return data, mime


def call_gemini(image_path: str) -> dict:
    """Send an image to Gemini for analysis."""
    b64_data, mime_type = encode_image(image_path)

    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": CATEGORIZATION_PROMPT},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": b64_data
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json"
        }
    }).encode()

    req = urllib.request.Request(
        GEMINI_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        # Extract text from Gemini response
        text = result["candidates"][0]["content"]["parts"][0]["text"]

        # Parse JSON from response
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        return json.loads(text)

    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        if e.code == 429:
            raise Exception(f"RATE_LIMITED: {body}")
        raise Exception(f"HTTP {e.code}: {body[:200]}")
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw": text[:300] if 'text' in dir() else "no text"}
    except Exception as e:
        raise


def get_tail_candidates(state: dict) -> list[str]:
    """Find processed Qwen items that haven't been touched by Gemini yet."""
    candidates = []
    for path, data in state.get("processed", {}).items():
        if not isinstance(data, dict): 
            continue
        
        # Must be Qwen processed
        if data.get("model") != QWEN_MODEL:
            continue
            
        # Must NOT have Gemini data yet
        if "gemini" in data:
            continue
            
        candidates.append(path)
    return candidates


def process_tail(dry_run: bool = False):
    """Continuous polling mode to process Qwen outputs."""
    log("Starting Gemini tail process (waiting for Qwen results)...")
    
    # Ensure state has daily_counts
    state = atomic_load_state()
    if "daily_counts" not in state:
        state["daily_counts"] = {}
        atomic_save_state(state)
    
    consecutive_empty_loops = 0
    
    while True:
        state = atomic_load_state()
        candidates = get_tail_candidates(state)
        
        if not candidates:
            # Check if Qwen is still running
            if not QWEN_LOCK_FILE.exists():
                # Qwen finished and we have no more candidates
                log("Qwen lock file gone and no candidates remaining. Exiting tail process.")
                break
            
            # Wait for more data
            if consecutive_empty_loops % 10 == 0:
                log("Waiting for new Qwen items...")
            consecutive_empty_loops += 1
            time.sleep(30)
            continue
            
        consecutive_empty_loops = 0
        log(f"Found {len(candidates)} new candidates from Qwen.")
        
        for path in candidates:
            # Reload state to be fresh (in case of race, though unlikely with our flow)
            # Actually, for the loop efficiency we can work with current state check
            # but need to lock when writing.
            
            # Re-check daily limit
            if daily_remaining(state) <= 0:
                log("Daily limit reached. Stopping tail.")
                return

            item_data = state["processed"][path]
            qwen_result = item_data.get("result", {})
            if not isinstance(qwen_result, dict):
                qwen_result = {}
            qwen_rel = qwen_result.get("relevance", "low")
            
            spot_check = False
            
            # Logic: High relevance -> Always process
            #        Medium/Low -> 15% random spot check
            should_process = False
            
            if qwen_rel == "high":
                should_process = True
            else:
                if True:  # 100% coverage — all medium/low go to Gemini
                    should_process = True
                    spot_check = True
            
            if not should_process:
                # Mark as skipped in Gemini field so we don't pick it up again
                # OR just leave it? If we leave it, get_tail_candidates picks it up again.
                # We must mark it.
                # We'll write a null or skipped marker.
                # Requirement: "Write Gemini results into the SAME ... entry under a new 'gemini' key"
                # If we skip, we should probably just mark it as skipped so we don't loop forever.
                state = atomic_load_state() # Fresh load before write
                if path in state["processed"]:
                    state["processed"][path]["gemini"] = {
                        "skipped": True,
                        "spot_check": False,
                        "timestamp": datetime.now().isoformat()
                    }
                    atomic_save_state(state)
                continue

            # Process with Gemini
            full_path = MARE_ROOT / path
            if not full_path.exists():
                log(f"File missing: {full_path}")
                continue
                
            log(f"Processing {'(SPOT CHECK) ' if spot_check else ''}{path} (Qwen said: {qwen_rel})")
            
            if dry_run:
                log("  [DRY RUN] Would call Gemini")
                result = {"relevance": "high", "dry_run": True} # Dummy
            else:
                try:
                    result = call_gemini(str(full_path))
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                except Exception as e:
                    log(f"  ❌ Error calling Gemini: {e}")
                    # If rate limited, maybe wait longer?
                    if "RATE_LIMITED" in str(e):
                        time.sleep(60)
                    continue

            # Update State
            state = atomic_load_state()
            if path in state["processed"]:
                state["processed"][path]["gemini"] = {
                    "analyzed_at": datetime.now().isoformat(),
                    "model": GEMINI_MODEL,
                    "result": result,
                    "spot_check": spot_check
                }
                
                # Stats update
                today = get_today()
                state.setdefault("daily_counts", {})[today] = state.get("daily_counts", {}).get(today, 0) + 1
                
                if spot_check:
                    state["spot_check_count"] = state.get("spot_check_count", 0) + 1
                    gemini_rel = result.get("relevance")
                    # Disagreement logic: Gemini says High, Qwen said Medium/Low
                    if gemini_rel == "high" and qwen_rel != "high":
                        log(f"  ⚠️ MISCAT DETECTED: Qwen {qwen_rel} -> Gemini HIGH on {path}")
                        state["miscat_count"] = state.get("miscat_count", 0) + 1

                atomic_save_state(state)
            
            # End of item loop


def export_results(state: dict):
    """Export vision results back into the folder JSONs."""
    # Group results by folder
    by_folder = {}
    
    processed_items = state["processed"]
    
    for path, data in processed_items.items():
        folder = data["folder"]
        if folder not in by_folder:
            by_folder[folder] = []
            
        # Determine primary result
        # If Gemini exists and is not skipped, use it.
        # Otherwise use Qwen.
        
        final_result = {}
        gemini_data = data.get("gemini")
        qwen_result = data.get("result")
        
        if gemini_data and not gemini_data.get("skipped"):
            # Use Gemini as primary
            final_result = gemini_data.get("result", {})
            # Keep Qwen as backup
            final_result["qwen_result"] = qwen_result
            final_result["primary_model"] = GEMINI_MODEL
        else:
            # Use Qwen
            final_result = qwen_result
            final_result["primary_model"] = QWEN_MODEL
            
        by_folder[folder].append({
            "path": path,
            **final_result
        })

    # Write per-folder vision results
    for folder, results in by_folder.items():
        out_file = CRAWL_DIR / f"{folder.lower().replace(' ', '_')}_vision.json"
        out_file.write_text(json.dumps({
            "folder": folder,
            "vision_pass_at": datetime.now().isoformat(),
            "total_analyzed": len(results),
            "results": results,
        }, indent=2))
        log(f"Exported {len(results)} results to {out_file.name}")


def main():
    parser = argparse.ArgumentParser(description="MARE Pass 2 — Gemini Vision Sweep")
    parser.add_argument("--dry-run", action="store_true", help="Don't call API")
    parser.add_argument("--limit", type=int, default=DAILY_LIMIT)
    parser.add_argument("--folder", type=str)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--high-only", action="store_true", help="Legacy mode: Re-analyze only Qwen high-relevance images (batch)")
    parser.add_argument("--tail", action="store_true", help="Run in continuous tail mode following Qwen")
    args = parser.parse_args()

    if not GEMINI_API_KEY and not args.dry_run and not args.status:
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)

    state = atomic_load_state()

    if args.status:
        total = len(state["processed"])
        qwen_only = 0
        gemini_done = 0
        
        for data in state.get("processed", {}).values():
            if "gemini" in data and not data["gemini"].get("skipped"):
                gemini_done += 1
            elif data.get("model") == QWEN_MODEL:
                qwen_only += 1
                
        spot_checks = state.get("spot_check_count", 0)
        miscats = state.get("miscat_count", 0)
        miscat_rate = (miscats / spot_checks * 100) if spot_checks > 0 else 0
        
        candidates = get_tail_candidates(state)
        # Break down queue into what tail would actually process
        high_queue = 0
        sample_pool = 0
        for path in candidates:
            data = state["processed"].get(path, {})
            result = data.get("result", {})
            rel = result.get("relevance", "low") if isinstance(result, dict) else "low"
            if rel == "high":
                high_queue += 1
            else:
                sample_pool += 1
        estimated_samples = int(sample_pool * 0.25)
        
        print(f"Total Processed: {total}")
        print(f"  Qwen Only: {qwen_only}")
        print(f"  Gemini Processed: {gemini_done}")
        print(f"Daily Usage: {state.get('daily_counts', {}).get(get_today(), 0)}/{DAILY_LIMIT}")
        print(f"Spot Checks: {spot_checks}")
        print(f"  Miscategorizations: {miscats}")
        print(f"  Miscat Rate: {miscat_rate:.1f}%")
        print(f"Gemini Queue: {high_queue} high + ~{estimated_samples} spot-checks (from {sample_pool} medium/low)")
        print(f"Last run: {state.get('last_run', 'never')}")
        return

    if args.export:
        export_results(state)
        return

    # Lock file for Gemini/Tail process
    try:
        lock_fd = open(GEMINI_LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        atexit.register(lambda: (fcntl.flock(lock_fd, fcntl.LOCK_UN), lock_fd.close(), GEMINI_LOCK_FILE.unlink(missing_ok=True)))
    except (IOError, OSError):
        log("Another Gemini vision sweep is already running. Exiting.")
        sys.exit(0)

    if args.tail:
        process_tail(args.dry_run)
    else:
        # Legacy batch mode (logic similar to tail but one-pass)
        log("Running in legacy batch mode (use --tail for continuous processing)")
        # ... (Legacy logic omitted for brevity as --tail is the primary request, 
        # but to keep the file valid I should probably leave basic queue logic if needed, 
        # or just point user to --tail. The prompt implies modifying the script to support it.)
        # Reuse process_tail loop logic but break after one pass? 
        # Or just run process_tail once? process_tail has the loop.
        # Let's just run process_tail logic but without the infinite wait loop if Qwen is done?
        # Actually, simpler: just call process_tail. It handles the "wait for Qwen" logic. 
        # If user didn't pass --tail, maybe they want the old behavior?
        # The old behavior was "get_high_only_queue" or "get_image_queue".
        # Requirement: "Keep existing --high-only mode working"
        
        # Re-implement batch logic for --high-only or standard run
        if args.high_only:
             # Just process existing high items that haven't been done
             queue = []
             for path, data in state["processed"].items():
                 if data.get("model") == QWEN_MODEL and "gemini" not in data:
                     if data.get("result", {}).get("relevance") == "high":
                         queue.append(path)
             
             log(f"Processing {len(queue)} high-relevance items...")
             for path in queue:
                 full_path = MARE_ROOT / path
                 if daily_remaining(state) <= 0: break
                 
                 try:
                     res = call_gemini(str(full_path))
                     state = atomic_load_state()
                     if path in state["processed"]:
                         state["processed"][path]["gemini"] = {
                             "analyzed_at": datetime.now().isoformat(),
                             "model": GEMINI_MODEL,
                             "result": res,
                             "spot_check": False
                         }
                         state.setdefault("daily_counts", {})[get_today()] = state.get("daily_counts", {}).get(get_today(), 0) + 1
                         atomic_save_state(state)
                     time.sleep(DELAY_BETWEEN_REQUESTS)
                 except Exception as e:
                     log(f"Error: {e}")
        else:
            log("Please use --tail for the new Qwen+Gemini workflow, or --high-only for batch pass.")

    export_results(state)


if __name__ == "__main__":
    main()
