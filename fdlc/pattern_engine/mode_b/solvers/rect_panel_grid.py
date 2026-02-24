#!/usr/bin/env python3
"""Rounded-rectangle panel grid solver for Mode B parametric generation."""

from __future__ import annotations

import json
from typing import Dict, List

try:
    from ezdxf.enums import TextEntityAlignment as _TEA
    _TEXT_ALIGN = _TEA.MIDDLE_CENTER
except ImportError:
    _TEXT_ALIGN = "MIDDLE_CENTER"  # ezdxf < 1.0 fallback

MM_PER_INCH = 25.4
CUTLINE_OFFSET_IN = 3.0 / MM_PER_INCH


def solve(
    leg_width: float,
    leg_length: float,
    panels_per_row: int,
    panels_per_col: int,
    gap_ratio: float,
    corner_radius: float,
    seam_allowance: float = 0.625,
) -> dict:
    """
    Compute panel/gap dimensions for a non-touching rectangular panel grid.

    Returns dict with panel metrics and piece origins.
    """
    if leg_width <= 0 or leg_length <= 0:
        raise ValueError("leg_width and leg_length must be > 0")
    if panels_per_row < 1 or panels_per_col < 1:
        raise ValueError("panels_per_row and panels_per_col must be >= 1")
    if gap_ratio < 0:
        raise ValueError("gap_ratio must be >= 0")

    width_divisor = panels_per_row + (panels_per_row - 1) * gap_ratio
    height_divisor = panels_per_col + (panels_per_col - 1) * gap_ratio
    panel_width = leg_width / width_divisor
    panel_height = leg_length / height_divisor
    gap_x = panel_width * gap_ratio
    gap_y = panel_height * gap_ratio

    max_radius = min(panel_width, panel_height) / 2.0
    clamped_radius = min(max(corner_radius, 0.0), max_radius)

    pieces: List[Dict[str, float | int | str]] = []
    for row in range(1, panels_per_col + 1):
        for col in range(1, panels_per_row + 1):
            x_origin = (col - 1) * (panel_width + gap_x)
            y_origin = (row - 1) * (panel_height + gap_y)
            pieces.append(
                {
                    "id": f"PANEL_R{row}_C{col}",
                    "col": col,
                    "row": row,
                    "x_origin": x_origin,
                    "y_origin": y_origin,
                }
            )

    total_width = panels_per_row * panel_width + (panels_per_row - 1) * gap_x
    total_height = panels_per_col * panel_height + (panels_per_col - 1) * gap_y

    return {
        "panel_width": panel_width,
        "panel_height": panel_height,
        "gap_x": gap_x,
        "gap_y": gap_y,
        "corner_radius": clamped_radius,
        "seam_allowance": seam_allowance,
        "grid_cols": panels_per_row,
        "grid_rows": panels_per_col,
        "total_width": total_width,
        "total_height": total_height,
        "pieces": pieces,
    }


def _rounded_rect_lwpoly(msp, x0: float, y0: float, width: float, height: float, radius: float, layer: str, n_arc: int = 12) -> None:
    """
    Draw a rounded rectangle as a closed LWPOLYLINE with tessellated arcs.

    Uses straight-line vertex approximation of each quarter-circle corner
    (n_arc segments per 90°) — avoids LWPOLYLINE bulge values which CLO3D
    ignores, rendering octagonal chamfers instead of smooth curves.

    n_arc=12 gives <0.01" error on typical corner radii.
    """
    import math
    x1 = x0 + width
    y1 = y0 + height
    r = min(max(radius, 0.0), min(width, height) / 2.0)

    pts: List[tuple] = []

    def add_arc(cx: float, cy: float, start_deg: float, end_deg: float) -> None:
        """Append n_arc points for a quarter-circle arc (start vertex added by caller)."""
        for i in range(1, n_arc + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / n_arc)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # CCW traversal starting at bottom-left, moving right along bottom edge:
    pts.append((x0 + r, y0))               # bottom edge start
    pts.append((x1 - r, y0))               # bottom edge end
    add_arc(x1 - r, y0 + r, 270, 360)      # bottom-right corner
    pts.append((x1,   y1 - r))             # right edge end
    add_arc(x1 - r, y1 - r,   0,  90)      # top-right corner
    pts.append((x0 + r, y1))               # top edge end
    add_arc(x0 + r, y1 - r,  90, 180)      # top-left corner
    pts.append((x0,   y0 + r))             # left edge end
    add_arc(x0 + r, y0 + r, 180, 270)      # bottom-left corner (closes back to start)

    msp.add_lwpolyline(pts, format="xy", dxfattribs={"layer": layer, "closed": True})


def draw(msp, dims: dict, x_offset: float = 0.0, y_offset: float = 0.0, scale: float = 1.0):
    """
    Draw all panels directly into an ezdxf ModelSpace (no BLOCK/INSERT).
    CLO3D requires geometry in modelspace — block references are ignored on import.
    Each panel is drawn as absolute LINE + ARC entities at its grid position.
    """
    panel_w = float(dims["panel_width"]) * scale
    panel_h = float(dims["panel_height"]) * scale
    corner_r = float(dims["corner_radius"]) * scale

    cut_offset = CUTLINE_OFFSET_IN * scale
    cut_w = panel_w + (2.0 * cut_offset)
    cut_h = panel_h + (2.0 * cut_offset)
    cut_r = corner_r + cut_offset

    text_height = max(0.15 * scale, min(panel_w, panel_h) * 0.12)

    for piece in dims.get("pieces", []):
        px = (x_offset + float(piece["x_origin"])) * scale
        py = (y_offset + float(piece["y_origin"])) * scale

        # Sewing line — closed LWPOLYLINE, AAMA Layer 1 (piece outline)
        _rounded_rect_lwpoly(msp, px, py, panel_w, panel_h, corner_r, layer="1")

        # Cutting line — closed LWPOLYLINE, AAMA Layer 8 (cut line, offset outward)
        _rounded_rect_lwpoly(
            msp,
            px - CUTLINE_OFFSET_IN,
            py - CUTLINE_OFFSET_IN,
            cut_w, cut_h, cut_r,
            layer="8",
        )

        # Panel label (layer 1)
        label = str(piece.get("id", f"R{piece['row']}C{piece['col']}"))
        msp.add_text(
            label,
            dxfattribs={"layer": "1", "height": text_height},
        ).set_placement((px + panel_w / 2.0, py + panel_h / 2.0), align=_TEXT_ALIGN)


if __name__ == "__main__":
    defaults = solve(
        leg_width=10.0,
        leg_length=30.0,
        panels_per_row=3,
        panels_per_col=4,
        gap_ratio=0.12,
        corner_radius=0.5,
        seam_allowance=0.625,
    )
    print(json.dumps(defaults, indent=2))
