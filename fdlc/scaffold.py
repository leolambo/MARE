#!/usr/bin/env python3
"""
MARE Design Repository — Scaffold a new design entry.
"""
import argparse, json, shutil, subprocess
from datetime import date, datetime
from pathlib import Path

DESIGNS_ROOT = Path.home() / "base/creative/MAREv2/designs"
DSS_STATE = Path.home() / ".openclaw/workspace/creative/MARE/dss/crawl/vision_state_designs.json"

def slugify(s):
    return s.lower().replace(" ", "-").replace("_", "-")

def scaffold(args):
    slug = slugify(args.name)
    design_dir = DESIGNS_ROOT / slug

    if design_dir.exists() and not args.force:
        print(f"❌ Design '{slug}' already exists. Use --force to overwrite.")
        return

    # Create folder structure
    for sub in ["images/flat", "images/model", "images/sketch", "images/detail", "references", "prompts"]:
        (design_dir / sub).mkdir(parents=True, exist_ok=True)
    print(f"✓ Created folder structure at {design_dir}")

    today = date.today().isoformat()
    colorways = [c.strip() for c in (args.colorways or "").split(",") if c.strip()]
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    # metadata.json
    metadata = {
        "id": slug,
        "name": args.title or slug,
        "status": args.status or "concept",
        "collection": "",
        "season": "",
        "colorways": colorways,
        "tags": tags,
        "price_tier": "",
        "created": today,
        "updated": today
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print("✓ Wrote metadata.json")

    # README.md
    readme = f"# {args.title or slug}\n\n## Description\n\n{args.description or '_Add description here._'}\n\n## Colorways\n\n"
    for c in colorways:
        readme += f"- **{c.replace('-', ' ').title()}**\n"
    readme += "\n## Notes\n\n_Add design notes, decisions, and context here as the design evolves._\n"
    (design_dir / "README.md").write_text(readme)
    print("✓ Wrote README.md")

    # spec.md
    spec = f"# {args.title or slug} — Construction Spec\n\n## Fabric\n\n_TBD_\n\n## Construction\n\n_TBD_\n\n## Silhouette\n\n_TBD_\n\n## Hardware / Closures\n\n_TBD_\n\n## Sizing\n\n_TBD_\n\n## Materials\n\n_TBD — fabric weight, composition_\n"
    (design_dir / "spec.md").write_text(spec)
    print("✓ Wrote spec.md")

    # prompts/generation-log.md
    gen_log = f"# Generation Log — {args.title or slug}\n\nModel used: `gemini-3-pro-image-preview` via API key (nano-banana-pro)\n\n## Iteration History\n\n| Version | File | Key change | Notes |\n|---------|------|-----------|-------|\n| v1 | | Initial concept | |\n\n## Key Prompt Learnings\n\n_Document what worked and what didn't as you iterate._\n\n## Final Prompt Template\n\n```\n_Paste the winning prompt here once locked in._\n```\n"
    (design_dir / "prompts/generation-log.md").write_text(gen_log)
    print("✓ Wrote prompts/generation-log.md")

    # Copy images
    def copy_image(src_str, dest_dir, label=None):
        src = Path(src_str.strip())
        if not src.exists():
            print(f"  ⚠ Image not found: {src}")
            return
        suffix = src.suffix
        filename = (slugify(label) + suffix) if label else src.name
        dest = design_dir / dest_dir / filename
        shutil.copy2(src, dest)
        print(f"  ✓ Copied {src.name} → {dest_dir}/{filename}")

    for entry in (args.image_flat or []):
        parts = entry.split(",", 1)
        copy_image(parts[0], "images/flat", parts[1] if len(parts) > 1 else None)
    for entry in (args.image_model or []):
        parts = entry.split(",", 1)
        copy_image(parts[0], "images/model", parts[1] if len(parts) > 1 else None)
    for entry in (args.image_sketch or []):
        copy_image(entry, "images/sketch")
    for entry in (args.image_reference or []):
        copy_image(entry, "references")

    # Update index.json
    index_file = DESIGNS_ROOT / "index.json"
    if index_file.exists():
        index = json.loads(index_file.read_text())
    else:
        index = {"updated": today, "designs": []}

    # Remove existing entry if present
    index["designs"] = [d for d in index["designs"] if d["id"] != slug]
    index["designs"].append({
        "id": slug,
        "name": metadata["name"],
        "status": metadata["status"],
        "colorways": colorways,
        "collection": "",
        "tags": tags,
        "created": today
    })
    index["updated"] = today
    index_file.write_text(json.dumps(index, indent=2))
    print("✓ Updated index.json")

    # Update DSS vision_state_designs.json
    update_dss(slug, metadata, design_dir, args)
    print("✓ Updated vision_state_designs.json")

    # Reindex QMD
    print("⟳ Reindexing QMD...")
    subprocess.run(["qmd", "update"], check=False)
    subprocess.run(["qmd", "embed"], check=False)
    print("✓ QMD reindexed")

    print(f"\n✅ Design '{slug}' scaffolded at:\n   {design_dir}")


def build_dss_entry(image_path: Path, slug: str, metadata: dict, image_type: str, colorway: str = None):
    """Build a pre-authored DSS entry for a known design image."""
    now = datetime.now().isoformat()
    colors = [colorway] if colorway else metadata.get("colorways", [])
    description = (
        f"{metadata['name']}"
        + (f", {colorway} colorway" if colorway else "")
        + f". {image_type.replace('_', ' ').title()} shot."
    )

    visual_type_map = {
        "flat": "flat_lay",
        "model": "model_shot",
        "sketch": "sketch",
        "detail": "detail_shot",
        "reference": "reference",
    }

    return {
        "folder": f"images/{image_type}" if image_type not in ("reference", "sketch") else image_type,
        "collection": slug,
        "collection_source": "authored",
        "source": "authored",
        "analyzed_at": now,
        "model": "authored",
        "result": {
            "visual_type": visual_type_map.get(image_type, image_type),
            "garment_category": "bottoms",
            "description": description,
            "design_elements": metadata.get("tags", []),
            "colors": colors,
            "relevance": "high",
            "notes": f"Curated design asset. Status: {metadata.get('status', 'concept')}."
        }
    }


def update_dss(slug: str, metadata: dict, design_dir: Path, args):
    """Write pre-authored DSS entries for all images in this design."""
    # Load or init state
    if DSS_STATE.exists():
        state = json.loads(DSS_STATE.read_text())
    else:
        state = {
            "processed": {},
            "errors": [],
            "started_at": datetime.now().isoformat(),
            "last_run": datetime.now().isoformat(),
        }

    # Remove any existing entries for this design (re-scaffold idempotency)
    state["processed"] = {
        k: v for k, v in state["processed"].items()
        if v.get("collection") != slug
    }

    def add_entry(image_path: Path, image_type: str, colorway: str = None):
        if not image_path.exists():
            return
        state["processed"][str(image_path)] = build_dss_entry(image_path, slug, metadata, image_type, colorway)

    # Flat images
    for entry in (args.image_flat or []):
        parts = entry.split(",", 1)
        src = Path(parts[0].strip())
        label = parts[1].strip() if len(parts) > 1 else None
        suffix = src.suffix
        filename = (label.lower().replace(" ", "-") + suffix) if label else src.name
        add_entry(design_dir / "images/flat" / filename, "flat", label)

    # Model images
    for entry in (args.image_model or []):
        parts = entry.split(",", 1)
        src = Path(parts[0].strip())
        label = parts[1].strip() if len(parts) > 1 else None
        suffix = src.suffix
        filename = (label.lower().replace(" ", "-") + suffix) if label else src.name
        add_entry(design_dir / "images/model" / filename, "model", label)

    # Sketches
    for entry in (args.image_sketch or []):
        src = Path(entry.strip())
        add_entry(design_dir / "images/sketch" / src.name, "sketch")

    # References
    for entry in (args.image_reference or []):
        src = Path(entry.strip())
        add_entry(design_dir / "references" / src.name, "reference")

    state["last_run"] = datetime.now().isoformat()
    DSS_STATE.write_text(json.dumps(state, indent=2))
    print(f"  → {len([v for v in state['processed'].values() if v.get('collection') == slug])} images registered in DSS")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new MARE design entry")
    parser.add_argument("--name", required=True, help="Slug (e.g. star-grid-denim-pants)")
    parser.add_argument("--title", help="Human readable name")
    parser.add_argument("--description", help="Full design description")
    parser.add_argument("--colorways", help="Comma-separated colorways (e.g. black,light-wash)")
    parser.add_argument("--status", default="concept", help="Status: concept|approved|in-production")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--image-flat", action="append", metavar="PATH[,LABEL]")
    parser.add_argument("--image-model", action="append", metavar="PATH[,LABEL]")
    parser.add_argument("--image-sketch", action="append", metavar="PATH")
    parser.add_argument("--image-reference", action="append", metavar="PATH")
    parser.add_argument("--force", action="store_true", help="Overwrite existing")
    args = parser.parse_args()
    scaffold(args)

if __name__ == "__main__":
    main()
