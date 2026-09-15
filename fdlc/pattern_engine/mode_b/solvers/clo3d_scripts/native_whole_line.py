"""Operation-local native references from observed SDK 2026.1.224 schema.

No coordinate transform, exported-array/native-index identity, UUID mapping or
curve-midpoint inference. Endpoint + arc-length agreement is NOT complete cubic
identity: callers must bracket the same-project export with identical full native
reads and recheck the exact native bytes at mutation entry on the main queue.
"""
import json
import math
import seam_correspondence as geo
import whole_line_recipe

# Native float endpoints and tessellated length: measured retained comparison
# maximum length residual 0.012566 mm. These are explicit matching tolerances,
# not a vendor curve-fidelity guarantee; ambiguous candidates are rejected.
ENDPOINT_MM = .001
LENGTH_MM = .02

# Narrow observed float32/decimal native export profile: two half-ULPs at
# unit scale plus half a nine-decimal-place serialization step. This is an
# acceptance budget, NOT a guarantee of SDK summation/serialization behavior.
FRACTION_BUDGET = 2**-23 + 5e-10
ENDPOINT_ERROR_MM = .001
SECTION_ERROR_RATIO = .001


def _point(value):
    geo.require(type(value) is dict and all(type(value.get(k)) in (int, float)
                and math.isfinite(value[k]) for k in ('x', 'y')), 'native-point-schema')
    return value['x'], value['y']


def bind_geometry(exported, live):
    panels = geo.panel_index(exported)
    geo.require(type(live) is dict and live.get('ok') is True and
                type(live.get('pattern_count')) is int and
                live['pattern_count'] == len(panels) and
                type(live.get('patterns')) is list and len(live['patterns']) == len(panels),
                'native-pattern-schema')
    result, indices = {}, set()
    for row in live['patterns']:
        index = row.get('index')
        geo.require(type(index) is int and 0 <= index < len(panels) and index not in indices,
                    'native-pattern-index')
        indices.add(index)
        # Current host returns no outline points. Do not silently disregard future
        # richer geometry; add a separately tested interpretation when observed.
        geo.require(row.get('outline_points') == [], 'native-outline-schema')
        for key in ('pattern_line_info_json', 'pattern_information_json'):
            geo.require(type(row.get(key)) is str and 0 < len(row[key].encode()) <= 65536,
                        'native-json-bound')
        info = json.loads(row['pattern_information_json'])
        lines = json.loads(row['pattern_line_info_json'])
        name = lines.get('patternName')
        geo.require(lines.get('status') == 'success' and type(lines.get('patternIndex')) is int
                    and lines['patternIndex'] == index and name in panels
                    and name not in result and info.get('name') == name, 'native-pattern-name')
        sections = geo.points(panels[name])
        native = lines.get('lines')
        geo.require(type(native) is list and type(lines.get('lineCount')) is int and
                    lines['lineCount'] == len(native) == len(sections), 'native-line-count')
        identifiers = [line.get('lineIndex') for line in native]
        geo.require(all(type(i) is int and 0 <= i < 4096 for i in identifiers)
                    and len(set(identifiers)) == len(identifiers), 'native-line-index')
        parsed = []
        for line in native:
            length = line.get('length')
            geo.require(type(length) in (int, float) and math.isfinite(length) and length > 0,
                        'native-length')
            parsed.append((line['lineIndex'], (_point(line['start']), _point(line['end'])), length))
        matches = []
        for section in sections:
            endpoints = (section[0], section[-1]); length = geo.arc_length(section)
            candidates = [(index, reverse) for index, ends, size in parsed
                          for reverse in (False, True)
                          if geo.close(endpoints, ends[::-1] if reverse else ends, ENDPOINT_MM)
                          and abs(length-size) <= LENGTH_MM]
            geo.require(len(candidates) == 1, 'native-geometry-unmatched-or-ambiguous')
            matches.append(candidates[0])
        geo.require(len({i for i, _ in matches}) == len(native), 'native-geometry-not-bijective')
        sizes = {i: size for i, _, size in parsed}
        result[name] = {'pattern_index': index, 'sections': matches,
                        'lengths': [sizes[i] for i, _ in matches]}
    geo.require(result.keys() == panels.keys(), 'native-pattern-set')
    return result


def bind_fixed(source, exported, live, group):
    """Only the understood side-top / adjacent hip-knee endpoint pairing.

    Both source sections pair their starts together and ends together. The retained
    generated orientation fixture represents that same forward/forward traversal using
    reversed LengthParam + opposite Direction on one side. Do not copy its JSON
    booleans into the native API: SDK true means forward along the observed line.
    """
    geo.require(type(group) is int and group in (0, 1), 'unsupported-native-group')
    mapping = bind_geometry(exported, live)
    geo.require(len(mapping) == 6, 'native-benchmark-pattern-count')
    report = whole_line_recipe.analyze(source, exported)
    selected = report['groups'][group]
    geo.require(selected['name'] == ('side_top_L', 'side_hip_knee_L')[group]
                and len(selected['sides']) == 2, 'native-fixed-recipe')
    refs = []
    for side, name in zip(selected['sides'], ('Back_Left', 'Front_Left')):
        geo.require(side['panel'] == name and side['coverage'] == 'whole-target-section'
                    and side['source_sections'] == [group+1]
                    and side['source_boundary_order'] == [group+1, group+2], 'native-fixed-recipe')
        index, reverse = mapping[name]['sections'][side['target_sections'][0]]
        refs.append((mapping[name]['pattern_index'], index,
                     not (side['target_reversed'][0] ^ reverse)))
    return dict(pattern_a=refs[0][0], line_a=refs[0][1], pattern_b=refs[1][0],
                line_b=refs[1][1], direction_a=refs[0][2], direction_b=refs[1][2])


def verify_fixed_result(source, before, after, count, live=None):
    """Conservative known whole-line export profile, not generic scalar semantics.

    Verify all cubic control points through pipeline correspondence, unique target
    LineIDs, both intended pairs, whole-section endpoints and endpoint orientation.
    live MUST be the caller-authenticated same-run export-bracket geometry, equal
    to the complete post-sewing readback. This pure verifier cannot authenticate
    run provenance itself. Missing witnesses and unknown representations fail
    closed. Native lengths are ordered by geometry correspondence, not indices.
    """
    geo.require(type(count) is int and count in (1, 2), 'native-result-count')
    old, new = geo.panel_index(before), geo.panel_index(after)
    geo.require(old.keys() == new.keys(), 'native-result-panels')
    for name in old:
        geo.match_sections(geo.points(old[name]), geo.points(new[name]))
    # Bind both exports; no analytic fallback and no relaxation of curve checks.
    bind_geometry(before, live)
    mapping = bind_geometry(after, live)
    intended = whole_line_recipe.analyze(source, after)['groups'][:count]
    groups = after.get('SeamLinePairGroupList')
    geo.require(type(groups) is list and len(groups) == count, 'native-result-count')
    by_id = {p.get('ID', p.get('ShapeID')): name for name, p in new.items()}
    observed = []
    for group in groups:
        pairs = group.get('PairList')
        geo.require(type(pairs) is list and len(pairs) == 1 and set(pairs[0]) == {'First', 'Second'},
                    'native-result-pair')
        signature = []
        for side in pairs[0].values():
            name = by_id.get(side.get('ShapeID'))
            geo.require(name in ('Back_Left', 'Front_Left'), 'native-result-panel')
            lines = new[name]['ShapeInfo']['LineList']
            indices = [i for i, line in enumerate(lines)
                       if line.get('ID', line.get('ShapeID')) == side.get('LineID')]
            geo.require(len(indices) == 1 and type(side.get('Direction')) is bool,
                        'native-result-line')
            index = indices[0]
            sizes = mapping[name]['lengths']
            perimeter = math.fsum(sizes)
            geo.require(math.isfinite(perimeter) and perimeter > 0, 'native-result-perimeter')
            fractions = [math.fsum(sizes[:i])/perimeter for i in range(len(sizes)+1)]
            # Both absolute physical error and relative section loss are bounded;
            # tiny sections/large perimeters never inherit a unit-scale allowance.
            tolerance = min(FRACTION_BUDGET, ENDPOINT_ERROR_MM/perimeter,
                            SECTION_ERROR_RATIO*sizes[index]/perimeter)
            params = side.get('LengthParam', {})
            start, end = params.get('fStart'), params.get('fEnd')
            geo.require(all(type(x) in (int, float) and math.isfinite(x) for x in (start, end)),
                        'native-result-endpoints')
            geo.require(0 <= start <= 1 and 0 <= end <= 1, 'native-result-endpoints')
            forward = abs(start-fractions[index]) <= tolerance and abs(end-fractions[index+1]) <= tolerance
            backward = abs(end-fractions[index]) <= tolerance and abs(start-fractions[index+1]) <= tolerance
            geo.require(forward != backward, 'native-result-whole-section')
            signature.append((name, index, forward == side['Direction']))
        observed.append(tuple(sorted(signature)))
    expected = []
    for group in intended:
        geo.require(len(group['sides']) == 2, 'native-result-recipe')
        signature = []
        for side in group['sides']:
            geo.require(side['coverage'] == 'whole-target-section', 'native-result-recipe')
            signature.append((side['panel'], side['target_sections'][0], not side['target_reversed'][0]))
        expected.append(tuple(sorted(signature)))
    geo.require(sorted(observed) == sorted(expected), 'native-result-pairing-or-direction')
