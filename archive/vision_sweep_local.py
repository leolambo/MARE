#!/usr/bin/env python3
"""
MARE Archive — Pass 2 Local (Qwen2.5-VL via Ollama)
Fast local vision sweep for categorization. No rate limits.
Gemini will do a detail pass on high-relevance items later.

Usage: python3 vision_sweep_local.py [--archive original|online] [--dry-run] [--limit N] [--folder FOLDER] [--status] [--export] [--resweep]
"""

import json, os, sys, time, subprocess, fcntl, atexit, re
from pathlib import Path
from datetime import datetime

ARCHIVE_PATHS = {
    "original": Path.home() / "base" / "creative" / "MARE",
    "online": Path.home() / "base" / "creative" / "MARE ONLINE ARCHIVE",
}

CRAWL_DIRS = {
    "original": Path.home() / ".openclaw" / "workspace" / "creative" / "MARE" / "dss" / "crawl",
    "online": Path.home() / ".openclaw" / "workspace" / "creative" / "MARE ONLINE ARCHIVE" / "dss" / "crawl",
}

MARE_ROOT = ARCHIVE_PATHS["original"]
CRAWL_DIR = CRAWL_DIRS["original"]
VISION_STATE = CRAWL_DIR / "vision_state.json"
VISION_LOG = CRAWL_DIR / "vision_local.log"
LOCK_FILE = CRAWL_DIR / "vision.lock"
LOCK_RESWEEP_FILE = CRAWL_DIR / "vision_resweep.lock"

MODEL = "qwen2.5vl:7b"

HIGH_VALUE_FOLDERS = [
    "PRODUCTS", "PATTERNS", "FABRIC - MATERIALS", "SHIRTS", "RENDERS",
    "FALL WINTER 19", "ARCHIVE", "INSPIRATION", "3D", "WORK", "M'S", "ART",
    "LOGOS", "MARKETING", "PHOTOGRAPHY"
]

ONLINE_HIGH_VALUE_FOLDERS = [
    "PRODUCTS", "MARKETING", "MARE PHOTOGRAPHY", "COLLECTIONS",
    "ANIMATIONS", "ASSETS", "VIDEOGRAPHY", "INSPIRATION",
    "DESIGN FORM"
]

COLLECTION_MAP = {
    "GENESIS COLLECTION": "Genesis",
    "SPRING 19 COLLECTION": "Spring 19",
    "SUMMER 19": "Summer 19",
    "FW 19": "FW 19",
    "FALL COLLECTIONS": "Fall Collections",
    "NIGHTMARE ": "Goodnight Mareyland",
    "GOODNIGHT MAREYLAND": "Goodnight Mareyland",
    "LOVE & PAIN": "Love & Pain",
    "love & pain": "Love & Pain",
    "VVS COLLECTION - 2021": "VVS",
    "VVS": "VVS",
    "vvs": "VVS",
    "ARME": "ARME",
    "CLOUDY NIGHTS": "Cloudy Nights",
    "vip -cloudy nights": "Cloudy Nights / VIP",
    "COLLABS": "Collabs",
    "MANGA": "Manga",
    "GAP RELEASES": "Gap Releases",
    "grid tee": "Grid Tee",
    "aesthetic inspo": "Aesthetic Inspo",
}

# Subfolders to SKIP within MARKETING
MARKETING_SKIP = {"HIRING", "MEMES", "IG"}

# Subfolders to SKIP within PHOTOGRAPHY
PHOTOGRAPHY_SKIP = {"EVENTS", "PHOTOSHOP ACTIONS", "photoscape"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SKIP_EXTENSIONS = {".nef"}
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

ENRICHED_PROMPT = """You are analyzing images from the MARE archive — a streetwear brand (2018-2022) preparing for relaunch as MARE 2.0.

Brand Context

MARE (also known as NIGHT by MARE) is built around the concept of transforming nightmare energy into strength. The name comes from taking "night" out of "nightmare" — what's left is new perspectives, new beginnings. The brand's battle cry is "Life #AintFair. Now what?"

Core Themes
- Resilience and mental fortitude — owning struggle, not hiding from it
- Darkness-to-light transformation
- "No glory in suffering, but there is glory in sacrifice"
- "Faith in Pain"
- Biblical undertones: valley of shadow, treasures of darkness, walking through fire unburned
- "Destruction spawns construction"
- Acknowledgement of darkness not consumed by it
- Natural disasters to wearable art
- Mental health advocacy — brand donates to ADAA, 1-for-1 therapy session model
- We make people feel good thru clothes they enjoy wearing and messages that help them be better

Design Language
- Genre mix: 30% streetwear / 40% techwear / 30% sportswear
- Silhouettes: tactical vests, boxy cropped hoodies/tees, quarter zips, cargo pants, puffer pants, modular elements
- Construction: technical fabrics, tactical hardware, manipulated puffer/down designs, puffer cutouts
- Colors: grayscale base + cool muted tones + vibrant pop accents
- Clean and futuristic with a dash of grunge — grayscale palette with pops of color
- Materials: reflective (3M), down/puffer, technical fabrics. No limits.
- Modular philosophy: detachable aesthetic elements (snap-on graphic panels), not purely utility modularity

Brand Symbols & Elements
- Viz — the Smile character. Defiance in the face of darkness.
- Grid pattern — with slanted MARE text stylized between lines
- VVS (Very Very Solid) — sub-concept
- Elements inspo: lightning, lava, ice, snow, fire, wind

Cultural DNA
- Meaning inspiration: Shayne Oliver, Vivienne Westwood, Raf Simons, Yohji Yamamoto, Maison Margiela, Rick Owens
- Execution inspiration: Stone Island, Heliot Emil, A-COLD-WALL*, Off-White, C2H4
- Cultural inspiration: grunge, cyberpunk, anime/manga, tech culture, rap culture, nerd culture
- Brand equation: Streetwear x Rockstar Grunge x Techwear with a DMV twist

Key Collections & Pieces
- Best work: Winter 2019 capsule (Tactical Vest + Puffer Pants + Vasquiat Quarter Zip)
- Most reaction: Reflective Shorts, Puffer Pants
- Best seller: Reflective Shorts
- Collection names: Genesis, Lightning Capsule, Vasquiat capsule, Love and Pain, VVS (Very Very Solid), GOODNIGHT MAREYLAND, ARME, Cloudy Nights, Spring 19, Summer 19, FW 19, Fall Collections, Collabs

What's NOT MARE
- Generic lifestyle photography with no design connection
- Hiring posts, memes, social media reposts
- The GOODNIGHT MAREYLAND denim pieces (jacket, ripped pants) were considered off-brand
- Anything that romanticizes suffering without the transformation/resilience angle

Analyze this image and return a JSON object with:
- "visual_type": one of ["product_photo", "flat_lay", "on_model", "detail_shot", "sketch", "technical_drawing", "pattern_piece", "render_3d", "texture_swatch", "fabric_photo", "lookbook", "mood_board", "logo", "graphic", "packaging", "label_tag", "construction_detail", "wip_shot", "reference_photo", "brand_element", "unknown"]
- "garment_category": if garment visible, one of ["outerwear", "tops", "bottoms", "accessories", "footwear", "bags", "headwear", "sets", null]
- "description": 1-2 sentence description
- "design_elements": list of notable design elements
- "colors": list of dominant colors
- "brand_alignment": {"score": 1-10, "themes": ["list of brand themes this connects to"], "relaunch_value": "high"|"medium"|"low"}
- "collection": "collection name if identifiable from image content or folder context, null otherwise"
- "notes": why this matters or doesn't for the relaunch

Output ONLY valid JSON."""


def resolve_collection_from_path(rel_path: str) -> tuple[str | None, str | None]:
    """Return first collection match from deepest folder to root."""
    folder_parts = Path(rel_path).parts[:-1]
    for part in reversed(folder_parts):
        if part in COLLECTION_MAP:
            return COLLECTION_MAP[part], "folder_path"
    return None, None


def build_prompt(base_prompt: str, collection: str | None) -> str:
    if not collection:
        return base_prompt
    return f'[Context: This image is from the "{collection}" collection.]\n\n{base_prompt}'


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(VISION_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def atomic_load_state() -> dict:
    """Thread/Process-safe state load."""
    try:
        exists = VISION_STATE.exists()
    except OSError:
        return {
            "processed": {},
            "errors": [],
            "started_at": None,
            "last_run": None,
        }

    if not exists:
        return {
            "processed": {},
            "errors": [],
            "started_at": None,
            "last_run": None,
        }
    
    # Retry loop for acquiring lock (simple spin)
    for _ in range(5):
        try:
            with open(VISION_STATE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    return data
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (IOError, json.JSONDecodeError, OSError):
            time.sleep(0.1)
    
    # Fallback if locked too long or corrupt
    return {"processed": {}, "errors": []}


def atomic_save_state(state: dict):
    """Thread/Process-safe state save."""
    try:
        # Ensure file exists
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
    except OSError:
        pass


def get_image_queue(state: dict, high_value_folders: list[str], resweep: bool = False) -> list[dict]:
    queue = []
    try:
        json_files = sorted(CRAWL_DIR.glob("*.json"))
    except OSError:
        json_files = []

    found_manifest = False
    for json_file in json_files:
        if json_file.name in ("state.json", "vision_state.json", "vision_state_online.json"):
            continue
        if "_vision" in json_file.name:
            continue

        try:
            with open(json_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, dict) or "files" not in data:
            continue
        found_manifest = True

        folder = data.get("folder", "")
        if folder not in high_value_folders:
            continue

        for file_entry in data["files"]:
            if not file_entry.get("is_image"):
                continue
            path = file_entry["path"]
            # Skip excluded subfolders
            if folder in ("MARKETING", "PHOTOGRAPHY"):
                parts = path.split("/")
                subfolder = parts[1] if len(parts) > 2 else ""
                skip_set = MARKETING_SKIP if folder == "MARKETING" else PHOTOGRAPHY_SKIP
                if subfolder in skip_set:
                    continue
            ext = file_entry.get("ext", "").lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            if ext in SKIP_EXTENSIONS:
                continue
            
            # Queue Logic
            if resweep:
                # In resweep, we check if 'result_v2' exists. 
                # If it does, we skip. If it doesn't, we add to queue.
                if "result_v2" in state["processed"].get(path, {}):
                    continue
            else:
                # Normal sweep: skip if path exists in processed
                if path in state["processed"]:
                    continue

            if file_entry.get("size", 0) > MAX_IMAGE_SIZE:
                continue
            if file_entry.get("size", 0) == 0:
                continue

            abs_path = (MARE_ROOT / path).resolve()
            rel_path = Path(path)
            collection, collection_source = resolve_collection_from_path(str(rel_path))
            processed_entry = state["processed"].get(path, {})
            queue.append({
                "path": str(abs_path),
                "rel_path": str(rel_path),
                "folder": folder,
                "state_key": path,  # Preserve legacy key style for manifest-driven archives
                "size": file_entry.get("size", 0),
                "ext": ext,
                "collection": collection,
                "collection_source": collection_source,
                "processed_entry": processed_entry,
            })

    # Fallback for archives without crawl manifests (online archive mode): scan filesystem directly.
    if found_manifest:
        return queue

    root = MARE_ROOT
    allowed_top = set(high_value_folders)
    if not root.exists():
        return queue

    try:
        for abs_path in root.rglob("*"):
            if not abs_path.is_file():
                continue
            ext = abs_path.suffix.lower()
            if ext in SKIP_EXTENSIONS:
                continue
            if ext not in IMAGE_EXTENSIONS:
                continue
            try:
                rel_path = abs_path.relative_to(root)
            except ValueError:
                continue
            if not rel_path.parts:
                continue
            folder = rel_path.parts[0]
            if folder not in allowed_top:
                continue

            rel_path_str = str(rel_path)
            # Mirror manifest-mode exclusions for matching folders.
            if folder in ("MARKETING", "PHOTOGRAPHY", "MARE PHOTOGRAPHY"):
                subfolder = rel_path.parts[1] if len(rel_path.parts) > 2 else ""
                skip_set = MARKETING_SKIP if folder == "MARKETING" else PHOTOGRAPHY_SKIP
                if subfolder in skip_set:
                    continue

            try:
                size = abs_path.stat().st_size
            except OSError:
                continue
            if size == 0 or size > MAX_IMAGE_SIZE:
                continue

            abs_path_str = str(abs_path.resolve())
            processed_entry = state["processed"].get(abs_path_str, {})
            if resweep:
                if "result_v2" in processed_entry:
                    continue
            else:
                if abs_path_str in state["processed"]:
                    continue

            collection, collection_source = resolve_collection_from_path(rel_path_str)
            queue.append({
                "path": abs_path_str,
                "rel_path": rel_path_str,
                "folder": folder,
                "state_key": abs_path_str,
                "size": size,
                "ext": ext,
                "collection": collection,
                "collection_source": collection_source,
                "processed_entry": processed_entry,
            })
    except OSError:
        return queue

    return queue


def parse_json_from_output(text: str) -> dict:
    """Extract JSON from model output, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw": text[:300]}


def call_qwen(image_path: str, prompt: str = CATEGORIZATION_PROMPT) -> dict:
    """Send image to Qwen2.5-VL via Ollama CLI."""
    result = subprocess.run(
        ["ollama", "run", MODEL],
        input=f"[img]{image_path}[/img]\n{prompt}",
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise Exception(f"Ollama error: {result.stderr[:200]}")
    return parse_json_from_output(result.stdout)


def process_queue(queue: list[dict], state: dict, limit: int, resweep: bool = False, dry_run: bool = False):
    to_process = queue[:limit]
    log(f"Queue: {len(queue)} images pending, processing {len(to_process)} (Resweep: {resweep})")

    processed = 0
    errors = 0
    
    prompt = ENRICHED_PROMPT if resweep else CATEGORIZATION_PROMPT

    for i, item in enumerate(to_process):
        item_key = item.get("state_key", item["path"])
        if dry_run:
            if item.get("collection"):
                log(f"  [DRY RUN] Would process: {item['path']} (collection={item['collection']})")
            else:
                log(f"  [DRY RUN] Would process: {item['path']}")
            processed += 1
            continue

        try:
            if not Path(item["path"]).exists():
                log(f"  ⚠️ File missing: {item['path']}")
                errors += 1
                continue

            result = call_qwen(
                item["path"],
                prompt=build_prompt(prompt, item.get("collection")),
            )

            # Use atomic update for safety
            state = atomic_load_state()
            
            # Preserve existing entry data if any
            existing = state["processed"].get(item_key, {})
            
            # Deep merge/update logic
            if resweep:
                # In resweep, we modify the existing entry (or create new if somehow missing)
                # We do NOT touch 'result' or 'gemini' or 'model' (original model)
                # We add 'result_v2', 'analyzed_v2_at'
                entry = existing.copy() if existing else {}
                
                # If it's a new entry (wasn't processed in pass 1), we should set folder
                if "folder" not in entry:
                    entry["folder"] = item["folder"]
                entry["collection"] = item.get("collection")
                entry["collection_source"] = item.get("collection_source")
                
                entry["analyzed_v2_at"] = datetime.now().isoformat()
                entry["model_v2"] = "qwen2.5vl:7b"
                entry["result_v2"] = result
                
                state["processed"][item_key] = entry
                
                # Track resweep count
                state.setdefault("resweep_count", 0)
                state["resweep_count"] += 1
            
            else:
                # Normal sweep logic
                new_entry = {
                    "folder": item["folder"],
                    "collection": item.get("collection"),
                    "collection_source": item.get("collection_source"),
                    "analyzed_at": datetime.now().isoformat(),
                    "model": "qwen2.5vl:7b",
                    "result": result,
                }
                # If Gemini data exists (edge case), keep it
                if "gemini" in existing:
                    new_entry["gemini"] = existing["gemini"]
                
                state["processed"][item_key] = new_entry

            processed += 1
            atomic_save_state(state)

            if processed % 25 == 0:
                elapsed_per = (time.time() - start_time) / processed if processed else 0
                remaining = len(queue) - processed
                eta_min = (remaining * elapsed_per) / 60
                log(f"  Checkpoint: {processed}/{len(to_process)} done, {errors} errors, ~{eta_min:.0f}min remaining")

        except Exception as e:
            errors += 1
            state["errors"].append({
                "path": item["path"],
                "error": str(e)[:200],
                "at": datetime.now().isoformat(),
            })
            log(f"  ❌ Error on {item['path']}: {str(e)[:100]}")
            if errors >= 20:
                log(f"  ❌ Too many errors ({errors}), stopping")
                break

    state["last_run"] = datetime.now().isoformat()
    atomic_save_state(state)
    log(f"Done: {processed} processed, {errors} errors")


def export_results(state: dict):
    # This export function exports the ORIGINAL results (v1)
    # We might want to update it or add a new exporter, but requirements didn't specify.
    # I'll leave it as is for safety, or maybe dump both if v2 exists.
    # Let's keep it simple: export whatever is in 'result'. 
    # If the user wants v2 export, they might need to ask or I can include it.
    # The requirement said "Writes results to a NEW field result_v2... preserves original result".
    # It didn't explicitly ask for v2 export logic changes, but standard export usually dumps the `result` key.
    # I'll tweak export to include result_v2 if present.
    
    by_folder = {}
    for path, data in state["processed"].items():
        folder = data.get("folder", "UNKNOWN")
        if folder not in by_folder:
            by_folder[folder] = []
        
        export_item = {
            "path": path,
            **data.get("result", {}),
        }
        if "result_v2" in data:
            export_item["result_v2"] = data["result_v2"]
            
        by_folder[folder].append(export_item)

    for folder, results in by_folder.items():
        out_file = CRAWL_DIR / f"{folder.lower().replace(' ', '_').replace('-', '')}_vision.json"
        out_file.write_text(json.dumps({
            "folder": folder,
            "vision_pass_at": datetime.now().isoformat(),
            "model": "qwen2.5vl:7b",
            "total_analyzed": len(results),
            "results": results,
        }, indent=2))
        log(f"Exported {len(results)} results to {out_file.name}")


def ensure_runtime_paths(archive: str):
    """Ensure crawl/state paths are writable; fallback to local workspace runtime dir when needed."""
    global CRAWL_DIR, VISION_STATE, VISION_LOG, LOCK_FILE, LOCK_RESWEEP_FILE
    try:
        CRAWL_DIR.mkdir(parents=True, exist_ok=True)
        return
    except OSError:
        fallback_dir = Path.cwd() / ".vision_runtime" / archive
        fallback_dir.mkdir(parents=True, exist_ok=True)
        CRAWL_DIR = fallback_dir
        VISION_STATE = CRAWL_DIR / ("vision_state_online.json" if archive == "online" else "vision_state.json")
        VISION_LOG = CRAWL_DIR / "vision_local.log"
        LOCK_FILE = CRAWL_DIR / "vision.lock"
        LOCK_RESWEEP_FILE = CRAWL_DIR / "vision_resweep.lock"


def main():
    global start_time, MARE_ROOT, CRAWL_DIR, VISION_STATE, VISION_LOG, LOCK_FILE, LOCK_RESWEEP_FILE
    import argparse
    parser = argparse.ArgumentParser(description="MARE Pass 2 — Local Qwen Vision Sweep")
    parser.add_argument("--archive", choices=["original", "online"], default="original")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=999999)
    parser.add_argument("--folder", type=str)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--resweep", action="store_true", help="Run resweep with enriched prompt (writes to result_v2)")
    args = parser.parse_args()

    MARE_ROOT = ARCHIVE_PATHS[args.archive]
    CRAWL_DIR = CRAWL_DIRS[args.archive]
    VISION_STATE = CRAWL_DIR / ("vision_state_online.json" if args.archive == "online" else "vision_state.json")
    VISION_LOG = CRAWL_DIR / "vision_local.log"
    LOCK_FILE = CRAWL_DIR / "vision.lock"
    LOCK_RESWEEP_FILE = CRAWL_DIR / "vision_resweep.lock"
    ensure_runtime_paths(args.archive)

    high_value_folders = ONLINE_HIGH_VALUE_FOLDERS if args.archive == "online" else HIGH_VALUE_FOLDERS

    state = atomic_load_state()

    if args.status:
        total = len(state["processed"])
        
        # Calculate queue based on mode (if user passes --resweep --status, show resweep queue)
        # But wait, default status should probably show both if resweep active?
        # Requirement: "Update --status to also show resweep progress when --resweep is passed"
        
        if args.resweep:
            queue = get_image_queue(state, high_value_folders, resweep=True)
            resweep_done = state.get("resweep_count", 0) # Or count actual result_v2 keys for accuracy
            resweep_done_actual = sum(1 for v in state["processed"].values() if "result_v2" in v)
            
            print(f"=== RESWEEP STATUS ===")
            print(f"Processed (result_v2): {resweep_done_actual}")
            print(f"Remaining in Resweep Queue: {len(queue)}")
            print(f"Errors: {len(state.get('errors', []))}")
            if queue:
                folders = {}
                for item in queue:
                    folders[item['folder']] = folders.get(item['folder'], 0) + 1
                print("Resweep Queue by folder:")
                for f, c in sorted(folders.items(), key=lambda x: -x[1]):
                    print(f"  {f}: {c}")
        else:
            queue = get_image_queue(state, high_value_folders, resweep=False)
            high_rel = sum(1 for v in state["processed"].values()
                           if isinstance(v.get("result"), dict) and v["result"].get("relevance") == "high")
            gemini_count = sum(1 for v in state["processed"].values() if "gemini" in v)
            resweep_count = sum(1 for v in state["processed"].values() if "result_v2" in v)

            print(f"Processed (Qwen): {total}")
            print(f"High relevance: {high_rel}")
            print(f"Picked up by Gemini: {gemini_count}")
            print(f"Reswept (v2): {resweep_count}")
            print(f"Remaining in Qwen Queue: {len(queue)}")
            print(f"Errors: {len(state.get('errors', []))}")
            print(f"Last run: {state.get('last_run', 'never')}")
            if queue:
                folders = {}
                for item in queue:
                    folders[item['folder']] = folders.get(item['folder'], 0) + 1
                print("Queue by folder:")
                for f, c in sorted(folders.items(), key=lambda x: -x[1]):
                    print(f"  {f}: {c}")
        return

    if args.export:
        export_results(state)
        return

    queue = get_image_queue(state, high_value_folders, resweep=args.resweep)
    if args.folder:
        queue = [q for q in queue if q["folder"] == args.folder]

    if not queue:
        log("All images processed! Run --export to generate result files.")
        return

    # Lock file logic
    lock_file_path = LOCK_RESWEEP_FILE if args.resweep else LOCK_FILE
    
    try:
        lock_fd = open(lock_file_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        atexit.register(lambda: (fcntl.flock(lock_fd, fcntl.LOCK_UN), lock_fd.close(), lock_file_path.unlink(missing_ok=True)))
    except (IOError, OSError):
        log(f"Another vision sweep ({'resweep' if args.resweep else 'normal'}) is already running. Exiting.")
        sys.exit(0)

    state["started_at"] = datetime.now().isoformat()
    start_time = time.time()
    
    mode_str = "RESWEEP (Enriched Prompt)" if args.resweep else "Pass 2 Local Vision Sweep"
    log(f"=== {mode_str} (Qwen2.5-VL 7B) ===")
    log(f"Archive: {args.archive} ({MARE_ROOT})")
    log(f"Folders: {', '.join(high_value_folders)}")

    process_queue(queue, state, args.limit, resweep=args.resweep, dry_run=args.dry_run)
    export_results(state)


if __name__ == "__main__":
    main()
