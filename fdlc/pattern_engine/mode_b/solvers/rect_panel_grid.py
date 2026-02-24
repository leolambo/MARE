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


def _rounded_rect_lwpoly(msp, x0: float, y0: float, width: float, height: float, radius: float, layer: str) -> None:
    """
    Draw a rounded rectangle as a single closed LWPOLYLINE with bulge values.

    This is the DXF-AAMA/ASTM compatible format — CLO3D identifies each closed
    LWPOLYLINE as one pattern piece boundary. Individual LINE+ARC entities are
    treated as unrecognized baselines and don't form pattern pieces.

    Bulge encoding: bulge = tan(arc_angle / 4)
    For a CCW quarter-circle (90°): bulge = tan(22.5°) ≈ 0.41421356
    """
    x1 = x0 + width
    y1 = y0 + height
    r = min(max(radius, 0.0), min(width, height) / 2.0)
    ARC_BULGE = 0.41421356  # tan(π/8) — CCW quarter-circle

    # 8 vertices in CCW order: 4 straight edges + 4 corner arcs (via bulge)
    # bulge lives at the START vertex of each arc segment
    points = [
        (x0 + r, y0,      0.0),        # bottom edge start → straight
        (x1 - r, y0,      ARC_BULGE),  # bottom edge end   → CCW arc (bottom-right corner)
        (x1,     y0 + r,  0.0),        # right edge start  → straight
        (x1,     y1 - r,  ARC_BULGE),  # right edge end    → CCW arc (top-right corner)
        (x1 - r, y1,      0.0),        # top edge start    → straight
        (x0 + r, y1,      ARC_BULGE),  # top edge end      → CCW arc (top-left corner)
        (x0,     y1 - r,  0.0),        # left edge start   → straight
        (x0,     y0 + r,  ARC_BULGE),  # left edge end     → CCW arc (bottom-left corner) → back to start
    ]

    # format="xyb" = x, y, bulge per vertex
    msp.add_lwpolyline(
        [(x, y, bulge) for x, y, bulge in points],
        format="xyb",
        dxfattribs={"layer": layer, "closed": True},
    )


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
