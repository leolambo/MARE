#!/usr/bin/env python3
"""Rounded-rectangle panel grid solver for Mode B parametric generation."""

from __future__ import annotations

import json
from typing import Dict, List

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


def _rounded_rect(block, x0: float, y0: float, width: float, height: float, radius: float, layer: str) -> None:
    """Draw exact rounded rectangle using 4 lines + 4 quarter-circle arcs."""
    x1 = x0 + width
    y1 = y0 + height
    r = min(max(radius, 0.0), min(width, height) / 2.0)

    block.add_line((x0 + r, y0), (x1 - r, y0), dxfattribs={"layer": layer})
    block.add_line((x1, y0 + r), (x1, y1 - r), dxfattribs={"layer": layer})
    block.add_line((x1 - r, y1), (x0 + r, y1), dxfattribs={"layer": layer})
    block.add_line((x0, y1 - r), (x0, y0 + r), dxfattribs={"layer": layer})

    block.add_arc(center=(x1 - r, y0 + r), radius=r, start_angle=270.0, end_angle=360.0, dxfattribs={"layer": layer})
    block.add_arc(center=(x1 - r, y1 - r), radius=r, start_angle=0.0, end_angle=90.0, dxfattribs={"layer": layer})
    block.add_arc(center=(x0 + r, y1 - r), radius=r, start_angle=90.0, end_angle=180.0, dxfattribs={"layer": layer})
    block.add_arc(center=(x0 + r, y0 + r), radius=r, start_angle=180.0, end_angle=270.0, dxfattribs={"layer": layer})


def draw(msp, dims: dict, x_offset: float = 0.0, y_offset: float = 0.0):
    """
    Draw all panels into an ezdxf ModelSpace.

    Each panel is represented as a named BLOCK (PANEL_R{row}_C{col}) and inserted at
    the computed panel origin offset by x_offset/y_offset.
    """
    import ezdxf  # type: ignore  # noqa: F401

    doc = msp.doc
    panel_w = float(dims["panel_width"])
    panel_h = float(dims["panel_height"])
    corner_r = float(dims["corner_radius"])

    cut_w = panel_w + (2.0 * CUTLINE_OFFSET_IN)
    cut_h = panel_h + (2.0 * CUTLINE_OFFSET_IN)
    cut_r = corner_r + CUTLINE_OFFSET_IN

    text_height = max(0.15, min(panel_w, panel_h) * 0.12)

    for piece in dims.get("pieces", []):
        row = int(piece["row"])
        col = int(piece["col"])
        block_name = f"PANEL_R{row}_C{col}"

        if block_name in doc.blocks:
            block = doc.blocks.get(block_name)
        else:
            block = doc.blocks.new(name=block_name)
            _rounded_rect(block, 0.0, 0.0, panel_w, panel_h, corner_r, layer="14")
            _rounded_rect(
                block,
                -CUTLINE_OFFSET_IN,
                -CUTLINE_OFFSET_IN,
                cut_w,
                cut_h,
                cut_r,
                layer="87",
            )
            label = str(piece.get("id", block_name))
            block.add_text(
                label,
                dxfattribs={"layer": "1", "height": text_height},
            ).set_placement((panel_w / 2.0, panel_h / 2.0), align="MIDDLE_CENTER")

        insert_x = x_offset + float(piece["x_origin"])
        insert_y = y_offset + float(piece["y_origin"])
        msp.add_blockref(block_name, (insert_x, insert_y))


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
