"""Read-only, privacy-projected offline CLO artifact checks (stdlib only)."""

import argparse
import importlib.util
import hashlib
import json
import math
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'mare_seam_correspondence', Path(__file__).with_name('seam_correspondence.py'))
assert _spec is not None and _spec.loader is not None
_geometry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_geometry)


class InvalidArtifact(ValueError):
    """Static error codes only: never leak document values or paths."""


def require(condition, code):
    if not condition:
        raise InvalidArtifact(code)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def identity(pattern):
    values = [pattern[k] for k in ("ID", "ShapeID") if k in pattern]
    require(bool(values) and all(text(v) for v in values), "invalid-id")
    require(len(set(values)) == 1, "ambiguous-id")
    return values[0]


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate-json-key")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InvalidArtifact):
            raise
        raise InvalidArtifact("invalid-json") from None


def finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), "nonfinite-number")
    elif isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def validate_schema(data):
    """Validate structure and references without interpreting scalar traversal."""
    require(isinstance(data, dict), "document-type")
    finite_tree(data)
    require(data.get("Unit") == "mm", "unsupported-unit")
    patterns = data.get("PatternList")
    require(isinstance(patterns, list) and bool(patterns), "pattern-list")
    names, ids, lines = {}, set(), {}
    for pattern in patterns:
        require(isinstance(pattern, dict), "pattern-type")
        name = pattern.get("Name")
        require(text(name), "invalid-name")
        ident = identity(pattern)
        require(name not in names, "duplicate-name")
        require(ident not in ids, "duplicate-id")
        names[name] = ident
        ids.add(ident)
        shape = pattern.get("ShapeInfo")
        require(isinstance(shape, dict), "shape-info")
        outline = shape.get("LineList")
        require(isinstance(outline, list) and bool(outline), "line-list")
        line_ids = set()
        for line in outline:
            require(isinstance(line, dict), "line-type")
            if "ID" not in line and "ShapeID" not in line:
                continue  # Generator waistband outlines omit IDs; cannot resolve LineID here.
            lid = identity(line)
            require(lid not in line_ids, "duplicate-line-id")
            line_ids.add(lid)
        lines[ident] = line_ids
    groups = data.get("SeamLinePairGroupList")
    require(isinstance(groups, list), "seam-list")
    used, exact = set(), set()

    count = 0
    for group in groups:
        require(isinstance(group, dict), "group-type")
        require(
            set(group) <= {"Name", "PairList", "bIsTurned", "FoldData"}, "group-schema"
        )
        if "Name" in group:
            require(isinstance(group["Name"], str), "group-name-type")
        if "bIsTurned" in group:
            require(type(group["bIsTurned"]) is bool, "turned-type")
        if "FoldData" in group:
            # Generator and retained artifacts use only these integer settings.
            # Never copy opaque nested references through the seam remapper.
            fold = group["FoldData"]
            require(
                isinstance(fold, dict)
                and set(fold) == {"iAngle", "iStrength"}
                and all(type(value) is int for value in fold.values()),
                "fold-schema",
            )
        pairs = group.get("PairList")
        require(isinstance(pairs, list) and bool(pairs), "pair-list")
        for pair in pairs:
            require(
                isinstance(pair, dict) and set(pair) == {"First", "Second"},
                "pair-schema",
            )
            for side in pair.values():
                require(isinstance(side, dict), "side-type")
                require(
                    set(side)
                    in (
                        {"ShapeID", "LineID", "Direction"},
                        {"ShapeID", "LengthParam", "Direction"},
                    ),
                    "side-schema",
                )
                sid = side["ShapeID"]
                require(text(sid) and sid in ids, "unknown-shape")
                require(type(side["Direction"]) is bool, "direction-type")
                if "LineID" in side:
                    lid = side["LineID"]
                    require(text(lid) and lid in lines[sid], "unknown-line")
                    edge = (sid, lid)
                    require(edge not in used, "physical-edge-reuse")
                    used.add(edge)
                else:

                    fractions = side["LengthParam"]
                    require(
                        isinstance(fractions, dict)
                        and set(fractions) == {"fStart", "fEnd"},
                        "fraction-schema",
                    )
                    require(
                        all(
                            type(v) in (int, float) and 0 <= v <= 1 and math.isfinite(v)
                            for v in fractions.values()
                        ),
                        "fraction-range-or-type",
                    )
                    ref = (
                        sid,
                        fractions["fStart"],
                        fractions["fEnd"],
                        side["Direction"],
                    )
                    require(ref not in exact, "duplicate-reference")
                    exact.add(ref)
                count += 1
    return {
        "names": names,
        "patterns": len(patterns),
        "seam_groups": len(groups),
        "seam_sides": count,
        "physical_edges": "unknown",
        "target_lengthparam_semantics": "unknown",
    }


def validate(data, legacy=False):
    info = validate_schema(data)
    try:
        if legacy:
            _geometry.check_intervals(data, legacy=True)
            info['physical_edges'] = 'passed'
            info['physical_edges_basis'] = 'legacy-source-recipe'
        else:
            for pattern in data['PatternList']:
                _geometry.points(pattern)
    except _geometry.CorrespondenceError as exc:
        raise InvalidArtifact(str(exc)) from None
    return info


def nonseam(data):
    return {k: v for k, v in data.items() if k != 'SeamLinePairGroupList'}


def remap_seams(source, target, *, with_report=False):
    source_info, target_info = validate(source, legacy=True), validate_schema(target)
    old, new = source_info["names"], target_info["names"]
    require(old.keys() == new.keys(), "name-set-mismatch")
    try:
        result, report = _geometry.correspond(source, target)
    except _geometry.CorrespondenceError as exc:
        raise InvalidArtifact(str(exc)) from None
    validate_schema(result)
    require(canonical(nonseam(result)) == canonical(nonseam(target)),
            'export-preservation-mismatch')
    return (result, report) if with_report else result


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify(paths):
    report = {
        "status": "incomplete",
        "artifacts": {},
        "checks": {"roundtrip": "unknown"},
        "errors": [],
        "missing_stages": [
            s for s in ("panels", "clo-export", "sewn") if s not in paths
        ],
    }
    documents = {}
    for stage, path in paths.items():
        try:
            raw = Path(path).read_bytes()
            report["artifacts"][stage] = {"sha256": hashlib.sha256(raw).hexdigest()}
            data = parse(raw)
            info = validate(data, legacy=stage == 'panels')
            documents[stage] = data
            report["artifacts"][stage].update(
                {k: v for k, v in info.items() if k != "names"}
            )
        except InvalidArtifact as exc:
            report["errors"].append({"stage": stage, "code": str(exc)})
        except (OSError, RecursionError):
            report["errors"].append({"stage": stage, "code": "unreadable-or-too-deep"})
    if not report["errors"]:
        try:
            infos = [validate(d, legacy=s == 'panels')["names"] for s, d in documents.items()]
            require(
                all(i.keys() == infos[0].keys() for i in infos), "name-set-mismatch"
            )
            if "panels" in documents:
                for target in ("clo-export", "sewn"):
                    if target in documents:
                        expected, coverage = remap_seams(documents["panels"], documents[target], with_report=True)
                        report['checks'].setdefault('correspondence', {})[target] = coverage
                        if target == "sewn":
                            require(
                                canonical(expected) == canonical(documents[target]),
                                "seam-remap-mismatch",
                            )
            if "clo-export" in documents and "sewn" in documents:
                require(
                    canonical(nonseam(documents["clo-export"]))
                    == canonical(nonseam(documents["sewn"])),
                    "export-preservation-mismatch",
                )
            if not report["missing_stages"]:
                # Promote only after expected sewn equality and export preservation.
                report['artifacts']['sewn'].update(
                    physical_edges='passed', physical_edges_basis='correspondence-mapping')
                report["checks"]["roundtrip"] = "passed"
                if (
                    all(
                        report['artifacts'][s]["physical_edges"] == "passed"
                        for s in ('panels', 'sewn')
                    )
                    and report["artifacts"]["panels"]["seam_sides"] > 0
                ):
                    report["status"] = "passed"
        except InvalidArtifact as exc:
            report["errors"].append({"stage": "cross-stage", "code": str(exc)})
    if report["errors"]:
        report["status"] = "invalid"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for stage in ("panels", "clo-export", "sewn", "artifact"):
        parser.add_argument("--" + stage)
    args = parser.parse_args()
    paths = {k.replace("_", "-"): v for k, v in vars(args).items() if v}
    if not paths or ("artifact" in paths and len(paths) != 1):
        parser.error("supply staged files or one unstaged --artifact")
    report = verify(paths)
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"passed": 0, "invalid": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
