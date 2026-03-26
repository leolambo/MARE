"""Back patch pocket module.

A patch pocket is a separate piece sewn onto the outside of the back panel.
No opening cut into the panel — the bag sits on the surface, open at the top.

Geometry
--------
The patch is a rectangle with a curved bottom edge (softens the silhouette).
It's positioned at hip height, centered on the back panel width.

For IRL construction:
  1. Finish top edge of patch (fold/stitch).
  2. Press seam allowance on remaining three sides.
  3. Topstitch patch to back panel on three sides, leaving top open.
  Optional: bar tack at top corners for reinforcement.

For CLO3D:
  The patch is a separate pattern piece placed on the back panel surface.
  It's sewn around three sides (bottom + two sides) via internal seam pairs.
  The top is left open (no seam pair there).

Default dimensions (standard back patch for pants):
  width:       6.0" (pocket width)
  height:      6.5" (pocket height)
  corner_r:    1.0" radius on bottom corners
  drop:        3.5" from waist seam to top of pocket
  center_x:    centered on panel (default)
  topstitch:   0.25" parallel line drawn inside patch for DXF
"""

from __future__ import annotations

import math
from typing import List, Optional

from ..solvers.pattern_utils import (
    Point, _dist, _bbox, _cbez, _qbez, _closed_offset,
)
from .pocket_base import _side_seam_points


# Default dimensions
DEFAULTS = {
    "width": 6.0,
    "height": 6.5,
    "corner_r": 0.75,
    "drop": 3.5,
    "topstitch": 0.25,
}


def _rounded_rect(x0: float, y0: float, w: float, h: float, r: float) -> List[Point]:
    """Rectangle with rounded bottom corners. Top edge is straight (pocket opening).

    Origin: top-left = (x0, y0), Y increases downward.
    Corners: bottom-left and bottom-right are rounded with radius r.
    """
    r = min(r, w / 2, h / 2)
    pts = []

    # Top-left → top-right (straight, this is the opening)
    pts.append((x0, y0))
    pts.append((x0 + w, y0))

    # Top-right → bottom-right corner (straight)
    pts.append((x0 + w, y0 + h - r))

    # Bottom-right curve
    arc = _cbez(
        (x0 + w, y0 + h - r),
        (x0 + w, y0 + h - r * 0.2),
        (x0 + w - r * 0.2, y0 + h),
        (x0 + w - r, y0 + h),
        12,
    )
    pts.extend(arc[1:])

    # Bottom edge (straight across)
    pts.append((x0 + r, y0 + h))

    # Bottom-left curve
    arc = _cbez(
        (x0 + r, y0 + h),
        (x0 + r * 0.2, y0 + h),
        (x0, y0 + h - r * 0.2),
        (x0, y0 + h - r),
        12,
    )
    pts.extend(arc[1:])

    # Bottom-left → top-left (straight)
    pts.append((x0, y0))

    return pts


def _panel_center_x(panel: dict) -> float:
    """Find the horizontal center of the panel in the region around hip depth."""
    pts = panel["cut"]
    ys = [p[1] for p in pts]
    min_y = min(ys)
    # Hip is roughly 8.5" down from waist
    hip_y = min_y + 8.5
    hip_pts = [p[0] for p in pts if abs(p[1] - hip_y) < 3.0]
    if not hip_pts:
        xs = [p[0] for p in pts]
        return (max(xs) + min(xs)) / 2
    return (max(hip_pts) + min(hip_pts)) / 2


def build(panel: dict, measurements: dict, construction: dict) -> dict:
    """Build back patch pocket for the given back panel.

    Args:
        panel: back_panel dict from pant_block.solve()
        measurements: measurements dict
        construction: construction dict (may override defaults via patch_* keys)

    Returns:
        PocketResult dict:
            opening_lines:   placement outline drawn on panel (INTERNAL layer)
            opening_notches: corner notches for placement registration
            pieces:          [patch_piece]
            placement:       (center_x, top_y) in panel coordinates
    """
    c = construction
    width    = float(c.get("patch_width",    DEFAULTS["width"]))
    height   = float(c.get("patch_height",   DEFAULTS["height"]))
    corner_r = float(c.get("patch_corner_r", DEFAULTS["corner_r"]))
    drop     = float(c.get("patch_drop",     DEFAULTS["drop"]))
    topstitch = float(c.get("patch_topstitch", DEFAULTS["topstitch"]))

    # Placement: centered on back panel at `drop` inches below waist
    pts = panel["cut"]
    ys = [p[1] for p in pts]
    waist_y = min(ys)  # Y-down: waist is at min Y
    top_y = waist_y + drop
    center_x = _panel_center_x(panel)
    x0 = center_x - width / 2

    # Pocket outline on the panel (placement guide)
    placement_outline = _rounded_rect(x0, top_y, width, height, corner_r)

    # Topstitch line: same shape inset by topstitch distance
    # _closed_offset sign depends on winding; try both, keep whichever is smaller
    try:
        ts_neg = _closed_offset(placement_outline, -topstitch)
        ts_pos = _closed_offset(placement_outline, topstitch)
        from ..solvers.pattern_utils import _bbox as _b
        n0, n1 = _b(ts_neg)[0], _b(ts_neg)[2]
        p0, p1 = _b(ts_pos)[0], _b(ts_pos)[2]
        o0, o1 = _b(placement_outline)[0], _b(placement_outline)[2]
        # Pick the one whose X span is smaller (inset, not outset)
        topstitch_line = ts_neg if abs(n1 - n0) < abs(o1 - o0) else ts_pos
    except Exception:
        topstitch_line = []

    # Notches at top corners for placement registration
    notches = [
        ((x0, top_y), "patch_top_left"),
        ((x0 + width, top_y), "patch_top_right"),
    ]

    # The patch piece itself (cut separately, applied to panel surface)
    # Add seam allowance to three sides (bottom + sides), not top opening
    sa = c.get("seam_allowance", 0.625)
    hem_top = 1.0  # folded hem at top opening

    # Patch piece origin at (0, 0) for clean DXF placement
    patch_pts = _rounded_rect(0, hem_top, width, height, corner_r)

    x0p, y0p, x1p, y1p = _bbox(patch_pts)
    bw, bh = abs(x1p - x0p), abs(y1p - y0p)

    # Topstitch line on the patch piece itself (inset)
    try:
        ts_neg = _closed_offset(patch_pts, -topstitch)
        ts_pos = _closed_offset(patch_pts, topstitch)
        from ..solvers.pattern_utils import _bbox as _b
        n0, n1 = _b(ts_neg)[0], _b(ts_neg)[2]
        p0, p1 = _b(ts_pos)[0], _b(ts_pos)[2]
        o0, o1 = _b(patch_pts)[0], _b(patch_pts)[2]
        patch_topstitch = ts_neg if abs(n1 - n0) < abs(o1 - o0) else ts_pos
    except Exception:
        patch_topstitch = []

    patch_piece = {
        "name": "back_pocket_patch",
        "count": 2,
        "mirror": False,   # same shape both sides, no mirroring needed
        "cut": patch_pts,
        "seam_allowance": sa,
        "hem_allowance": 0.0,
        "grainline": [(bw / 2, hem_top + 0.5), (bw / 2, y1p - 0.5)],
        "internal_lines": [patch_topstitch] if patch_topstitch else [],
        "notches": [
            ((0, hem_top), "top_left"),
            ((width, hem_top), "top_right"),
        ],
        "label_pos": (bw / 2, hem_top + bh / 2),
        "meta": {
            "pocket_type": "patch",
            "width": width,
            "height": height,
            "corner_r": corner_r,
            "hem_top": hem_top,
            "topstitch": topstitch,
            "sewing_note": (
                "Fold and press top hem 1\". "
                "Press SA on remaining three sides. "
                "Topstitch to back panel on three sides. "
                "Bar tack at top corners."
            ),
        },
    }

    return {
        "opening_lines": [placement_outline],
        "opening_notches": notches,
        "pieces": [patch_piece],
        "placement": {"center_x": center_x, "top_y": top_y},
        "meta": {
            "pocket_type": "patch",
            "drop": drop,
            "width": width,
            "height": height,
        },
    }


__all__ = ["build", "DEFAULTS"]
