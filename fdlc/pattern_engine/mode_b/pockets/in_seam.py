"""In-seam front pocket module.

The pocket opening is hidden in the side seam of the front panel.
The bag is a kidney-shaped piece that hangs behind the front panel,
attached at the opening edges.

Geometry
--------
Opening: a segment of the front side seam, from `drop` inches below waist
         to `drop + length` inches below waist.

Bag: two pieces (front facing + back bag) that together form the pocket.
     - Front facing: a strip along the opening, curves around to the bag.
       This is the piece the hand slides into — it's attached to the front panel.
     - Back bag: the deep bag piece, attached to the front facing around its perimeter.

For IRL construction:
  1. Sew front facing to front panel at side seam opening.
  2. Sew back bag to front facing around the bag perimeter.
  3. Baste bag to waist seam and side seam at top to hold in place.

For CLO3D:
  The in-seam pocket doesn't need to be simulated as separate pieces —
  it's fully contained behind the panel. The side seam seam pair on the
  front panel is split at the opening to allow the CLO seam to skip that
  segment (the opening is left open in the side seam).
  Pocket pieces can be omitted from CLO sim or attached as internal geometry.

Default dimensions (industry standard for a front in-seam pocket):
  drop:   1.5" from waist seam (below waistband)
  length: 7.0" opening
  depth:  10.5" bag depth
  width:  7.5" bag width (at widest)
"""

from __future__ import annotations

import math
from typing import List, Tuple

from ..solvers.pattern_utils import (
    Point, _dist, _polyline_length, _bbox, _cbez, _qbez, _rect_piece,
)
from .pocket_base import (
    _side_seam_points, _side_seam_segment, _walk_perimeter_fraction,
    _nearest_point_on_poly,
)


# Default dimensions
DEFAULTS = {
    "drop": 1.5,       # inches from waist to top of opening
    "length": 7.0,     # inches of opening along side seam
    "depth": 10.5,     # bag depth (vertical)
    "width": 7.5,      # bag width at widest point
    "facing_width": 1.5,  # width of front facing strip
}


def _bag_shape(opening_top: Point, opening_bot: Point, depth: float, width: float) -> List[Point]:
    """Build the pocket bag outline.

    The bag hangs from the opening. Top edge matches opening length.
    Bottom is a smooth curve (kidney shape).

    Returns closed polyline in inches (Y-down, same as solver space).
    """
    olen = _dist(opening_top, opening_bot)

    # Place bag with opening_top at origin for simplicity, then translate
    # Opening runs vertically (Y down), bag extends to the left (into the garment)
    pts = []

    # Top edge: straight across the opening width
    pts.append((0, 0))           # opening top
    pts.append((-width, 0))      # top-left corner of bag

    # Left side + bottom: smooth curve
    curve = _cbez(
        (-width, 0),
        (-width, depth * 0.4),
        (-width * 0.5, depth),
        (0, depth),
        24,
    )
    pts.extend(curve[1:])

    # Right side: straight back up to opening bottom
    pts.append((0, olen))        # opening bottom
    pts.append((0, 0))           # close

    # Translate to actual opening position
    tx, ty = opening_top
    return [(x + tx, y + ty) for x, y in pts]


def _facing_shape(opening_top: Point, opening_bot: Point, facing_width: float) -> List[Point]:
    """Build the front facing (the strip sewn to the panel at the opening).

    It mirrors the opening segment and extends `facing_width` into the bag.
    """
    olen = _dist(opening_top, opening_bot)
    tx, ty = opening_top

    pts = [
        (0, 0),
        (-facing_width, 0),
        (-facing_width, olen),
        (0, olen),
        (0, 0),
    ]
    return [(x + tx, y + ty) for x, y in pts]


def build(panel: dict, measurements: dict, construction: dict) -> dict:
    """Build in-seam front pocket for the given front panel.

    Args:
        panel: front_panel dict from pant_block.solve()
        measurements: measurements dict
        construction: construction dict (may override defaults via in_seam_* keys)

    Returns:
        PocketResult dict:
            opening_lines:   lines to draw on panel (INTERNAL layer)
            opening_notches: notches to add to panel at opening endpoints
            pieces:          [facing_piece, bag_piece]
            side_seam_split: (frac_top, frac_bot) fractions on panel perimeter
                             where the side seam opening is located.
                             Used by clo3d_json to split the side seam pair.
    """
    c = construction
    drop   = float(c.get("in_seam_drop",   DEFAULTS["drop"]))
    length = float(c.get("in_seam_length", DEFAULTS["length"]))
    depth  = float(c.get("in_seam_depth",  DEFAULTS["depth"]))
    width  = float(c.get("in_seam_width",  DEFAULTS["width"]))
    facing_w = float(c.get("in_seam_facing_width", DEFAULTS["facing_width"]))

    # Locate opening on the side seam
    opening_top, opening_bot = _side_seam_segment(panel, drop, length)

    # Opening line drawn on the panel
    opening_line = [opening_top, opening_bot]

    # Notches at opening endpoints (single notch each)
    notches = [
        (opening_top, "pocket_open_top"),
        (opening_bot, "pocket_open_bot"),
    ]

    # Build bag and facing shapes
    bag_pts = _bag_shape(opening_top, opening_bot, depth, width)
    facing_pts = _facing_shape(opening_top, opening_bot, facing_w)

    x0, y0, x1, y1 = _bbox(bag_pts)
    bw, bh = abs(x1 - x0), abs(y1 - y0)

    x0f, y0f, x1f, y1f = _bbox(facing_pts)
    fw, fh = abs(x1f - x0f), abs(y1f - y0f)

    bag_piece = {
        "name": "front_pocket_bag",
        "count": 2,
        "mirror": True,
        "cut": bag_pts,
        "seam_allowance": c.get("seam_allowance", 0.625),
        "hem_allowance": 0.0,
        "grainline": [(x0 + bw * 0.5, y0 + 0.5), (x0 + bw * 0.5, y1 - 0.5)],
        "internal_lines": [],
        "notches": [],
        "label_pos": (x0 + bw / 2, y0 + bh / 2),
        "meta": {
            "pocket_type": "in_seam",
            "opening_length": length,
            "bag_depth": depth,
            "bag_width": width,
        },
    }

    facing_piece = {
        "name": "front_pocket_facing",
        "count": 2,
        "mirror": True,
        "cut": facing_pts,
        "seam_allowance": c.get("seam_allowance", 0.625),
        "hem_allowance": 0.0,
        "grainline": [(x0f + fw * 0.5, y0f + 0.5), (x0f + fw * 0.5, y1f - 0.5)],
        "internal_lines": [],
        "notches": [],
        "label_pos": (x0f + fw / 2, y0f + fh / 2),
        "meta": {"pocket_type": "in_seam_facing"},
    }

    # Compute where the opening falls on the panel perimeter (for CLO3D seam splitting)
    pts = panel["cut"]
    # Remove closing duplicate if present
    closed_pts = pts[:-1] if pts and _dist(pts[0], pts[-1]) < 0.01 else pts
    n = len(closed_pts)
    total_perim = sum(_dist(closed_pts[i], closed_pts[(i + 1) % n]) for i in range(n))

    # Find the two nearest panel vertices to the opening endpoints
    top_idx, _ = _nearest_point_on_poly(closed_pts, opening_top)
    bot_idx, _ = _nearest_point_on_poly(closed_pts, opening_bot)

    # Walk forward from top to bot (side seam direction)
    seg_top = sum(_dist(closed_pts[i], closed_pts[(i + 1) % n])
                  for i in range(top_idx, bot_idx if bot_idx > top_idx else bot_idx + n))
    frac_top = sum(_dist(closed_pts[i], closed_pts[(i + 1) % n])
                   for i in range(0, top_idx)) / total_perim
    frac_bot = frac_top + seg_top / total_perim

    return {
        "opening_lines": [opening_line],
        "opening_notches": notches,
        "pieces": [facing_piece, bag_piece],
        "side_seam_split": (round(frac_top, 4), round(frac_bot, 4)),
        "meta": {
            "pocket_type": "in_seam",
            "drop": drop,
            "length": length,
            "opening_top": opening_top,
            "opening_bot": opening_bot,
        },
    }


__all__ = ["build", "DEFAULTS"]
