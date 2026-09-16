"""Bounded six-panel generator anatomy, independent of JSON sewing flags.

Section ordinals here describe the PINNED source generator, never native indices.
Mirroring preserves source traversal; current host references still require the
full geometry bijection and authenticated native observations.
"""
import math
import seam_correspondence as geo
import whole_line_recipe

# (name, ((panel, section, anatomical traversal), ...)). True is source forward.
POLICY = tuple(
    (name+'_'+leg, (('Back_'+word, section, True), ('Front_'+word, section, True)))
    for leg, word in (('L', 'Left'), ('R', 'Right'))
    for name, section in (('side_top',1), ('side_hip_knee',2), ('side_knee_hem',3),
                          ('inseam_straight',5), ('inseam_curve',6))) + (
    ('center_front', (('Front_Left', (8,9,10,11), True), ('Front_Right', (8,9,10,11), True))),
    ('center_back', (('Back_Left',8,True), ('Back_Right',8,True))),
    ('crotch_front', (('Front_Left',7,True), ('Front_Right',7,True))),
    ('crotch_back', (('Back_Left',7,True), ('Back_Right',7,True))),
    ('wb_front_to_FL', (('Front_Left',0,True), ('WB_Front',1,True))),
    ('wb_front_to_FR', (('WB_Front',0,True), ('Front_Right',0,False))),
    ('wb_back_to_BL', (('WB_Back',0,True), ('Back_Left',0,False))),
    ('wb_back_to_BR', (('Back_Right',0,True), ('WB_Back',1,True))),
    ('wb_side_R', (('WB_Front',2,True), ('WB_Back',4,False))),
    ('wb_side_L', (('WB_Front',4,True), ('WB_Back',2,False))),
)
WHOLE_GROUPS = tuple(i for i in range(len(POLICY)) if i != 10)


def recipe_plan(source, target):
    report = whole_line_recipe.analyze(source, target)
    groups = report['groups']
    for group in source['SeamLinePairGroupList']:
        # No inferred easing/turned/fold conversion through a six-argument API.
        geo.require(set(group) == {'Name','bIsTurned','PairList','FoldData'}
                    and group['bIsTurned'] is False
                    and group['FoldData'] == {'iAngle':180,'iStrength':5},
                    'native-recipe-sewing-semantics')
        for pair in group['PairList']:
            geo.require(set(pair)=={'First','Second'}, 'native-recipe-sewing-semantics')
            for side in pair.values():
                geo.require(set(side) <= {'ShapeID','LineID','LengthParam','Direction'}
                            and type(side.get('Direction')) is bool,
                            'native-recipe-sewing-semantics')
    geo.require(len(groups) == len(POLICY), 'native-recipe-group-set')
    panels = {name: geo.points(p) for name, p in geo.panel_index(source).items()}
    geo.require(set(panels) == {'Front_Left','Front_Right','Back_Left','Back_Right','WB_Front','WB_Back'},
                'native-recipe-panel-set')
    for family, count in (('Front',12), ('Back',9)):
        left, right = panels[family+'_Left'], panels[family+'_Right']
        geo.require(len(left) == len(right) == count, 'native-recipe-anatomy')
        axis = left[0][0][0]+right[0][0][0]
        reflected = [[(axis-x,y) for x,y in section] for section in left]
        geo.require(all(geo.close(a,b,1e-6) for a,b in zip(reflected,right)), 'native-recipe-mirror')
        # Closed ordered source anatomy and hem/knee/hip/waist vertical order.
        geo.require(all(geo.close([a[-1]],[b[0]],1e-6) for a,b in zip(left,left[1:]+left[:1])),
                    'native-recipe-continuity')
        geo.require(left[1][0][1] > left[2][0][1] > left[3][0][1] > left[3][-1][1]
                    and left[5][0][1] < left[5][-1][1] < left[6][-1][1], 'native-recipe-anatomy')
    for name in ('WB_Front','WB_Back'):
        s = panels[name]
        geo.require(len(s) == 5 and all(len(x)==2 for x in s)
                    and all(geo.close([a[-1]],[b[0]],1e-6) for a,b in zip(s,s[1:]+s[:1])),
                    'native-recipe-waistband')
        x,y = s[0][0]; mid=s[0][-1][0]; end=s[1][-1][0]; top=s[2][-1][1]
        expected=[[(x,y),(mid,y)],[(mid,y),(end,y)],[(end,y),(end,top)],
                  [(end,top),(x,top)],[(x,top),(x,y)]]
        geo.require(x < mid < end and top > y and abs(mid-x-(end-mid))<1e-6
                    and all(geo.close(a,b,1e-6) for a,b in zip(s,expected)), 'native-recipe-waistband')
    result=[]; occupied=set()
    for i, (group, (name, policy)) in enumerate(zip(groups,POLICY)):
        geo.require(group['name']==name and len(group['sides'])==2, 'native-recipe-group-set')
        sides=[]
        for side,(panel,section,forward) in zip(group['sides'],policy):
            sections=list(section) if isinstance(section,tuple) else [section]
            geo.require(side['panel']==panel and side['source_sections']==sections,
                        'native-recipe-coverage')
            for section in sections:
                key=(panel,section)
                geo.require(key not in occupied, 'native-recipe-overlap'); occupied.add(key)
            sides.append(dict(side,forward=forward,
                              source_length_mm=math.fsum(geo.arc_length(panels[panel][j]) for j in sections)))
        result.append(dict(index=i,name=name,supported=i!=10,sides=sides,
                           status='whole-section-eligible' if i!=10 else 'center-front-grouping-unresolved',
                           length_delta_mm=sides[0]['source_length_mm']-sides[1]['source_length_mm']))
    # CF is not paired by ordinal: compare reflected geometric endpoints/full
    # sections and unique candidates, lengths, continuity and total coverage.
    left,right=panels['Front_Left'],panels['Front_Right']
    axis=left[0][0][0]+right[0][0][0]; candidates=[]
    for i in range(8,12):
        mirrored=[(axis-x,y) for x,y in left[i]]
        matches=[j for j in range(8,12) if geo.close(mirrored,right[j],1e-6)
                 and abs(geo.arc_length(left[i])-geo.arc_length(right[j]))<1e-6]
        geo.require(len(matches)==1, 'native-center-front-ambiguous')
        candidates.append([i,matches[0]])
    geo.require(len({j for _,j in candidates})==4, 'native-center-front-ambiguous')
    result[10]['constituent_candidates']=candidates
    result[10]['split_authorized']=False
    return result
