"""Offline boundary correspondence. Callers must validate artifact schemas first."""
import copy
import math

DIRECT_TOLERANCE_MM = 0.001
NUMERICAL_TOLERANCE_MM = 1e-8
SNAP_FRACTION_TOLERANCE = 1e-9
ARC_LENGTH_TOLERANCE_MM = 1e-10

class CorrespondenceError(ValueError):
    """Static privacy-safe failure category."""

def require(ok, category):
    if not ok:
        raise CorrespondenceError(category)

def points(pattern):
    sections = []
    for line in pattern['ShapeInfo']['LineList']:
        pts = line.get('PointList')
        require(isinstance(pts, list) and len(pts) in (2, 4), 'geometry-schema')
        require(all(isinstance(p, dict) and type(p.get('PointType')) in (int, str) for p in pts), 'geometry-schema')
        require([p['PointType'] for p in pts] in ([0, 0], [0, 3, 3, 0],
                ['Straight', 'Straight'], ['Straight', 'Bezier Curve', 'Bezier Curve', 'Straight']), 'geometry-schema')
        section = []
        for p in pts:
            pos = p.get('Position')
            require(isinstance(pos, dict) and all(type(pos.get(k)) in (int, float)
                    and math.isfinite(pos[k]) for k in ('x', 'y')), 'geometry-schema')
            section.append((pos['x'], pos['y']))
        require(sum(math.dist(a, b) for a, b in zip(section, section[1:])) > NUMERICAL_TOLERANCE_MM,
                'degenerate-section')
        sections.append(tuple(section))
    require(all(math.dist(s[-1], sections[(i+1) % len(sections)][0]) <= NUMERICAL_TOLERANCE_MM
                for i, s in enumerate(sections)), 'open-boundary')
    return sections

def arc_length(s):
    if len(s) == 2:
        return math.dist(*s)
    def speed(t):
        return math.hypot(*(3*((1-t)**2*(s[1][k]-s[0][k]) +
                              2*(1-t)*t*(s[2][k]-s[1][k]) +
                              t*t*(s[3][k]-s[2][k])) for k in (0, 1)))
    def simpson(a, b):
        return (b-a)*(speed(a)+4*speed((a+b)/2)+speed(b))/6
    def adaptive(a, b, whole, budget, depth):
        mid = (a+b)/2
        left, right = simpson(a, mid), simpson(mid, b)
        delta = left+right-whole
        if abs(delta) <= 15*budget:
            return left+right+delta/15
        require(depth > 0, 'arc-length-nonconvergence')
        return adaptive(a, mid, left, budget/2, depth-1) + adaptive(mid, b, right, budget/2, depth-1)
    return adaptive(0, 1, simpson(0, 1), ARC_LENGTH_TOLERANCE_MM, 24)

def lengths(sections, legacy=False):
    if legacy:
        return [sum(math.dist(a, b) for a, b in zip(s, s[1:])) *
                (1.15 if len(s) == 4 else 1) for s in sections]
    return [arc_length(s) for s in sections]

def boundaries(values):
    total = sum(values)
    return [sum(values[:i]) / total for i in range(len(values) + 1)]

def close(a, b, tolerance):
    return len(a) == len(b) and all(math.dist(x, y) <= tolerance for x, y in zip(a, b))

def snap(value, fractions):
    candidates = [i for i, boundary in enumerate(fractions)
                  if abs(boundary-value) <= SNAP_FRACTION_TOLERANCE]
    require(bool(candidates), 'nonboundary-endpoint')
    require(len(candidates) == 1, 'ambiguous-endpoint')
    return candidates[0]

def match_sections(src, dst):
    require(len(src) == len(dst), 'unsupported-subdivision-or-section-count')
    direct = all(close(a, b, DIRECT_TOLERANCE_MM) for a, b in zip(src, dst))
    tolerance = DIRECT_TOLERANCE_MM if direct else NUMERICAL_TOLERANCE_MM
    matches = []
    for section in src:
        candidates = [(j, rev) for j, other in enumerate(dst) for rev in (False, True)
                      if close(section, other[::-1] if rev else other, tolerance)]
        require(bool(candidates), 'unmatched-geometry')
        require(len(candidates) == 1, 'ambiguous-geometry')
        matches.append(candidates[0])
    require(len({j for j, _ in matches}) == len(dst), 'ambiguous-geometry')
    reverse = matches[0][1]
    require(all(r == reverse and j == (matches[0][0] + (-i if reverse else i)) % len(dst)
                for i, (j, r) in enumerate(matches)), 'unsupported-contour-order')
    return matches

def panel_index(data):
    require(data.get('Unit') == 'mm', 'unsupported-unit')
    names, ids = {}, set()
    for pattern in data['PatternList']:
        name = pattern.get('Name')
        values = [pattern[k] for k in ('ID', 'ShapeID') if k in pattern]
        require(isinstance(name, str) and bool(name.strip()), 'invalid-name')
        require(bool(values) and all(isinstance(v, str) and bool(v.strip()) for v in values), 'invalid-id')
        require(len(set(values)) == 1, 'ambiguous-id')
        require(name not in names, 'duplicate-name')
        require(values[0] not in ids, 'duplicate-id')
        names[name] = pattern
        ids.add(values[0])
    return names

def correspond(source, target):
    """Return (deep-copied sewn export, privacy-safe coverage report)."""
    old_names, by_name = panel_index(source), panel_index(target)
    require(old_names.keys() == by_name.keys(), 'name-set-mismatch')
    mapping = {}
    line_indices = {}
    target_line_ids = {}
    categories = {'direct': 0, 'reordered': 0, 'reversed': 0}
    discrepancies = []
    section_count = side_count = 0
    for old in source['PatternList']:
        new = by_name[old['Name']]
        src, dst = points(old), points(new)
        matches = match_sections(src, dst)
        category = 'reversed' if matches[0][1] else ('direct' if matches[0][0] == 0 else 'reordered')
        categories[category] += 1
        section_count += len(src)
        for s, (j, reverse) in zip(src, matches):
            discrepancies.extend(math.dist(a, b) for a, b in zip(s, dst[j][::-1] if reverse else dst[j]))
        line_indices[old.get('ID', old.get('ShapeID'))] = {
            edge.get('ID', edge.get('ShapeID')): i
            for i, edge in enumerate(old['ShapeInfo']['LineList'])
            if 'ID' in edge or 'ShapeID' in edge}
        target_line_ids[old.get('ID', old.get('ShapeID'))] = {
            i: edge.get('ID', edge.get('ShapeID'))
            for i, edge in enumerate(new['ShapeInfo']['LineList'])
            if 'ID' in edge or 'ShapeID' in edge}
        mapping[old.get('ID', old.get('ShapeID'))] = (
            new.get('ID', new.get('ShapeID')), boundaries(lengths(src, legacy=True)), boundaries(lengths(dst)), matches,
            all(index == target_index and not reverse for index, (target_index, reverse) in enumerate(matches)))
    seams = copy.deepcopy(source['SeamLinePairGroupList'])
    occupied = {}
    target_occupied = {}
    for group in seams:
        for pair in group['PairList']:
            for side in pair.values():
                side_count += 1
                source_ident = side['ShapeID']
                ident, src, dst, matches, direct_contour = mapping[source_ident]
                if 'LineID' in side:
                    start = line_indices[source_ident][side.pop('LineID')]
                    end = start + 1
                else:
                    start, end = [snap(side['LengthParam'][key], src)
                                  for key in ('fStart', 'fEnd')]
                side['ShapeID'] = ident
                require(start != end and (start, end) != (len(matches), 0), 'empty-or-ambiguous-interval')
                # Legacy generator recipes name index boundaries, not wrap intent.
                selected = set(range(min(start, end), max(start, end)))
                used = occupied.setdefault(ident, set())
                require(not used.intersection(selected), 'physical-interval-overlap')
                used.update(selected)
                mapped = {matches[i][0] for i in selected}
                target_used = target_occupied.setdefault(ident, set())
                require(len(mapped) == len(selected) and not target_used.intersection(mapped),
                        'physical-interval-overlap')
                target_used.update(mapped)
                # Current CLO host exports retain a target LineID alongside
                # LengthParam for a one-section side. Preserve the resolved
                # target reference only where it is exact; multi-section spans
                # remain LengthParam-only until host semantics are established.
                if len(mapped) == 1:
                    target_index = next(iter(mapped))
                    if target_index in target_line_ids[source_ident]:
                        side['LineID'] = target_line_ids[source_ident][target_index]
                # The closure point is geometrically equal at 0 and 1, but the
                # serialized endpoint is seam-interval syntax. Preserve a source
                # final-boundary start on an unchanged contour rather than modulo
                # normalizing it to 0.
                first, reverse = matches[start % len(matches)]
                if direct_contour and start == len(matches):
                    first = len(matches)
                last, _ = matches[(end-1) % len(matches)]
                side['LengthParam'] = {'fStart': dst[last] if reverse else dst[first],
                                       'fEnd': dst[first+1] if reverse else dst[last+1]}
                if len(selected) == len(matches):
                    side['LengthParam'] = {'fStart': 0, 'fEnd': 1}
    result = copy.deepcopy(target)
    result['SeamLinePairGroupList'] = seams
    return result, {
        'status': 'passed',
        'physical_edges': 'passed',
        'physical_edges_basis': 'correspondence-mapping',
        'target_lengthparam_semantics': 'unknown',
        'counts': {'panels': len(mapping), 'sections': section_count, 'seam_sides': side_count},
        'coverage': {'matched_sections': section_count, 'sewn_sections': sum(map(len, occupied.values()))},
        'categories': categories,
        'tolerances': {'direct_mm': DIRECT_TOLERANCE_MM, 'numerical_mm': NUMERICAL_TOLERANCE_MM,
                       'snap_fraction': SNAP_FRACTION_TOLERANCE, 'arc_length_mm': ARC_LENGTH_TOLERANCE_MM},
        'discrepancy_mm': {'max': max(discrepancies), 'mean': math.fsum(discrepancies)/len(discrepancies)},
    }

def check_intervals(data, legacy=False):
    """Recover legacy recipe occupancy, or apply the unchanged target check.

    The target forward/wrap check is not established CLO LengthParam semantics.
    """
    indices = {}
    source_boundaries = {}
    for pattern in data['PatternList']:
        fractions = boundaries(lengths(points(pattern), legacy=legacy))
        source_boundaries[pattern.get('ID', pattern.get('ShapeID'))] = fractions
        indices[pattern.get('ID', pattern.get('ShapeID'))] = {
            edge.get('ID', edge.get('ShapeID')): (fractions[i], fractions[i+1])
            for i, edge in enumerate(pattern['ShapeInfo']['LineList'])
            if 'ID' in edge or 'ShapeID' in edge}
    used = {}
    for group in data['SeamLinePairGroupList']:
        for pair in group['PairList']:
            for side in pair.values():
                ident = side['ShapeID']
                if 'LineID' in side:
                    start, end = indices[ident][side['LineID']]
                else:
                    start, end = (side['LengthParam'][key] for key in ('fStart', 'fEnd'))
                require(start != end and (start, end) != (1, 0), 'empty-or-ambiguous-interval')
                if legacy:
                    start, end = [snap(value, source_boundaries[ident]) for value in (start, end)]
                    require(start != end and (start, end) != (len(source_boundaries[ident])-1, 0),
                            'empty-or-ambiguous-interval')
                    intervals = [(min(start, end), max(start, end))]
                else:
                    intervals = [(start, end)] if start < end else [(start, 1), (0, end)]
                previous = used.setdefault(ident, [])
                for a, b in intervals:
                    require(all(min(b, d) <= max(a, c) for c, d in previous), 'physical-interval-overlap')
                previous.extend(intervals)
