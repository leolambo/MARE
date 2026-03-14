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
    from .solvers import rect_panel_grid, pant_block
except Exception:  # direct script run fallback
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from solvers import rect_panel_grid, pant_block  # type: ignore


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


def _load_size_chart(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _pants_measurements_from_size_chart(path: Path, *, size: str | None = None) -> dict:
    data = _load_size_chart(path)
    sizes = data.get("sizes") or {}
    ref_size = str(size or data.get("reference_size") or "30")
    row = sizes.get(ref_size)
    if not row:
        raise ValueError(f"Size {ref_size} not found in {path}")

    # Brand chart is flat for hip/leg opening. Waist is size-based circumference.
    inseam = float(row.get("inseam_extra_short") or row.get("inseam_short") or row.get("inseam_standard"))
    waist = float(row["waist"])
    hip = float(row["hip"]) * 2.0
    leg_opening = float(row["leg_opening"]) * 2.0
    front_rise = float(row["front_rise"])

    return {
        "waist": waist,
        "hip": hip,
        "front_rise": front_rise,
        "back_rise": front_rise + 2.0,
        "inseam": inseam,
        "outseam": front_rise + inseam - 0.75,
        "thigh": 28.0 if waist == 30 else max(24.0, hip * 0.54),
        "leg_opening": leg_opening,
        "fly_length": 10.0,
        "size": ref_size,
    }


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
        # wrap_factor: 1.0 = front face only, 2.0 = full leg circumference (Option A)
        "wrap_factor": float(ratios.get("wrap_factor", 1.0)),
    }
    if out["panels_per_row"] < 1 or out["panels_per_col"] < 1:
        raise ValueError("panels_per_row and panels_per_col must be >= 1")
    if out["gap_ratio"] < 0 or out["corner_radius_ratio"] < 0:
        raise ValueError("gap_ratio and corner_radius_ratio must be >= 0")
    if out["wrap_factor"] <= 0:
        raise ValueError("wrap_factor must be > 0")
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


def _rounded_rect_svg_path(x0: float, y0: float, w: float, h: float, r: float, n_arc: int = 12) -> str:
    """Return an SVG path string for a rounded rectangle (tessellated arcs, mm coords)."""
    import math
    x1, y1 = x0 + w, y0 + h
    r = min(max(r, 0.0), min(w, h) / 2.0)
    pts = []

    def add_arc(cx: float, cy: float, start_deg: float, end_deg: float) -> None:
        for i in range(1, n_arc + 1):
            ang = math.radians(start_deg + (end_deg - start_deg) * i / n_arc)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

    pts.append((x0 + r, y0))
    pts.append((x1 - r, y0))
    add_arc(x1 - r, y0 + r, 270, 360)
    pts.append((x1,   y1 - r))
    add_arc(x1 - r, y1 - r,   0,  90)
    pts.append((x0 + r, y1))
    add_arc(x0 + r, y1 - r,  90, 180)
    pts.append((x0,   y0 + r))
    add_arc(x0 + r, y0 + r, 180, 270)

    d = f"M {pts[0][0]:.3f},{pts[0][1]:.3f} " + " ".join(f"L {x:.3f},{y:.3f}" for x, y in pts[1:]) + " Z"
    return d


def _write_svg_preview(output_path: Path, dims: dict, right_dims: dict, right_x_offset: float, scale: float = 1.0) -> None:
    """Write an SVG preview of both legs for visual shape verification."""
    MM = scale  # scale factor applied to all coords (already in mm if scale=25.4)

    panel_w = float(dims["panel_width"]) * MM
    panel_h = float(dims["panel_height"]) * MM
    corner_r = float(dims["corner_radius"]) * MM
    cut_off = 3.0 / 25.4 * MM  # CUTLINE_OFFSET_IN in mm

    right_offset_mm = right_x_offset * MM
    total_w = right_offset_mm + float(dims["total_width"]) * MM
    total_h = float(dims["total_height"]) * MM

    pad = 10.0
    vb_w = total_w + pad * 2
    vb_h = total_h + pad * 2

    paths = []

    def add_panels(piece_list: list, x_off: float) -> None:
        for piece in piece_list:
            px = (x_off + float(piece["x_origin"])) * MM + pad
            py = float(piece["y_origin"]) * MM + pad
            # sewing line
            d = _rounded_rect_svg_path(px, py, panel_w, panel_h, corner_r)
            paths.append(f'  <path d="{d}" fill="white" stroke="#222" stroke-width="1.2"/>')
            # cutting line
            d2 = _rounded_rect_svg_path(px - cut_off, py - cut_off, panel_w + 2*cut_off, panel_h + 2*cut_off, corner_r + cut_off)
            paths.append(f'  <path d="{d2}" fill="none" stroke="#888" stroke-width="0.6" stroke-dasharray="3,2"/>')

    add_panels(dims.get("pieces", []), 0.0)
    add_panels(right_dims.get("pieces", []), right_x_offset)

    svg = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w:.1f} {vb_h:.1f}" width="{vb_w:.0f}" height="{vb_h:.0f}">',
        f'  <rect width="{vb_w:.1f}" height="{vb_h:.1f}" fill="#e8e8e8"/>',
        *paths,
        "</svg>",
    ])
    output_path.write_text(svg)
    print(f"Preview SVG: {output_path}")


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
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate an SVG preview alongside the DXF for visual shape verification (no CLO3D needed)",
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

    size_chart_path = design_dir / "size-chart.json"
    pants_mode = size_chart_path.exists() and "pants" in json.dumps(_load_size_chart(size_chart_path)).lower()

    try:
        measurements = _pants_measurements_from_size_chart(size_chart_path) if pants_mode else _parse_measurements_from_intake(intake_path)
    except Exception as exc:
        print(f"Failed to read measurements: {exc}", file=sys.stderr)
        return 1

    if pants_mode:
        output_dir = design_dir / "patterns" / "mode_b"
        output_path = output_dir / f"{design_slug}-pant-block.dxf"
        if args.dry_run:
            solution = pant_block.solve(measurements, pant_block.DEFAULT_CONSTRUCTION, pant_block.DEFAULT_EASE)
            print(f"[dry-run] Pants mode for {design_slug}")
            print(json.dumps(measurements, indent=2))
            print(json.dumps(solution["validation"], indent=2))
            print(f"[dry-run] Would write DXF: {output_path}")
            return 0
        solution = pant_block.solve(measurements, pant_block.DEFAULT_CONSTRUCTION, pant_block.DEFAULT_EASE)
        written = pant_block.to_dxf(solution, str(output_path))
        print(f"Design: {design_slug}")
        print(f"Garment: wide_leg_pants")
        print(f"Size: {measurements.get('size', 'reference')}")
        print(f"Pieces: {len(solution['pieces'])}")
        print(f"Validation: {json.dumps(solution['validation'])}")
        print(f"DXF: {written}")
        return 0

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

    # wrap_factor=2.0 (Option A): panels tile full leg circumference,
    # not just the front face. leg_width × 2 ≈ full circumference for wide-leg.
    leg_width = float(measurements["hem_width_per_leg"]) * ratios["wrap_factor"]
    leg_length = float(measurements["inseam"])
    if ratios["wrap_factor"] != 1.0:
        print(f"Wrap mode: factor={ratios['wrap_factor']} → effective leg_width={leg_width:.3f}\"")
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

    # CLO3D works in millimeters — output all coordinates in mm
    MM_PER_IN = 25.4
    doc.header["$INSUNITS"] = 4  # 4 = millimeters

    rect_panel_grid.draw(msp, dims, x_offset=0.0, y_offset=0.0, scale=MM_PER_IN)

    leg_spacing = 2.0  # inches between left and right leg layouts
    right_start_x = float(dims["total_width"]) + leg_spacing
    right_dims = _mirrored_dims(dims)
    rect_panel_grid.draw(msp, right_dims, x_offset=right_start_x, y_offset=0.0, scale=MM_PER_IN)

    # Set drawing extents in mm
    total_w = (right_start_x + float(dims["total_width"])) * MM_PER_IN
    total_h = float(dims["total_height"]) * MM_PER_IN
    margin = float(dims.get("seam_allowance", 0.625)) * MM_PER_IN
    doc.header["$EXTMIN"] = (-margin, -margin, 0)
    doc.header["$EXTMAX"] = (total_w + margin, total_h + margin, 0)

    output_dir.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(output_path))

    if args.preview:
        preview_path = output_path.with_suffix(".svg")
        _write_svg_preview(preview_path, dims, right_dims, right_start_x, scale=MM_PER_IN)

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
