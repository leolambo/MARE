"""Offline synthetic fixtures: never evidence of a CLO host roundtrip."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    return {
        "Unit": "mm",
        "PatternList": [
            {"Name": name, "ID": ident, "ShapeInfo": {"LineList": [
                {"ID": lid, "PointList": [
                    {"PointType": 0, "Position": {"x": x, "y": y}}
                    for x, y in ends]}
                for lid, ends in [
                    ("edge", [(0, 0), (10, 0)]),
                    ("right", [(10, 0), (10, 10)]),
                    ("top", [(10, 10), (0, 10)]),
                    ("left", [(0, 10), (0, 0)])]]}}
            for name, ident in [("front", "a"), ("back", "b")]
        ],
        "SeamLinePairGroupList": [
            {
                "Name": "a",
                "PairList": [
                    {
                        side: {"ShapeID": ident, "LineID": "edge", "Direction": False}
                        for side, ident in [("First", "a"), ("Second", "b")]
                    }
                ],
            }
        ],
    }


def files(tmp_path, source=None):
    source = source or fixture()
    export = copy.deepcopy(source)
    export["SeamLinePairGroupList"] = []
    for p, ident in zip(export["PatternList"], ["b", "c"]):
        p["ID"] = ident
    paths = [
        tmp_path / name for name in ["panels.json", "clo-export.json", "sewn.json"]
    ]
    for path, data in zip(paths, [source, export]):
        path.write_text(json.dumps(data))
    return paths


def test_exact_remap_does_not_cascade_or_replace_names(tmp_path):
    paths = files(tmp_path)
    load("02_inject_seams").inject_seams(*map(str, paths))
    seams = json.loads(paths[2].read_text())["SeamLinePairGroupList"]
    assert seams[0]["Name"] == "a"
    assert seams[0]["PairList"][0]["First"]["ShapeID"] == "b"
    assert seams[0]["PairList"][0]["Second"]["ShapeID"] == "c"


def test_partial_cli_is_incomplete_and_private(tmp_path):
    paths = files(tmp_path)
    result = subprocess.run(
        [sys.executable, str(HERE / "verify_artifacts.py"), "--panels", str(paths[0])],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "incomplete"
    assert report["artifacts"]["panels"]["sha256"]
    assert "front" not in result.stdout
    assert str(tmp_path) not in result.stdout
    assert report["checks"]["roundtrip"] == "unknown"


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate-name",
        "duplicate-id",
        "ambiguous-id",
        "unknown-shape",
        "direction",
        "fraction-bool",
        "fraction-nan",
        "fraction-range",
        "unknown-side-key",
        "unknown-line",
        "duplicate-edge",
        "missing-pairs",
    ],
)
def test_invalid_artifacts_rejected(tmp_path, fault):
    data = fixture()
    patterns = data["PatternList"]
    group = data["SeamLinePairGroupList"][0]
    side = group["PairList"][0]["First"]
    if fault == "duplicate-name":
        patterns[1]["Name"] = patterns[0]["Name"]
    if fault == "duplicate-id":
        patterns[1]["ID"] = "a"
    if fault == "ambiguous-id":
        patterns[0]["ShapeID"] = "other"
    if fault == "unknown-shape":
        side["ShapeID"] = "unknown"
    if fault == "direction":
        side["Direction"] = 1
    if fault.startswith("fraction-"):
        del side["LineID"]
        value = {
            "fraction-bool": True,
            "fraction-nan": float("nan"),
            "fraction-range": 1.1,
        }[fault]
        side["LengthParam"] = {"fStart": value, "fEnd": 0.5}
    if fault == "unknown-side-key":
        side["RenamedID"] = "a"
    if fault == "unknown-line":
        side["LineID"] = "missing"
    if fault == "duplicate-edge":
        data["SeamLinePairGroupList"].append(copy.deepcopy(group))
    if fault == "missing-pairs":
        del group["PairList"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    report = load("verify_artifacts").verify({"panels": path})
    assert report["status"] == "invalid"
    assert report["errors"]


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "extra-pattern",
        "missing-pattern",
        "id-drift",
        "seam-drift",
        "arrangement-drift",
    ],
)
def test_complete_synthetic_roundtrip(tmp_path, fault):
    paths = files(tmp_path)
    load("02_inject_seams").inject_seams(*map(str, paths))
    sewn = json.loads(paths[2].read_text())
    if fault == "extra-pattern":
        extra = copy.deepcopy(sewn["PatternList"][0])
        extra.update(Name="extra", ID="extra")
        sewn["PatternList"].append(extra)
    if fault == "missing-pattern":
        sewn["PatternList"].pop()
    if fault == "id-drift":
        sewn["PatternList"][0]["ID"] = "changed"
    if fault == "seam-drift":
        sewn["SeamLinePairGroupList"][0]["Name"] = "changed"
    if fault == "arrangement-drift":
        sewn["Arrangement"] = "changed"
    paths[2].write_text(json.dumps(sewn))
    report = load("verify_artifacts").verify(
        dict(zip(["panels", "clo-export", "sewn"], paths))
    )
    assert report["status"] == ("passed" if fault == "none" else "invalid")


@pytest.mark.parametrize(
    "fault",
    ["duplicate", "extra", "unknown-ref", "schema", "existing-output", "source-output"],
)
def test_injector_fails_closed_without_writes(tmp_path, fault):
    paths = files(tmp_path)
    data = json.loads(paths[0].read_text())
    if fault == "duplicate":
        data["PatternList"][1]["Name"] = "front"
    if fault == "extra":
        data["PatternList"].pop()
    if fault == "unknown-ref":
        data["SeamLinePairGroupList"][0]["PairList"][0]["First"]["ShapeID"] = "missing"
    if fault == "schema":
        data["SeamLinePairGroupList"][0]["PairList"][0]["First"]["NewID"] = "a"
    paths[0].write_text(json.dumps(data))
    if fault == "existing-output":
        paths[2].write_text("original")
    if fault == "source-output":
        paths[2] = paths[0]
    before = {p: p.read_bytes() for p in paths if p.exists()}
    with pytest.raises((ValueError, FileExistsError)):
        load("02_inject_seams").inject_seams(*map(str, paths))
    assert all(p.read_bytes() == raw for p, raw in before.items())
    if paths[2] not in before:
        assert not paths[2].exists()


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        '{"secret-name": 1, "secret-name": 2}',
        "NaN",
        '{"PatternList": null}',
        "[]",
        '{"coordinate": Infinity}',
    ],
)
def test_malformed_json_private_failure(tmp_path, raw):
    path = tmp_path / "private-name.json"
    path.write_text(raw)
    result = subprocess.run(
        [sys.executable, str(HERE / "verify_artifacts.py"), "--sewn", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "invalid"
    assert "secret-name" not in result.stdout + result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr


def test_missing_file_private_failure(tmp_path):
    report = load("verify_artifacts").verify({"sewn": tmp_path / "secret.json"})
    assert report["status"] == "invalid"


def test_lengthparam_boundary_wrap_is_verified_conflict_free(tmp_path):
    data = fixture()
    for side in data["SeamLinePairGroupList"][0]["PairList"][0].values():
        del side["LineID"]
        side["LengthParam"] = {"fStart": 0.75, "fEnd": 0.25}
    paths = files(tmp_path, data)
    load("02_inject_seams").inject_seams(*map(str, paths))
    report = load("verify_artifacts").verify(
        dict(zip(["panels", "clo-export", "sewn"], paths))
    )
    assert report["status"] == "passed"
    assert report["checks"]["roundtrip"] == "passed"
    assert report["artifacts"]["sewn"]["physical_edges"] == "passed"


@pytest.mark.parametrize(
    "fault", ["unit", "group-schema", "geometry-nan", "duplicate-json-key"]
)
def test_injector_additional_drift_rejected(tmp_path, fault):
    paths = files(tmp_path)
    source = json.loads(paths[0].read_text())
    if fault == "unit":
        source["Unit"] = "inch"
    if fault == "group-schema":
        source["SeamLinePairGroupList"][0]["OtherShapeID"] = "a"
    if fault == "geometry-nan":
        source["PatternList"][0]["coordinate"] = float("nan")
    raw = json.dumps(source)
    if fault == "duplicate-json-key":
        raw = raw.replace('"Unit": "mm"', '"Unit": "mm", "Unit": "mm"')
    paths[0].write_text(raw)
    with pytest.raises(ValueError):
        load("02_inject_seams").inject_seams(*map(str, paths))
    assert not paths[2].exists()


def test_unstaged_variant_and_empty_seams_not_full_success(tmp_path):
    paths = files(tmp_path)
    report = load("verify_artifacts").verify({"artifact": paths[0]})
    assert report["missing_stages"] == ["panels", "clo-export", "sewn"]
    assert report["status"] == "incomplete"
    for path in paths[:2]:
        data = json.loads(path.read_text())
        data["SeamLinePairGroupList"] = []
        path.write_text(json.dumps(data))
    load("02_inject_seams").inject_seams(*map(str, paths))
    report = load("verify_artifacts").verify(
        dict(zip(["panels", "clo-export", "sewn"], paths))
    )
    assert report["status"] == "incomplete"


def test_generator_synthetic_export_compatibility(tmp_path):
    from fdlc.pattern_engine.mode_b.solvers.clo3d_json import generate_5panel_json

    source = tmp_path / "panels.json"
    export = tmp_path / "clo-export.json"
    sewn = tmp_path / "sewn.json"
    generate_5panel_json(
        {
            "waist": 30.0,
            "hip": 44.0,
            "front_rise": 12.75,
            "inseam": 31.5,
            "outseam": 43.5,
            "leg_opening": 23.5,
        },
        str(source),
    )
    data = json.loads(source.read_text())
    data["SeamLinePairGroupList"] = []
    for index, pattern in enumerate(data["PatternList"]):
        pattern["ID"] = "synthetic-" + str(index)
    export.write_text(json.dumps(data))
    # Legacy descending ranges overlap under the explicit forward/wrap contract.
    # Do not infer a different traversal from Direction or silently accept them.
    before = (source.read_bytes(), export.read_bytes())
    with pytest.raises(ValueError, match='physical-interval-overlap'):
        load("02_inject_seams").inject_seams(str(source), str(export), str(sewn))
    assert not sewn.exists()
    assert (source.read_bytes(), export.read_bytes()) == before

def test_missing_geometry_cannot_use_shape_id_only_bypass(tmp_path):
    data = fixture()
    del data['PatternList'][0]['ShapeInfo']['LineList'][0]['PointList']
    paths = files(tmp_path, data)
    with pytest.raises(ValueError, match='geometry-schema'):
        load('02_inject_seams').inject_seams(*map(str, paths))
    assert not paths[2].exists()

@pytest.mark.parametrize('overlap', [False, True])
def test_unstaged_mixed_line_and_fraction_physical_intervals(tmp_path, overlap):
    data = fixture()
    pair = copy.deepcopy(data['SeamLinePairGroupList'][0]['PairList'][0])
    for side in pair.values():
        del side['LineID']
        side['LengthParam'] = {'fStart': .125 if overlap else .25, 'fEnd': .5}
        side['Direction'] = True
    data['SeamLinePairGroupList'][0]['PairList'].append(pair)
    path = tmp_path / 'artifact.json'
    path.write_text(json.dumps(data))
    report = load('verify_artifacts').verify({'artifact': path})
    if overlap:
        assert report['errors'] == [{'stage': 'artifact', 'code': 'physical-interval-overlap'}]
    else:
        assert report['artifacts']['artifact']['physical_edges'] == 'passed'


@pytest.mark.parametrize("value", ["not a boolean", 0, 1, None, [], {}])
def test_group_turned_requires_boolean_before_injection(tmp_path, value):
    data = fixture()
    data["SeamLinePairGroupList"][0]["bIsTurned"] = value
    paths = files(tmp_path, data)
    before = [p.read_bytes() for p in paths[:2]]
    report = load("verify_artifacts").verify({"panels": paths[0]})
    assert report["status"] == "invalid"
    assert report["errors"] == [{"stage": "panels", "code": "turned-type"}]
    with pytest.raises(ValueError, match="^turned-type$"):
        load("02_inject_seams").inject_seams(*map(str, paths))
    assert not paths[2].exists()
    assert [p.read_bytes() for p in paths[:2]] == before


@pytest.mark.parametrize("value", [None, 1, False, [], {}, {"ShapeID": "missing"}])
def test_group_name_requires_string_before_injection(tmp_path, value):
    data = fixture()
    data["SeamLinePairGroupList"][0]["Name"] = value
    paths = files(tmp_path, data)
    report = load("verify_artifacts").verify({"panels": paths[0]})
    assert report["errors"] == [{"stage": "panels", "code": "group-name-type"}]
    with pytest.raises(ValueError, match="^group-name-type$"):
        load("02_inject_seams").inject_seams(*map(str, paths))
    assert not paths[2].exists()


@pytest.mark.parametrize(
    "value",
    [
        None, False, 180, "fold", [], {},
        {"ShapeID": "missing"},
        {"iAngle": 180},
        {"iStrength": 5},
        {"iAngle": 180, "iStrength": 5, "ShapeID": "missing"},
        {"iAngle": {"ShapeID": "missing"}, "iStrength": 5},
        {"iAngle": 180, "iStrength": [5]},
        {"iAngle": True, "iStrength": 5},
        {"iAngle": 180, "iStrength": False},
        {"iAngle": 180.0, "iStrength": 5},
        {"iAngle": 180, "iStrength": "5"},
    ],
)
@pytest.mark.parametrize("stage", ["panels", "clo-export"])
def test_group_fold_schema_rejected_before_output(tmp_path, value, stage):
    paths = files(tmp_path)
    index = 0 if stage == "panels" else 1
    data = json.loads(paths[index].read_text())
    if stage == "clo-export":
        group = copy.deepcopy(fixture()["SeamLinePairGroupList"][0])
        group["PairList"][0]["First"]["ShapeID"] = "b"
        group["PairList"][0]["Second"]["ShapeID"] = "c"
        data["SeamLinePairGroupList"] = [group]
    data["SeamLinePairGroupList"][0]["FoldData"] = value
    paths[index].write_text(json.dumps(data))
    before = [p.read_bytes() for p in paths[:2]]
    report = load("verify_artifacts").verify({stage: paths[index]})
    assert report["status"] == "invalid"
    assert report["errors"] == [{"stage": stage, "code": "fold-schema"}]
    assert "physical_edges" not in report["artifacts"][stage]
    with pytest.raises(ValueError, match="^fold-schema$"):
        load("02_inject_seams").inject_seams(*map(str, paths))
    assert not paths[2].exists()
    assert [p.read_bytes() for p in paths[:2]] == before


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"Name": ""},
        {"Name": "  seam  ", "bIsTurned": True},
        {"Name": "a", "bIsTurned": False,
         "FoldData": {"iAngle": 180, "iStrength": 5}},
    ],
)
def test_supported_group_metadata_preserved(tmp_path, metadata):
    data = fixture()
    group = data["SeamLinePairGroupList"][0]
    del group["Name"]
    group.update(metadata)
    paths = files(tmp_path, data)
    load("02_inject_seams").inject_seams(*map(str, paths))
    sewn = json.loads(paths[2].read_text())["SeamLinePairGroupList"][0]
    assert {k: v for k, v in sewn.items() if k != "PairList"} == metadata
    report = load("verify_artifacts").verify(
        dict(zip(["panels", "clo-export", "sewn"], paths))
    )
    assert report["status"] == "passed"


def test_export_preservation_is_type_sensitive(tmp_path):
    paths = files(tmp_path)
    export = json.loads(paths[1].read_text())
    export["CustomMetadata"] = {"flag": True}
    paths[1].write_text(json.dumps(export))
    load("02_inject_seams").inject_seams(*map(str, paths))
    sewn = json.loads(paths[2].read_text())
    sewn["CustomMetadata"]["flag"] = 1
    paths[2].write_text(json.dumps(sewn))
    report = load("verify_artifacts").verify(
        dict(zip(["panels", "clo-export", "sewn"], paths))
    )
    assert report["status"] == "invalid"

def test_cubic_injection_and_verification_share_geometry_report(tmp_path):
    data = fixture()
    for p in data['PatternList']:
        p['ShapeInfo']['LineList'][0]['PointList'] = [
            {'PointType': t, 'Position': {'x': x, 'y': y}}
            for t, x, y in [(0, 0, 0), (3, 0, -10), (3, 10, -10), (0, 10, 0)]]
    for side in data['SeamLinePairGroupList'][0]['PairList'][0].values():
        del side['LineID']
        side['LengthParam'] = {'fStart': 0, 'fEnd': 34.5 / 64.5}
    paths = files(tmp_path, data)
    load('02_inject_seams').inject_seams(*map(str, paths))
    sewn = json.loads(paths[2].read_text())
    assert sewn['SeamLinePairGroupList'][0]['PairList'][0]['First']['LengthParam']['fEnd'] == pytest.approx(.4, abs=1e-10)
    report = load('verify_artifacts').verify(dict(zip(['panels', 'clo-export', 'sewn'], paths)))
    assert report['status'] == 'passed'
    assert report['checks']['correspondence']['clo-export']['coverage']['matched_sections'] == 8
    assert report['checks']['correspondence']['sewn']['counts']['seam_sides'] == 2
