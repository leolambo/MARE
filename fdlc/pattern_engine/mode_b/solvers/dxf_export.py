#!/usr/bin/env python3
"""DXF export implementation for Mode B pant block solver."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from .annotate_dxf import (
    _add_grain_arrowhead,
    _add_notch_mark,
    _annotate_main_panel,
    _nearest_index,
    _vnorm,
)
from .pattern_utils import (
    LAYER_CUT,
    LAYER_GRAIN,
    LAYER_INTERNAL,
    LAYER_NOTCH,
    LAYER_SA,
    LAYER_TEXT,
    _TEXT_ALIGN,
    _bbox,
    _dist,
    _translate,
)


def _add_layers(doc) -> None:
    for name, color, lt in [
        (LAYER_CUT, 7, "CONTINUOUS"),
        (LAYER_SA, 8, "DASHED"),
        (LAYER_GRAIN, 3, "CENTER"),
        (LAYER_NOTCH, 1, "CONTINUOUS"),
        (LAYER_INTERNAL, 6, "DOTTED"),
        (LAYER_TEXT, 2, "CONTINUOUS"),
    ]:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color, linetype=lt)


def _draw_poly(msp, points, layer, closed=False):
    pts = points[:-1] if closed and points and points[0] == points[-1] else points
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, **({"closed": True} if closed else {})})


def to_dxf(solution: dict, output_path: str) -> str:
    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 1
    _add_layers(doc)
    msp = doc.modelspace()

    cx = 0.0
    cy = 0.0
    row_h = 0.0

    for piece in solution["pieces"]:
        cut = piece["cut"]
        x0, y0, x1, y1 = _bbox(cut)
        w = x1 - x0
        h = y1 - y0
        dx, dy = -x0 + cx, -y0 + cy

        tc = [(x+dx, y+dy) for x, y in cut]
        ts = [(x+dx, y+dy) for x, y in piece.get("seam_outline", [])]

        _draw_poly(msp, tc, LAYER_CUT, closed=True)
        if ts:
            _draw_poly(msp, ts, LAYER_SA, closed=True)

        for line in piece.get("internal_lines", []):
            _draw_poly(msp, [(x+dx, y+dy) for x, y in line], LAYER_INTERNAL)

        grain = piece.get("grainline")
        if grain:
            tg = _translate(grain, dx, dy)
            _draw_poly(msp, tg, LAYER_GRAIN)
            if len(tg) >= 2:
                _add_grain_arrowhead(msp, tg[0], (tg[0][0]-tg[1][0], tg[0][1]-tg[1][1]))
                _add_grain_arrowhead(msp, tg[-1], (tg[-1][0]-tg[-2][0], tg[-1][1]-tg[-2][1]))

        closed_pts = tc[:-1] if tc and _dist(tc[0], tc[-1]) < 0.01 else tc
        for (nx, ny), _label in piece.get("notches", []):
            p = (nx+dx, ny+dy)
            idx = _nearest_index(closed_pts, p)
            n_pts = len(closed_pts)
            tan = _vnorm((
                closed_pts[(idx+1) % n_pts][0] - closed_pts[(idx-1) % n_pts][0],
                closed_pts[(idx+1) % n_pts][1] - closed_pts[(idx-1) % n_pts][1],
            ))
            _add_notch_mark(msp, p, tan, count=1)

        if piece["name"] in ("front_panel", "back_panel"):
            translated_piece = dict(piece)
            lx, ly = piece["label_pos"]
            translated_piece["label_pos"] = (lx + dx, ly + dy)
            _annotate_main_panel(
                msp,
                translated_piece,
                tc,
                dy,
                solution.get("measurements", {}),
                is_front=(piece["name"] == "front_panel"),
            )
        else:
            lx, ly = piece["label_pos"]
            msp.add_text(
                piece["name"].replace("_", " ").title(),
                dxfattribs={"layer": LAYER_TEXT, "height": 0.25},
            ).set_placement((lx+dx, ly+dy), align=_TEXT_ALIGN)

        cx += w + 3.0
        row_h = max(row_h, h)
        if cx > 70:
            cx = 0
            cy += row_h + 2.0
            row_h = 0

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out))
    return str(out)


__all__ = ["to_dxf", "_add_layers", "_draw_poly"]
