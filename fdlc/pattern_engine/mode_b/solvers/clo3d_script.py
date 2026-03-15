"""
CLO3D Python Script — Auto-create trouser pattern with sewing.

Usage: In CLO3D: Edit > Python Script > Run Python Script > browse to this file.
Creates front + back panels with native curves, dumps line indices for sewing.

NOTE: This runs INSIDE CLO3D's Python environment.
Uses CLO's built-in pattern_api, utility_api, etc.
"""

import pattern_api

# ============================================================================
# MEASUREMENTS — edit these for different sizes/silhouettes
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
# COORDINATE HELPERS
# ============================================================================

INCH_TO_MM = 25.4

def inch_to_clo(x_in, y_in):
    return (round(x_in * INCH_TO_MM, 2), round(-y_in * INCH_TO_MM, 2))

def cbez_points(p0, p1, p2, p3):
    x0, y0 = inch_to_clo(*p0)
    x1, y1 = inch_to_clo(*p1)
    x2, y2 = inch_to_clo(*p2)
    x3, y3 = inch_to_clo(*p3)
    return [
        (x0, y0, 0),
        (x1, y1, 3),
        (x2, y2, 3),
        (x3, y3, 0),
    ]

def line_point(x_in, y_in):
    x, y = inch_to_clo(x_in, y_in)
    return (x, y, 0)

def strip_closing(points):
    if len(points) > 1:
        if points[0][0] == points[-1][0] and points[0][1] == points[-1][1]:
            return points[:-1]
    return points

# ============================================================================
# FRONT PANEL
# ============================================================================

def build_front_points(m):
    hip_y = 8.5
    CROTCH_Y = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    waist_half = m["waist"] / 2.0
    hip_half = m["hip"] / 2.0
    f_waist = waist_half * 0.48 + 1.0
    f_hip = hip_half * 0.48 + 0.5
    f_hem = m["leg_opening"] * 0.48
    f_cext = hip_half * 0.125
    x_sh = f_hip
    x_sk = f_hem + 0.3
    x_se = f_hem
    ct = (-f_cext, CROTCH_Y + 1.0)
    cf_w = (0, 0.75)
    sw = (f_waist, -0.5)

    points = []
    # Waist curve
    points.extend(cbez_points(cf_w, (f_waist*0.3, -0.8), (f_waist*0.65, -0.7), sw))
    # Side waist to hip
    points.extend(cbez_points(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y))[1:])
    # Side hip to knee
    points.extend(cbez_points((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y))[1:])
    # Side knee to hem
    points.append(line_point(x_se, hem_y))
    # Hem across
    points.append(line_point(0, hem_y))
    # Inseam hem to knee
    points.append(line_point(0, knee_y))
    # Inseam knee to crotch tip
    points.extend(cbez_points((0, knee_y), (0.1, knee_y-6), (-f_cext*0.5, ct[1]+3), ct)[1:])
    # Crotch curve to CF at crotch depth
    points.extend(cbez_points(ct, (-f_cext, CROTCH_Y+0.1), (-f_cext*0.5, CROTCH_Y), (0, CROTCH_Y))[1:])
    # CF seam straight segments back to waist
    cf_steps = 5
    for i in range(cf_steps - 1, 0, -1):
        t = i / cf_steps
        y = CROTCH_Y * t + cf_w[1] * (1 - t)
        points.append(line_point(0, y))

    return tuple(strip_closing(points))


# ============================================================================
# BACK PANEL
# ============================================================================

def build_back_points(m, b_drop=1.9):
    hip_y = 8.5
    CROTCH_Y = m["front_rise"]
    hem_y = m["outseam"]
    knee_y = hem_y - m["inseam"] * 0.52
    waist_half = m["waist"] / 2.0
    hip_half = m["hip"] / 2.0
    b_waist = waist_half * 0.52 - 1.0
    b_hip = hip_half * 0.52 + 1.5 - 3.4
    b_hem = m["leg_opening"] * 0.52
    b_cext = hip_half * 0.125 + 1.5
    x_sh = b_hip
    x_sk = b_hem + 0.3
    x_se = b_hem
    ct = (-b_cext, CROTCH_Y + b_drop)
    cf_w = (-2.0, -1.5)
    sw = (b_waist - 2.0, -0.3)

    points = []
    # Waist curve
    points.extend(cbez_points(cf_w, (cf_w[0]+b_waist*0.3, -1.2), (cf_w[0]+b_waist*0.7, -0.6), sw))
    # Side waist to hip
    points.extend(cbez_points(sw, (x_sh*0.7, hip_y*0.3), (x_sh, hip_y*0.7), (x_sh, hip_y))[1:])
    # Side hip to knee
    points.extend(cbez_points((x_sh, hip_y), (x_sh, hip_y+3), (x_sk, knee_y-5), (x_sk, knee_y))[1:])
    # Side knee to hem
    points.append(line_point(x_se, hem_y))
    # Hem across
    points.append(line_point(0, hem_y))
    # Inseam hem to knee
    points.append(line_point(0, knee_y))
    # Inseam knee to crotch tip
    points.extend(cbez_points((0, knee_y), (0.1, knee_y-6), (-b_cext*0.3, ct[1]+3), ct)[1:])
    # Crotch tip to CF at crotch depth (J-curve)
    points.extend(cbez_points(ct, (-b_cext*0.5, CROTCH_Y+0.3), (-b_cext*0.2, CROTCH_Y), (0, CROTCH_Y))[1:])
    # CB seam: CF crotch to CB waist (diagonal)
    points.extend(cbez_points((0, CROTCH_Y), (-0.5, CROTCH_Y*0.6), (-1.5, CROTCH_Y*0.3), cf_w)[1:])

    return tuple(strip_closing(points))


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("MARE Pattern Engine v2")
    print("=" * 60)

    m = MEASUREMENTS
    pre = pattern_api.GetPatternCount()

    front_pts = build_front_points(m)
    back_pts = build_back_points(m)

    print("Front: " + str(len(front_pts)) + " pts")
    print("Back:  " + str(len(back_pts)) + " pts")

    # Create front
    print("Creating front...")
    pattern_api.CreatePatternWithPoints(front_pts)
    c1 = pattern_api.GetPatternCount()
    print("Count: " + str(c1))

    # Create back (offset 500mm right)
    print("Creating back...")
    back_offset = tuple((x + 500, y, t) for x, y, t in back_pts)
    pattern_api.CreatePatternWithPoints(back_offset)
    c2 = pattern_api.GetPatternCount()
    print("Count: " + str(c2))

    created = c2 - pre
    print("")
    print("Created " + str(created) + " panels")

    if created >= 2:
        fi = c2 - 2
        bi = c2 - 1
        print("Front idx: " + str(fi))
        print("Back idx:  " + str(bi))

        # Line counts
        print("")
        print("--- LINE MAP ---")
        for name, idx in [("Front", fi), ("Back", bi)]:
            try:
                lc = pattern_api.GetLineCount(idx)
                print(name + " (pattern " + str(idx) + "): " + str(lc) + " lines")
                for li in range(lc):
                    try:
                        ln = pattern_api.GetLineLength(idx, li)
                        print("  " + str(li) + ": " + str(round(ln, 1)) + "mm")
                    except:
                        print("  " + str(li) + ": ?")
            except Exception as e:
                print(name + ": error " + str(e))

        print("")
        print("Share the line map above for sewing setup.")
    else:
        print("Missing panels. Check 2D window.")

    print("Done.")

main()
