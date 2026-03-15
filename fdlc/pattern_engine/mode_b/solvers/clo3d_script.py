"""
CLO3D Python Script — Auto-create trouser pattern + auto-sew.

Usage: CLO3D > Edit > Python Script > Run Python Script > browse to this file.
Start with a CLEAN scene (File > New).
"""

import pattern_api

# ============================================================================
# MEASUREMENTS
# ============================================================================
MEASUREMENTS = {
    "waist": 30.0,
    "hip": 52.0,
    "front_rise": 12.75,
    "back_rise": 14.75,
    "inseam": 28.5,
    "outseam": 40.5,
    "leg_opening": 23.5,
}

# ============================================================================
# HELPERS
# ============================================================================

INCH_TO_MM = 25.4

def inch_to_clo(x_in, y_in):
    return (round(x_in * INCH_TO_MM, 2), round(-y_in * INCH_TO_MM, 2))

def cbez(p0, p1, p2, p3):
    x0, y0 = inch_to_clo(*p0)
    x1, y1 = inch_to_clo(*p1)
    x2, y2 = inch_to_clo(*p2)
    x3, y3 = inch_to_clo(*p3)
    return [(x0, y0, 0), (x1, y1, 3), (x2, y2, 3), (x3, y3, 0)]

def lp(x_in, y_in):
    x, y = inch_to_clo(x_in, y_in)
    return (x, y, 0)

def strip_close(pts):
    if len(pts) > 1 and pts[0][0] == pts[-1][0] and pts[0][1] == pts[-1][1]:
        return pts[:-1]
    return pts

def get_line_count(pattern_idx):
    for i in range(100):
        try:
            pattern_api.GetLineLength(pattern_idx, i)
        except:
            return i
    return 0

# ============================================================================
# FRONT PANEL
# Each bezier span (on-curve → ctrl → ctrl → on-curve) = 1 CLO3D "line"
# Straight segments (on-curve → on-curve) = 1 CLO3D "line"
# We track line indices as we build.
# ============================================================================

def build_front(m):
    hip_y = 8.5
    CY = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    wh = m["waist"] / 2.0
    hh = m["hip"] / 2.0
    fw = wh * 0.48 + 1.0
    fhip = hh * 0.48 + 0.5
    fhem = m["leg_opening"] * 0.48
    fcx = hh * 0.125
    xsh = fhip
    xsk = fhem + 0.3
    xse = fhem
    ct = (-fcx, CY + 1.0)
    cfw = (0, 0.75)
    sw = (fw, -0.5)

    pts = []
    line_map = {}
    line_idx = 0

    # Line 0: waist curve (bezier)
    pts.extend(cbez(cfw, (fw*0.3, -0.8), (fw*0.65, -0.7), sw))
    line_map["waist"] = line_idx
    line_idx += 1

    # Line 1: side waist-to-hip (bezier)
    pts.extend(cbez(sw, (xsh*0.7, hip_y*0.3), (xsh, hip_y*0.7), (xsh, hip_y))[1:])
    line_map["side_top"] = line_idx
    line_idx += 1

    # Line 2: side hip-to-knee (bezier)
    pts.extend(cbez((xsh, hip_y), (xsh, hip_y+3), (xsk, knee_y-5), (xsk, knee_y))[1:])
    line_map["side_bot"] = line_idx
    line_idx += 1

    # Line 3: knee to hem (straight)
    pts.append(lp(xse, hem_y))
    line_map["side_hem"] = line_idx
    line_idx += 1

    # Line 4: hem across (straight)
    pts.append(lp(0, hem_y))
    line_map["hem"] = line_idx
    line_idx += 1

    # Line 5: inseam hem to knee (straight)
    pts.append(lp(0, knee_y))
    line_map["inseam_straight"] = line_idx
    line_idx += 1

    # Line 6: inseam knee to crotch (bezier)
    pts.extend(cbez((0, knee_y), (0.1, knee_y-6), (-fcx*0.5, ct[1]+3), ct)[1:])
    line_map["inseam_curve"] = line_idx
    line_idx += 1

    # Line 7: crotch curve (bezier)
    pts.extend(cbez(ct, (-fcx, CY+0.1), (-fcx*0.5, CY), (0, CY))[1:])
    line_map["crotch"] = line_idx
    line_idx += 1

    # Lines 8-11: CF seam straight segments
    cf_start = line_idx
    steps = 4
    for i in range(steps - 1, 0, -1):
        t = i / steps
        y = CY * t + cfw[1] * (1 - t)
        pts.append(lp(0, y))
        line_idx += 1
    line_map["cf_seam"] = list(range(cf_start, line_idx))

    # Line closing: last point back to first (auto by CLO3D)
    line_map["cf_close"] = line_idx  # the auto-closing segment

    return tuple(strip_close(pts)), line_map

# ============================================================================
# BACK PANEL
# ============================================================================

def build_back(m, b_drop=1.9):
    hip_y = 8.5
    CY = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    wh = m["waist"] / 2.0
    hh = m["hip"] / 2.0
    bw = wh * 0.52 - 1.0
    bhip = hh * 0.52 + 1.5 - 3.4
    bhem = m["leg_opening"] * 0.52
    bcx = hh * 0.125 + 1.5
    xsh = bhip
    xsk = bhem + 0.3
    xse = bhem
    ct = (-bcx, CY + b_drop)
    cfw = (-2.0, -1.5)
    sw = (bw - 2.0, -0.3)

    pts = []
    line_map = {}
    line_idx = 0

    # Line 0: waist curve
    pts.extend(cbez(cfw, (cfw[0]+bw*0.3, -1.2), (cfw[0]+bw*0.7, -0.6), sw))
    line_map["waist"] = line_idx
    line_idx += 1

    # Line 1: side waist-to-hip
    pts.extend(cbez(sw, (xsh*0.7, hip_y*0.3), (xsh, hip_y*0.7), (xsh, hip_y))[1:])
    line_map["side_top"] = line_idx
    line_idx += 1

    # Line 2: side hip-to-knee
    pts.extend(cbez((xsh, hip_y), (xsh, hip_y+3), (xsk, knee_y-5), (xsk, knee_y))[1:])
    line_map["side_bot"] = line_idx
    line_idx += 1

    # Line 3: knee to hem
    pts.append(lp(xse, hem_y))
    line_map["side_hem"] = line_idx
    line_idx += 1

    # Line 4: hem across
    pts.append(lp(0, hem_y))
    line_map["hem"] = line_idx
    line_idx += 1

    # Line 5: inseam hem to knee
    pts.append(lp(0, knee_y))
    line_map["inseam_straight"] = line_idx
    line_idx += 1

    # Line 6: inseam knee to crotch
    pts.extend(cbez((0, knee_y), (0.1, knee_y-6), (-bcx*0.3, ct[1]+3), ct)[1:])
    line_map["inseam_curve"] = line_idx
    line_idx += 1

    # Line 7: crotch J-curve
    pts.extend(cbez(ct, (-bcx*0.5, CY+0.3), (-bcx*0.2, CY), (0, CY))[1:])
    line_map["crotch"] = line_idx
    line_idx += 1

    # Line 8: CB seam (bezier)
    pts.extend(cbez((0, CY), (-0.5, CY*0.6), (-1.5, CY*0.3), cfw)[1:])
    line_map["cb_seam"] = line_idx
    line_idx += 1

    # Auto-close adds line_idx as closing segment
    line_map["cb_close"] = line_idx

    return tuple(strip_close(pts)), line_map

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 50)
    print("MARE Pattern Engine v3 — Auto-Sew")
    print("=" * 50)

    m = MEASUREMENTS
    pre = pattern_api.GetPatternCount()

    front_pts, f_map = build_front(m)
    back_pts, b_map = build_back(m)

    print("Front: " + str(len(front_pts)) + " pts")
    print("Back:  " + str(len(back_pts)) + " pts")

    # Create panels
    print("Creating front...")
    pattern_api.CreatePatternWithPoints(front_pts)
    c1 = pattern_api.GetPatternCount()

    print("Creating back...")
    back_offset = tuple((x + 500, y, t) for x, y, t in back_pts)
    pattern_api.CreatePatternWithPoints(back_offset)
    c2 = pattern_api.GetPatternCount()

    created = c2 - pre
    print("Created: " + str(created) + " panels")

    if created < 2:
        print("ERROR: expected 2 panels")
        return

    fi = c2 - 2
    bi = c2 - 1
    print("Front idx: " + str(fi))
    print("Back idx:  " + str(bi))

    # Verify line counts
    f_lines = get_line_count(fi)
    b_lines = get_line_count(bi)
    print("Front lines: " + str(f_lines))
    print("Back lines:  " + str(b_lines))

    # Print line lengths for debugging
    print("")
    print("--- FRONT LINES ---")
    for i in range(f_lines):
        try:
            ln = pattern_api.GetLineLength(fi, i)
            print("  " + str(i) + ": " + str(round(ln, 1)) + "mm")
        except:
            pass

    print("")
    print("--- BACK LINES ---")
    for i in range(b_lines):
        try:
            ln = pattern_api.GetLineLength(bi, i)
            print("  " + str(i) + ": " + str(round(ln, 1)) + "mm")
        except:
            pass

    # Print expected mapping
    print("")
    print("--- EXPECTED LINE MAP ---")
    print("Front: " + str(f_map))
    print("Back:  " + str(b_map))

    # ================================================================
    # AUTO-SEW
    # Seam pairs based on our build order:
    #   side_top + side_bot + side_hem = full side seam
    #   inseam_straight + inseam_curve = full inseam
    #   crotch + cf/cb seam = center seam
    #   waist = waist
    # ================================================================
    print("")
    print("--- AUTO-SEWING ---")

    sew_pairs = [
        # (name, front_lines, back_lines, dir_a, dir_b)
        ("side_top", f_map["side_top"], b_map["side_top"], True, True),
        ("side_bot", f_map["side_bot"], b_map["side_bot"], True, True),
        ("side_hem", f_map["side_hem"], b_map["side_hem"], True, True),
        ("inseam_straight", f_map["inseam_straight"], b_map["inseam_straight"], True, True),
        ("inseam_curve", f_map["inseam_curve"], b_map["inseam_curve"], True, True),
        ("crotch", f_map["crotch"], b_map["crotch"], True, True),
        ("waist", f_map["waist"], b_map["waist"], True, True),
    ]

    for name, f_line, b_line, da, db in sew_pairs:
        try:
            ok = pattern_api.AddSeamlinePairGroup(fi, f_line, bi, 0, b_line, da, db)
            status = "OK" if ok else "FAIL"
        except Exception as e:
            status = "ERR: " + str(e)
        print("  " + name + " (F:" + str(f_line) + " B:" + str(b_line) + "): " + status)

    print("")
    print("Done! Check 2D window for sewing lines.")
    print("If sewing looks wrong, compare line lengths above to find correct pairs.")

main()
