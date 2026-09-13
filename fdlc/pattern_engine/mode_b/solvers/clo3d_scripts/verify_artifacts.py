"""Read-only, privacy-projected offline CLO artifact checks (stdlib only)."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


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


def validate(data):
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
    unknown = False
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
                    unknown = True
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
        "physical_edges": "unknown" if unknown else "passed",
    }


def remap_seams(source, target):
    source_info, target_info = validate(source), validate(target)
    old, new = source_info["names"], target_info["names"]
    require(old.keys() == new.keys(), "name-set-mismatch")
    mapping = {ident: new[name] for name, ident in old.items()}
    seams = copy.deepcopy(source["SeamLinePairGroupList"])
    for group in seams:
        for pair in group["PairList"]:
            for side in pair.values():
                side["ShapeID"] = mapping[side["ShapeID"]]
    result = copy.deepcopy(target)
    result["SeamLinePairGroupList"] = seams
    validate(result)
    return result


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
            info = validate(data)
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
            infos = [validate(d)["names"] for d in documents.values()]
            require(
                all(i.keys() == infos[0].keys() for i in infos), "name-set-mismatch"
            )
            if "panels" in documents:
                for target in ("clo-export", "sewn"):
                    if target in documents:
                        expected = remap_seams(documents["panels"], documents[target])
                        if target == "sewn":
                            require(
                                canonical(expected) == canonical(documents[target]),
                                "seam-remap-mismatch",
                            )
            if "clo-export" in documents and "sewn" in documents:
                strip = lambda d: {
                    k: v for k, v in d.items() if k != "SeamLinePairGroupList"
                }
                require(
                    canonical(strip(documents["clo-export"]))
                    == canonical(strip(documents["sewn"])),
                    "export-preservation-mismatch",
                )
            if not report["missing_stages"]:
                report["checks"]["roundtrip"] = "passed"
                if (
                    all(
                        a["physical_edges"] == "passed"
                        for a in report["artifacts"].values()
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
