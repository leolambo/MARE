"""Offline recipe-to-export coverage; callers validate artifact schemas first.

Reuses the pipeline geometry authority. Export array positions are NOT CLO API
indices. Output is an internal recipe report, not a native mutation request.
"""
import seam_correspondence as geometry


def analyze(source, target):
    """Classify complete source intervals against bijectively matched sections."""
    _, correspondence = geometry.correspond(source, target)
    old = geometry.panel_index(source)
    new = geometry.panel_index(target)
    by_id = {p.get('ID', p.get('ShapeID')): name for name, p in old.items()}
    groups = []
    for group in source['SeamLinePairGroupList']:
        sides = []
        for pair in group['PairList']:
            for key in ('First', 'Second'):
                side = pair[key]
                name = by_id[side['ShapeID']]
                src, dst = geometry.points(old[name]), geometry.points(new[name])
                matches = geometry.match_sections(src, dst)
                fractions = geometry.boundaries(geometry.lengths(src, legacy=True))
                start, end = [geometry.snap(side['LengthParam'][k], fractions)
                              for k in ('fStart', 'fEnd')]
                selected = list(range(min(start, end), max(start, end)))
                geometry.require(bool(selected), 'empty-or-ambiguous-interval')
                if 'LineID' in side:
                    identified = [i for i, line in enumerate(old[name]['ShapeInfo']['LineList'])
                                  if line.get('ID', line.get('ShapeID')) == side['LineID']]
                    geometry.require(identified == selected and len(selected) == 1,
                                     'line-id-coverage-mismatch')
                mapped = [matches[i][0] for i in selected]
                sides.append({'side': key, 'panel': name,
                              'source_sections': selected, 'target_sections': mapped,
                              'source_boundary_order': [start, end],
                              'target_reversed': [matches[i][1] for i in selected],
                              'recipe_direction': side['Direction'],
                              'coverage': 'whole-target-section' if len(mapped) == 1
                                          else 'multiple-target-sections'})
        groups.append({'name': group.get('Name'), 'sides': sides})
    return {'groups': groups, 'correspondence': correspondence['status'],
            'native_index_binding': 'unproven', 'native_direction_binding': 'unproven',
            'target_lengthparam_semantics': 'unknown', 'host_sewing': 'unproven'}
