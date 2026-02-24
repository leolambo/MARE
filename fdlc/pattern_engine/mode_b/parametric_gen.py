#!/usr/bin/env python3
"""Mode B parametric pattern generator: intake + ratios -> solver -> DXF."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

DESIGNS_ROOT = Path.home() / "base/creative/MAREv2/designs"
OPENCLAW_CONFIG = Path.home() / ".openclaw/openclaw.json"
GEMINI_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={api_key}"
)
RATIO_PROMPT = (
    "You are analyzing a fashion tech pack. Extract the panel ratio information and return ONLY "
    "a JSON object with these fields: panels_per_row (int), panels_per_col (int), gap_ratio "
    "(float, gap as fraction of panel width), corner_radius_ratio (float, corner radius as fraction "
    "of panel width). No explanation, JSON only."
)


try:
    from .solvers import rect_panel_grid
except Exception:  # direct script run fallback
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from solvers import rect_panel_grid  # type: ignore


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty JSON response")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Could not parse JSON object")


def _get_gemini_api_key() -> str:
    config = _read_json(OPENCLAW_CONFIG)
    try:
        key = config["skills"]["entries"]["nano-banana-pro"]["apiKey"]
    except Exception as exc:
        raise RuntimeError(
            f"Gemini API key missing in {OPENCLAW_CONFIG} at skills.entries.nano-banana-pro.apiKey"
        ) from exc
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("Gemini API key is empty")
    return key.strip()


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/png"


def _call_gemini_for_ratios(tech_pack_path: Path, api_key: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "panels_per_row": 3,
            "panels_per_col": 4,
            "gap_ratio": 0.12,
            "corner_radius_ratio": 0.18,
        }

    if not tech_pack_path.exists():
        raise FileNotFoundError(f"Tech pack image not found: {tech_pack_path}")

    image_b64 = base64.b64encode(tech_pack_path.read_bytes()).decode("ascii")
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": RATIO_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": _mime_for(tech_pack_path),
                            "data": image_b64,
                        }
                    },
                ]
            }
        ]
    }

    req = urlrequest.Request(
        GEMINI_URL_TMPL.format(api_key=api_key),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    text_parts: list[str] = []
    for candidate in body.get("candidates", []) or []:
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        for part in parts or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])

    if not text_parts:
        raise RuntimeError("Gemini returned no text parts")
    return _extract_json_object("\n".join(text_parts))


def _parse_measurements_from_intake(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing intake file: {path}")

    key_map = {
        "waist": "waist",
        "hip": "hip",
        "inseam": "inseam",
        "rise - front": "rise_front",
        "rise - back": "rise_back",
        "hem width per leg": "hem_width_per_leg",
    }
    data: dict[str, float] = {}

    for line in path.read_text().splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        key = cells[0].lower()
        value = cells[1].replace('"', "").strip()
        if key in key_map:
            try:
                data[key_map[key]] = float(value)
            except ValueError:
                continue

    missing = [v for v in key_map.values() if v not in data]
    if missing:
        raise ValueError(f"Missing measurements in {path}: {', '.join(missing)}")
    return data


def _parse_tech_pack_from_intake(path: Path) -> Path | None:
    lines = path.read_text().splitlines()
    in_section = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            in_section = line.lower() == "## tech pack"
            continue
        if in_section and line.startswith("- Path:"):
            value = line.split(":", 1)[1].strip().strip("`")
            if value:
                return Path(value).expanduser()
    return None


def _normalize_ratios(ratios: dict) -> dict:
    required = ["panels_per_row", "panels_per_col", "gap_ratio", "corner_radius_ratio"]
    missing = [k for k in required if k not in ratios]
    if missing:
        raise ValueError(f"Ratio JSON missing keys: {', '.join(missing)}")

    out = {
        "panels_per_row": int(ratios["panels_per_row"]),
        "panels_per_col": int(ratios["panels_per_col"]),
        "gap_ratio": float(ratios["gap_ratio"]),
        "corner_radius_ratio": float(ratios["corner_radius_ratio"]),
    }
    if out["panels_per_row"] < 1 or out["panels_per_col"] < 1:
        raise ValueError("panels_per_row and panels_per_col must be >= 1")
    if out["gap_ratio"] < 0 or out["corner_radius_ratio"] < 0:
        raise ValueError("gap_ratio and corner_radius_ratio must be >= 0")
    return out


def _derive_corner_radius(leg_width: float, cols: int, gap_ratio: float, corner_radius_ratio: float) -> float:
    panel_width = leg_width / (cols + (cols - 1) * gap_ratio)
    return panel_width * corner_radius_ratio


def _mirrored_dims(dims: dict) -> dict:
    mirrored = dict(dims)
    mirrored_pieces = []
    total_w = float(dims["total_width"])
    panel_w = float(dims["panel_width"])

    for piece in dims.get("pieces", []):
        mirrored_piece = dict(piece)
        x = float(piece["x_origin"])
        mirrored_piece["x_origin"] = total_w - panel_w - x
        mirrored_pieces.append(mirrored_piece)

    mirrored["pieces"] = mirrored_pieces
    return mirrored


def _ensure_ezdxf() -> None:
    try:
        import ezdxf  # noqa: F401
    except Exception:
        print("ezdxf is required. Install with: pip install ezdxf", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="parametric_gen",
        description="Mode B parametric generator: ratios + measurements -> panel DXF",
    )
    parser.add_argument("design_name", help="Design slug/name under ~/base/creative/MAREv2/designs")
    parser.add_argument("--tech-pack", dest="tech_pack", help="Path to tech pack image for Gemini ratio extraction")
    parser.add_argument("--ratios", help="Manual ratio JSON override (skips Gemini), e.g. '{\"panels_per_row\":3,...}'")
    parser.add_argument("--recalculate", action="store_true", help="Re-run solver for post-CLO3D adjustments")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without external calls or file writes")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: read from patterns/mode_b/draft/pattern-intake-draft.md, write DXF to patterns/mode_b/draft/",
    )
    args = parser.parse_args()

    _ensure_ezdxf()

    design_slug = args.design_name.strip().lower().replace(" ", "-")
    design_dir = DESIGNS_ROOT / design_slug

    if args.draft:
        intake_path = design_dir / "patterns" / "mode_b" / "draft" / "pattern-intake-draft.md"
    else:
        intake_path = design_dir / "pattern-intake.md"

    if not design_dir.exists():
        print(f"Design directory not found: {design_dir}", file=sys.stderr)
        return 1

    try:
        measurements = _parse_measurements_from_intake(intake_path)
    except Exception as exc:
        print(f"Failed to read measurements: {exc}", file=sys.stderr)
        return 1

    ratios = None
    if args.ratios:
        try:
            ratios = _normalize_ratios(_extract_json_object(args.ratios))
        except Exception as exc:
            print(f"Invalid --ratios JSON: {exc}", file=sys.stderr)
            return 1
    else:
        tech_pack_path = Path(args.tech_pack).expanduser() if args.tech_pack else _parse_tech_pack_from_intake(intake_path)
        if tech_pack_path is None:
            print("No tech pack provided/found. Use --ratios or --tech-pack.", file=sys.stderr)
            return 1
        try:
            key = _get_gemini_api_key()
            ratios = _normalize_ratios(_call_gemini_for_ratios(tech_pack_path, key, dry_run=args.dry_run))
            print(f"Extracted ratios via Gemini from: {tech_pack_path}")
        except (RuntimeError, FileNotFoundError, urlerror.URLError, TimeoutError, ValueError) as exc:
            print(f"Gemini ratio extraction failed: {exc}", file=sys.stderr)
            print("Retry with manual override via --ratios '{...}'", file=sys.stderr)
            return 1

    assert ratios is not None

    leg_width = float(measurements["hem_width_per_leg"])
    leg_length = float(measurements["inseam"])
    corner_radius = _derive_corner_radius(
        leg_width=leg_width,
        cols=ratios["panels_per_row"],
        gap_ratio=ratios["gap_ratio"],
        corner_radius_ratio=ratios["corner_radius_ratio"],
    )

    dims = rect_panel_grid.solve(
        leg_width=leg_width,
        leg_length=leg_length,
        panels_per_row=ratios["panels_per_row"],
        panels_per_col=ratios["panels_per_col"],
        gap_ratio=ratios["gap_ratio"],
        corner_radius=corner_radius,
        seam_allowance=0.625,
    )

    if args.draft:
        output_dir = design_dir / "patterns" / "mode_b" / "draft"
        output_path = output_dir / f"{design_slug}-panels-draft.dxf"
    else:
        output_dir = design_dir / "patterns/mode_b"
        output_path = output_dir / f"{design_slug}-panels.dxf"

    if args.dry_run:
        print(f"[dry-run] Recalculate mode: {args.recalculate}")
        print(f"[dry-run] Design dir: {design_dir}")
        print(f"[dry-run] Measurements: {json.dumps(measurements, indent=2)}")
        print(f"[dry-run] Ratios: {json.dumps(ratios, indent=2)}")
        print(f"[dry-run] Solver dims: {json.dumps(dims, indent=2)}")
        print(f"[dry-run] Would write DXF: {output_path}")
        return 0

    import ezdxf  # type: ignore

    # R2000 (AC1015) — better CLO3D compatibility than R12
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()

    # Set units to inches ($INSUNITS=1) so CLO3D interprets correctly
    doc.header["$INSUNITS"] = 1  # 1 = inches

    rect_panel_grid.draw(msp, dims, x_offset=0.0, y_offset=0.0)

    leg_spacing = 2.0
    right_start_x = float(dims["total_width"]) + leg_spacing
    right_dims = _mirrored_dims(dims)
    rect_panel_grid.draw(msp, right_dims, x_offset=right_start_x, y_offset=0.0)

    # Set drawing extents explicitly — CLO3D uses these to zoom/fit on import
    total_w = right_start_x + float(dims["total_width"])
    total_h = float(dims["total_height"])
    margin = float(dims.get("seam_allowance", 0.625))
    doc.header["$EXTMIN"] = (-margin, -margin, 0)
    doc.header["$EXTMAX"] = (total_w + margin, total_h + margin, 0)

    output_dir.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(output_path))

    total_panels = len(dims.get("pieces", [])) * 2
    print(f"Design: {design_slug}")
    print(f"Recalculate mode: {args.recalculate}")
    print(f"Panels per leg: {len(dims.get('pieces', []))}")
    print(f"Total panels drawn: {total_panels}")
    print(
        "Panel size (in): "
        f"{dims['panel_width']:.3f} x {dims['panel_height']:.3f} | "
        f"gap_x={dims['gap_x']:.3f}, gap_y={dims['gap_y']:.3f}, "
        f"corner_radius={dims['corner_radius']:.3f}"
    )
    print(f"DXF: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
