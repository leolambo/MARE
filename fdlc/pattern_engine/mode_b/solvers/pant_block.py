#!/usr/bin/env python3
"""Trouser block solver for Mode B parametric generation.
v21 — validated via visual verification loop (see PATTERN-DRAFTING-FINDINGS.md)."""

from __future__ import annotations

import json
import math

from .annotate_dxf import (
    _add_grain_arrowhead,
    _add_notch_mark,
    _add_seam_number,
    _annotate_main_panel,
    _nearest_index,
    _seam_midpoint,
    _vmid,
    _vnorm,
    _vperp,
)
from .dxf_export import _add_layers, _draw_poly, to_dxf
from ..pockets import in_seam as _pocket_in_seam, patch as _pocket_patch
from .pattern_utils import (
    DEFAULT_CONSTRUCTION,
    DEFAULT_EASE,
    LAYER_CUT,
    LAYER_GRAIN,
    LAYER_INTERNAL,
    LAYER_NOTCH,
    LAYER_SA,
    LAYER_TEXT,
    Point,
    _TEXT_ALIGN,
    _bbox,
    _cbez,
    _closed_offset,
    _dist,
    _polyline_length,
    _qbez,
    _rect_piece,
    _translate,
)


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def _build_front_panel(m: dict, c: dict, e: dict) -> dict:
    """Build front trouser panel using validated v21 geometry."""
    hip_y = 8.5
    CROTCH_Y = float(m["front_rise"])
    hem_y = float(m["outseam"])
    knee_y = hem_y - float(m["inseam"]) * 0.52

    waist_half = float(m["waist"]) / 2.0
    hip_half = float(m["hip"])  # already flat (half circumference) — do NOT halve again

    f_waist = waist_half * 0.48 + 1.0
    f_hip = hip_half * 0.48 + 0.5
    f_hem = float(m["leg_opening"]) * 0.48
    f_cext = hip_half * 0.125

    x_sh = f_hip
    x_sk = f_hem + 0.3
    x_se = f_hem

    ct = (-f_cext, CROTCH_Y + 1.0)

    cf_w = (0, 0.75)
    sw = (f_waist, -0.5)
    wc = _cbez(cf_w, (f_waist*0.3, -0.8), (f_waist*0.65, -0.7), sw, 16)

    cf_seam = [(0, cf_w[1] + i*(CROTCH_Y-cf_w[1])/10) for i in range(11)]
    cc = _cbez((0, CROTCH_Y), (-f_cext*0.5, CROTCH_Y), (-f_cext, CROTCH_Y+0.1), ct, 32)
    ic = _cbez(ct, (-f_cext*0.5, ct[1]+3), (0.1, knee_y-6), (0, knee_y), 32)

    st = _cbez(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y), 24)
    sm = _cbez((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y), 24)

    inseam_len = _polyline_length(ic) + abs(hem_y - knee_y)
    side_len = _polyline_length(st) + _polyline_length(sm) + math.hypot(x_sk-x_se, knee_y-hem_y)

    outline = list(wc)
    outline += st[1:]
    outline += sm[1:]
    outline += [(x_se, hem_y), (0, hem_y), (0, knee_y)]
    outline += list(reversed(ic))[1:]
    outline += list(reversed(cc))[1:]
    outline += list(reversed(cf_seam))[1:]
    outline += [wc[0]]

    x0, y0, x1, y1 = _bbox(outline)
    grain_x = f_hem / 2.0

    return {
        "name": "front_panel",
        "count": 2,
        "mirror": True,
        "cut": outline,
        "grainline": [(grain_x, hip_y), (grain_x, hem_y - 2.0)],
        "internal_lines": [],   # pocket lines injected by solve()
        "notches": [((x_sk, knee_y), "knee"), ((0, knee_y), "knee")],
        "label_pos": ((x0+x1)/2, (y0+y1)/2),
        "meta": {
            "crotch_extension": f_cext,
            "inseam_length": inseam_len,
            "side_length": side_len,
            "hem_width": f_hem,
            "hip_width": f_hip,
            "side_seam_waist": sw,
            "side_seam_hem": (x_se, hem_y),
        },
    }


def _build_back_panel(m: dict, c: dict, e: dict, b_drop: float = 1.9) -> dict:
    """Build back trouser panel using validated v21 geometry."""
    hip_y = 8.5
    CROTCH_Y = float(m["front_rise"])
    hem_y = float(m["outseam"])
    knee_y = hem_y - float(m["inseam"]) * 0.52

    waist_half = float(m["waist"]) / 2.0
    hip_half = float(m["hip"])  # already flat (half circumference) — do NOT halve again

    b_waist = waist_half * 0.52 - 1.0
    b_hip = hip_half * 0.52 + 1.5 - 3.4
    b_hem = float(m["leg_opening"]) * 0.52
    b_cext = hip_half * 0.125 + 1.5

    x_sh = b_hip
    x_sk = b_hem + 0.3
    x_se = b_hem

    ct = (-b_cext, CROTCH_Y + b_drop)

    cf_w = (-2.0, -1.5)
    sw = (b_waist - 2.0, -0.3)
    wc = _cbez(cf_w, (cf_w[0]+b_waist*0.3, -1.2), (cf_w[0]+b_waist*0.7, -0.6), sw, 16)

    cb_to_crotch = _cbez(cf_w, (-1.0, CROTCH_Y*0.5), (-1.0, CROTCH_Y), ct, 48)
    ic = _cbez(ct, (-b_cext*0.3, ct[1]+3), (0.1, knee_y-6), (0, knee_y), 32)

    st = _cbez(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y), 24)
    sm = _cbez((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y), 24)

    inseam_len = _polyline_length(ic) + abs(hem_y - knee_y)
    side_len = _polyline_length(st) + _polyline_length(sm) + math.hypot(x_sk-x_se, knee_y-hem_y)

    outline = list(wc)
    outline += st[1:]
    outline += sm[1:]
    outline += [(x_se, hem_y), (0, hem_y), (0, knee_y)]
    outline += list(reversed(ic))[1:]
    outline += list(reversed(cb_to_crotch))[1:]
    outline += [wc[0]]

    x0, y0, x1, y1 = _bbox(outline)
    grain_x = b_hem / 2.0

    return {
        "name": "back_panel",
        "count": 2,
        "mirror": True,
        "cut": outline,
        "grainline": [(grain_x, hip_y), (grain_x, hem_y - 2.0)],
        "internal_lines": [],   # pocket lines injected by solve()
        "notches": [((x_sk, knee_y), "knee"), ((0, knee_y), "knee")],
        "label_pos": ((x0+x1)/2, (y0+y1)/2),
        "meta": {
            "crotch_extension": b_cext,
            "inseam_length": inseam_len,
            "side_length": side_len,
            "hem_width": b_hem,
            "hip_width": b_hip,
            "b_drop": b_drop,
        },
    }


def _match_seams(m: dict, c: dict, e: dict) -> tuple:
    """Build front, then adjust back b_drop until inseams match."""
    front = _build_front_panel(m, c, e)
    target_inseam = front["meta"]["inseam_length"]

    best_drop = 1.9
    best_err = 999
    for d10 in range(5, 45):
        d = d10 * 0.1
        back = _build_back_panel(m, c, e, b_drop=d)
        err = abs(back["meta"]["inseam_length"] - target_inseam)
        if err < best_err:
            best_err = err
            best_drop = d

    back = _build_back_panel(m, c, e, b_drop=best_drop)
    return front, back


def solve(measurements: dict, construction: dict | None = None, ease: dict | None = None) -> dict:
    """Main solver entry point."""
    c = {**DEFAULT_CONSTRUCTION, **(construction or {})}
    e = {**DEFAULT_EASE, **(ease or {})}
    m = dict(measurements)

    required = ["waist", "hip", "front_rise", "inseam", "outseam", "thigh", "leg_opening", "fly_length"]
    missing = [k for k in required if m.get(k) in (None, "")]
    if missing:
        raise ValueError(f"Missing measurements: {', '.join(missing)}")

    m["back_rise"] = float(m.get("back_rise") or (float(m["front_rise"]) + 2.0))
    if m.get("knee") in (None, ""):
        m["knee"] = (float(m["thigh"]) + float(m["leg_opening"])) / 2.0

    front, back = _match_seams(m, c, e)

    wb_len = float(m["waist"]) + e["waist"] + c["seam_allowance"] * 2.0
    wb_h = c["waistband_width"] * 2.0
    waistband = _rect_piece("waistband", wb_len/2, wb_h, count=1, fold=True)

    fly_len = float(m["fly_length"])
    fly_shield = {
        "name": "fly_shield",
        "count": 1,
        "mirror": False,
        "cut": [(0, 0), (2.5, 0)] + _qbez((2.5, 0), (1.7, fly_len*0.65), (0.5, fly_len), 20) + [(0, fly_len), (0, 0)],
        "grainline": [(1.25, 0.5), (1.25, fly_len-0.5)],
        "internal_lines": [],
        "notches": [],
        "label_pos": (1.25, fly_len*0.45),
        "meta": {},
    }
    fly_ext = _rect_piece("fly_extension", 1.5, fly_len)
    belt_loop = _rect_piece("belt_loop_strip", 17.5, 1.5)

    # ── Pocket modules ────────────────────────────────────────────────────
    front_pocket_result = None
    back_pocket_result = None
    extra_pieces = []

    front_pocket_type = c.get("pocket_type", "in_seam")
    back_pocket_type = c.get("back_pocket_type", "patch")

    if front_pocket_type == "in_seam":
        front_pocket_result = _pocket_in_seam(front, m, c)
        front["internal_lines"].extend(front_pocket_result["opening_lines"])
        front["notches"].extend(front_pocket_result["opening_notches"])
        extra_pieces.extend(front_pocket_result["pieces"])

    if back_pocket_type == "patch":
        back_pocket_result = _pocket_patch(back, m, c)
        back["internal_lines"].extend(back_pocket_result["opening_lines"])
        back["notches"].extend(back_pocket_result["opening_notches"])
        extra_pieces.extend(back_pocket_result["pieces"])

    pieces = [front, back, waistband, fly_shield, fly_ext, belt_loop] + extra_pieces

    for piece in pieces:
        piece["seam_allowance"] = c["seam_allowance"]
        piece["hem_allowance"] = c["hem_allowance"] if "panel" in piece["name"] else 0.0
        try:
            piece["seam_outline"] = _closed_offset(piece["cut"], c["seam_allowance"])
        except Exception:
            piece["seam_outline"] = []

    return {
        "garment_type": "wide_leg_pants",
        "unit": "inches",
        "measurements": m,
        "construction": c,
        "ease": e,
        "pieces": pieces,
        "pockets": {
            "front": front_pocket_result,
            "back": back_pocket_result,
        },
        "validation": {
            "front_inseam": round(front["meta"]["inseam_length"], 3),
            "back_inseam": round(back["meta"]["inseam_length"], 3),
            "front_side": round(front["meta"]["side_length"], 3),
            "back_side": round(back["meta"]["side_length"], 3),
            "inseam_delta": round(abs(front["meta"]["inseam_length"] - back["meta"]["inseam_length"]), 3),
            "side_delta": round(abs(front["meta"]["side_length"] - back["meta"]["side_length"]), 3),
            "b_drop": back["meta"]["b_drop"],
        },
    }


__all__ = [
    "solve",
    "to_dxf",
    "DEFAULT_CONSTRUCTION",
    "DEFAULT_EASE",
    "LAYER_CUT",
    "LAYER_SA",
    "LAYER_GRAIN",
    "LAYER_NOTCH",
    "LAYER_INTERNAL",
    "LAYER_TEXT",
    "Point",
    "_TEXT_ALIGN",
    "_qbez",
    "_cbez",
    "_dist",
    "_polyline_length",
    "_bbox",
    "_closed_offset",
    "_rect_piece",
    "_translate",
    "_vnorm",
    "_vperp",
    "_vmid",
    "_nearest_index",
    "_seam_midpoint",
    "_add_notch_mark",
    "_add_grain_arrowhead",
    "_add_seam_number",
    "_annotate_main_panel",
    "_add_layers",
    "_draw_poly",
    "_build_front_panel",
    "_build_back_panel",
    "_match_seams",
]


if __name__ == "__main__":
    sample = {
        "waist": 30.0,
        "hip": 52.0,
        "front_rise": 12.75,
        "back_rise": 14.75,
        "inseam": 28.5,
        "outseam": 40.5,
        "thigh": 28.0,
        "leg_opening": 23.5,
        "fly_length": 10.0,
    }
    sol = solve(sample, DEFAULT_CONSTRUCTION, DEFAULT_EASE)
    print(json.dumps(sol["validation"], indent=2))
