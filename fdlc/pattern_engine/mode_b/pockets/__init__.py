"""Pocket modules for Mode B pant block solver.

Each module exposes a single function:
    build(panel, measurements, construction) -> PocketResult

PocketResult is a dict:
    opening_lines:  list of [(x,y)...] to draw on the parent panel (INTERNAL layer)
    opening_notches: list of ((x,y), label) to add to parent panel
    pieces:         list of pattern piece dicts (same schema as pant_block pieces)
    clo3d_seams:    list of seam spec dicts for injection into generate_5panel_json
                    Each: {name, panel_role, frac_start, frac_end, bag_piece, bag_frac_start, bag_frac_end}

Available modules:
    in_seam   - hidden front pocket, opening in side seam
    patch     - back patch pocket, applied to panel surface
    slash     - (future) angled slash opening at side seam area
    welt      - (future) single-welt bound buttonhole style
"""

from .in_seam import build as in_seam
from .patch import build as patch

__all__ = ["in_seam", "patch"]
