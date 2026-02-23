#!/usr/bin/env python3
"""
MARE Design Repository - Pattern intake workflow.
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

DESIGNS_ROOT = Path.home() / "base/creative/MAREv2/designs"
OPENCLAW_ROOT = Path.home() / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_ROOT / "openclaw.json"
AUTH_PROFILE_ID = "anthropic:leoyambo95"
SONNET_MODEL = "anthropic/claude-sonnet-4-6"
OPUS_MODEL = "anthropic/claude-opus-4-6"
GEMINI_MODEL = "gemini-3-pro-preview"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MAX_DEBATE_ROUNDS_DEFAULT = 3

DEFAULT_MOCK_ANSWERS: Dict[str, Any] = {
    "target_size": "M",
    "garment_type": "pants",
    "waist": 32.0,
    "hip": 40.0,
    "inseam": 30.0,
    "rise_front": 11.0,
    "rise_back": 13.0,
    "hem_width_per_leg": 8.0,
    "ease_preference": "standard",
    "pipeline_mode": "both",
    "tech_pack_path": "",
    "additional_notes": "",
}

UNIVERSAL_QUESTION_LIST = [
    "Confirm complete piece inventory and mirrored/cut-on-fold intent.",
    "Confirm seam allowance amounts by edge class.",
    "Confirm grainline orientation and exceptions.",
    "Confirm notch strategy for key match points.",
    "Confirm fold lines, if any.",
    "List construction or fit risks needing verification.",
]

MOCK_AI_SUGGESTIONS = {
    "piece_inventory": [
        {"id": "front-left", "name": "Front Left Panel", "qty": 1, "notes": "Main front piece."},
        {"id": "front-right", "name": "Front Right Panel", "qty": 1, "notes": "Mirror of front-left."},
        {"id": "back-left", "name": "Back Left Panel", "qty": 1, "notes": "Main back piece."},
        {"id": "back-right", "name": "Back Right Panel", "qty": 1, "notes": "Mirror of back-left."},
        {"id": "waistband", "name": "Waistband", "qty": 1, "notes": "Cut on fold if continuous."},
    ],
    "seam_allowances": [
        {"edge": "side seams", "amount": "5/8\"", "notes": "Standard join seams."},
        {"edge": "inseam", "amount": "5/8\"", "notes": "Durable seam allowance."},
        {"edge": "hem", "amount": "1\"", "notes": "Turned hem allowance."},
        {"edge": "panel gaps (raw/design edge)", "amount": "0\"", "notes": "Raw edge, not sewn."},
    ],
    "grainlines": [
        {"piece": "all main panels", "direction": "vertical", "notes": "Parallel to center front/back."},
        {"piece": "waistband", "direction": "horizontal", "notes": "Stabilize waist edge."},
    ],
    "notches": [
        {
            "location": "side seam at hip",
            "on_pieces": ["front-left", "back-left", "front-right", "back-right"],
            "notes": "Match side seams at fullest hip.",
        },
        {
            "location": "inseam knee point",
            "on_pieces": ["front-left", "back-left", "front-right", "back-right"],
            "notes": "Align leg shaping.",
        },
    ],
    "fold_lines": [
        {"piece": "waistband", "line": "center fold", "notes": "Fold to cut one continuous band."},
    ],
    "additional_flags": [
        "Verify waistband ease against closure method.",
        "Confirm hem width still stacks over footwear intent.",
    ],
}

MOCK_OPUS_CRITIQUE_ROUND1 = {
    "issues": [
        "Panel gaps are raw/design edges and should remain 0\" seam allowance.",
        "Piece inventory is missing a fly facing for closure support.",
    ],
    "approved": [
        "Main panel grainlines are correctly vertical.",
        "Notch strategy on side seam and inseam is adequate.",
    ],
    "suggestions": [
        "Add fly facing piece with clear qty/cut instruction.",
    ],
}

MOCK_GEMINI_CRITIQUE_ROUND1 = {
    "issues": [
        "Waistband grainline should be cross-grain for production stability.",
        "Raw edge treatment should be explicitly called out for production handling.",
    ],
    "approved": [
        "0\" seam allowance on panel gaps is acceptable when intentionally raw.",
    ],
    "suggestions": [
        "Note fray-control expectation for QC checks.",
    ],
}

MOCK_OPUS_CRITIQUE_ROUND2 = {
    "issues": [],
    "approved": ["All previously raised technical issues are resolved."],
    "suggestions": [],
}

MOCK_GEMINI_CRITIQUE_ROUND2 = {
    "issues": [],
    "approved": ["Raw edge intent acknowledged; production note is sufficient."],
    "suggestions": [],
}

SUGGESTION_ORDER: List[Tuple[str, str]] = [
    ("piece_inventory", "Piece Inventory"),
    ("seam_allowances", "Seam Allowances"),
    ("grainlines", "Grainlines"),
    ("notches", "Notches"),
    ("fold_lines", "Fold Lines"),
    ("additional_flags", "Additional Flags"),
]


def slugify(s: str) -> str:
    return s.lower().replace(" ", "-").replace("_", "-")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def detect_garment_type(metadata: Dict[str, Any]) -> Optional[str]:
    tags = metadata.get("tags") or []
    if not isinstance(tags, list):
        return None
    normalized = [str(t).strip().lower() for t in tags]
    allowed = ["pants", "vest", "hoodie", "jacket", "other"]
    for item in allowed[:-1]:
        if item in normalized:
            return item
    return None


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def prompt_text(label: str, default: Optional[str] = None, required: bool = True, dry_run: bool = False) -> str:
    if dry_run and not is_interactive():
        return default or ""

    while True:
        suffix = f" [{default}]" if default not in (None, "") else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        if value or not required:
            return value
        print("Value required.")


def prompt_choice(label: str, choices: List[str], default: Optional[str] = None, dry_run: bool = False) -> str:
    choice_line = " / ".join(choices)
    if dry_run and not is_interactive():
        return default or choices[0]

    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label} ({choice_line}){suffix}: ").strip().lower()
        if not value and default:
            value = default
        if value in choices:
            return value
        print(f"Choose one of: {choice_line}")


def prompt_number(label: str, default: Optional[float] = None, dry_run: bool = False) -> float:
    if dry_run and not is_interactive():
        return float(default if default is not None else 0)

    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{label}{suffix}: ").strip()
        if not raw and default is not None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number.")


def load_design(name: str, dry_run: bool = False) -> Tuple[Path, Dict[str, Any], str, str]:
    slug = slugify(name)
    design_dir = DESIGNS_ROOT / slug
    if not design_dir.exists():
        if dry_run:
            print(f"⚠ Design '{slug}' not found at {design_dir}; using mock context for dry run.")
            return design_dir, {"id": slug, "name": slug, "status": "concept", "tags": ["pants"]}, "", ""
        print(f"❌ Design '{slug}' not found at {design_dir}")
        sys.exit(1)

    metadata = read_json(design_dir / "metadata.json", default={}) or {}
    readme = (design_dir / "README.md").read_text() if (design_dir / "README.md").exists() else ""
    spec = (design_dir / "spec.md").read_text() if (design_dir / "spec.md").exists() else ""
    return design_dir, metadata, readme, spec


def collect_phase1(metadata: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    auto_garment_type = detect_garment_type(metadata)

    if not is_interactive():
        # Non-interactive (e.g. piped/background): fall back to DEFAULT_MOCK_ANSWERS
        if not dry_run:
            print("⚠ Non-interactive session — using placeholder measurements (DEFAULT_MOCK_ANSWERS).")
            print("  Run interactively or with --dry-run to control measurements.")
        answers = dict(DEFAULT_MOCK_ANSWERS)
        if auto_garment_type:
            answers["garment_type"] = auto_garment_type
        return answers

    print("\nPhase 1 - High-level intake")
    answers: Dict[str, Any] = {}
    answers["target_size"] = prompt_text("Target size", default=None, required=True, dry_run=dry_run)

    if auto_garment_type:
        print(f"Garment type auto-detected from tags: {auto_garment_type}")
        answers["garment_type"] = auto_garment_type
    else:
        answers["garment_type"] = prompt_choice(
            "Garment type",
            ["pants", "vest", "hoodie", "jacket", "other"],
            default="pants",
            dry_run=dry_run,
        )

    answers["waist"] = prompt_number("Waist measurement (inches)", dry_run=dry_run)
    answers["hip"] = prompt_number("Hip measurement (inches)", dry_run=dry_run)
    answers["inseam"] = prompt_number("Inseam length (inches)", dry_run=dry_run)
    answers["rise_front"] = prompt_number("Rise - front (inches)", dry_run=dry_run)

    rise_back_default = round(answers["rise_front"] + 2.0, 2)
    answers["rise_back"] = prompt_number("Rise - back (inches)", default=rise_back_default, dry_run=dry_run)

    answers["hem_width_per_leg"] = prompt_number("Hem width per leg (inches)", dry_run=dry_run)
    answers["ease_preference"] = prompt_choice(
        "Ease preference",
        ["fitted", "standard", "relaxed", "oversized"],
        default="standard",
        dry_run=dry_run,
    )
    answers["pipeline_mode"] = prompt_choice(
        "Pipeline mode",
        ["parametric", "illustrator-bridge", "both"],
        default="both",
        dry_run=dry_run,
    )
    answers["tech_pack_path"] = ""
    if str(answers["pipeline_mode"]).strip().lower() in ("parametric", "both", "b"):
        has_tech_pack = prompt_choice(
            "Do you have a tech pack image for ratio extraction? (y/n)",
            ["y", "n"],
            default="n",
            dry_run=dry_run,
        )
        if has_tech_pack == "y":
            answers["tech_pack_path"] = prompt_text(
                "Tech pack image path",
                default=None,
                required=True,
                dry_run=dry_run,
            )
    answers["additional_notes"] = prompt_text("Additional notes (optional)", default="", required=False, dry_run=dry_run)
    return answers


def build_ai_prompt(metadata: Dict[str, Any], readme: str, spec: str, phase1: Dict[str, Any]) -> str:
    payload = {
        "design_metadata": metadata,
        "phase1_answers": phase1,
        "universal_question_list": UNIVERSAL_QUESTION_LIST,
        "output_schema": {
            "piece_inventory": [{"id": "...", "name": "...", "qty": 1, "notes": "..."}],
            "seam_allowances": [{"edge": "...", "amount": "...", "notes": "..."}],
            "grainlines": [{"piece": "...", "direction": "...", "notes": "..."}],
            "notches": [{"location": "...", "on_pieces": ["..."], "notes": "..."}],
            "fold_lines": [{"piece": "...", "line": "...", "notes": "..."}],
            "additional_flags": ["..."],
        },
    }
    return (
        "You are generating technical pattern-intake suggestions for a garment design. "
        "Return ONLY valid JSON matching the requested schema. Avoid markdown.\n\n"
        f"Context README:\n{readme}\n\n"
        f"Context spec.md:\n{spec}\n\n"
        f"Intake input JSON:\n{json.dumps(payload, indent=2)}\n"
    )


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Model output was not a valid JSON object")


def _summarize_suggestion_counts(suggestions: Dict[str, Any]) -> str:
    counts = []
    for key, label in SUGGESTION_ORDER:
        v = suggestions.get(key)
        if isinstance(v, list):
            counts.append(f"{len(v)} {label.lower()}")
    return ", ".join(counts) if counts else "no structured groups"


def _build_debate_context(metadata: Dict[str, Any], readme: str, spec: str, phase1: Dict[str, Any]) -> str:
    context_payload = {
        "design_metadata": metadata,
        "phase1_answers": phase1,
        "universal_question_list": UNIVERSAL_QUESTION_LIST,
    }
    return (
        f"Context README:\n{readme}\n\n"
        f"Context spec.md:\n{spec}\n\n"
        f"Intake context JSON:\n{json.dumps(context_payload, indent=2)}\n"
    )


def _build_critique_prompt(base_context: str, suggestions: Dict[str, Any], critic: str) -> str:
    if critic == "opus":
        task = (
            "Critique these pattern suggestions. Flag anything technically incorrect, missing, or inconsistent. "
            "Be specific. If something is correct, say so. Focus on piece inventory completeness, seam allowances "
            "for each edge type, grainline correctness, and notch placement logic."
        )
    else:
        task = (
            "Review these pattern suggestions from a manufacturing/production standpoint. Flag anything that would "
            "cause problems in actual cut-and-sew production. Consider fabric waste, cutting efficiency, assembly "
            "sequence, and raw edge treatment."
        )
    return (
        "You are reviewing technical pattern-intake suggestions.\n"
        f"{task}\n"
        'Return ONLY JSON: {"issues":[...], "approved":[...], "suggestions":[...]}.\n\n'
        f"{base_context}\n"
        f"Current suggestions JSON:\n{json.dumps(suggestions, indent=2)}\n"
    )


def _build_revision_prompt(
    base_context: str,
    original_suggestions: Dict[str, Any],
    opus_critique: Dict[str, Any],
    gemini_critique: Dict[str, Any],
) -> str:
    return (
        "Revise the pattern suggestions addressing critiques.\n"
        "Explain what you changed and why. If you disagree with a critique, explain why and keep your suggestion.\n"
        'Return ONLY JSON with keys: "piece_inventory", "seam_allowances", "grainlines", "notches", '
        '"fold_lines", "additional_flags", "changes", "disputes".\n\n'
        f"{base_context}\n"
        f"Current suggestions JSON:\n{json.dumps(original_suggestions, indent=2)}\n\n"
        f"Opus critique JSON:\n{json.dumps(opus_critique, indent=2)}\n\n"
        f"Gemini critique JSON:\n{json.dumps(gemini_critique, indent=2)}\n"
    )


def _read_auth_candidates() -> List[Path]:
    candidates: List[Path] = []
    auth_dir = OPENCLAW_ROOT / "auth"
    if auth_dir.exists() and auth_dir.is_dir():
        candidates.extend(sorted(auth_dir.glob("*.json")))
        profile_slug = AUTH_PROFILE_ID.replace(":", "_")
        candidates.extend(sorted(auth_dir.glob(f"*{profile_slug}*.json")))
        candidates.extend(sorted(auth_dir.glob(f"*{AUTH_PROFILE_ID}*.json")))
    return list(dict.fromkeys(candidates))


def resolve_anthropic_api_key() -> Optional[str]:
    config = read_json(OPENCLAW_CONFIG, default={}) or {}

    # Direct env override still allowed.
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key

    # Check obvious direct key slots.
    direct_paths = [
        ("anthropic", "api_key"),
        ("providers", "anthropic", "api_key"),
        ("auth", AUTH_PROFILE_ID, "api_key"),
    ]
    for key_path in direct_paths:
        current: Any = config
        ok = True
        for part in key_path:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and isinstance(current, str) and current.strip():
            return current.strip()

    # Inspect auth files for profile-specific token.
    for auth_file in _read_auth_candidates():
        auth_data = read_json(auth_file, default={}) or {}
        profile_hints = [
            str(auth_data.get("id", "")),
            str(auth_data.get("profile", "")),
            str(auth_data.get("provider", "")),
            auth_file.stem,
        ]
        hint_text = " ".join(profile_hints).lower()
        if "anthropic" not in hint_text and "leoyambo95" not in hint_text:
            # Keep looking, but still allow generic files with key names.
            pass

        for field in ["api_key", "token", "key", "access_token", "anthropic_api_key"]:
            v = auth_data.get(field)
            if isinstance(v, str) and v.strip().startswith("sk-"):
                return v.strip()

        # Nested structures.
        for container_key in ["credentials", "auth", "secrets"]:
            block = auth_data.get(container_key)
            if isinstance(block, dict):
                for field in ["api_key", "token", "key", "anthropic_api_key"]:
                    v = block.get(field)
                    if isinstance(v, str) and v.strip().startswith("sk-"):
                        return v.strip()

    return None


def call_anthropic_via_sdk(api_key: str, prompt: str, model: str = SONNET_MODEL) -> Dict[str, Any]:
    from anthropic import Anthropic  # type: ignore

    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=1800,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if text:
            text_blocks.append(text)
    raw = "\n".join(text_blocks).strip()
    return _parse_json_object(raw)


def call_anthropic_via_http(api_key: str, prompt: str, model: str = SONNET_MODEL) -> Dict[str, Any]:
    payload = {
        "model": model,
        "max_tokens": 1800,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urlrequest.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    blocks = body.get("content") or []
    raw = "\n".join([b.get("text", "") for b in blocks if isinstance(b, dict)]).strip()
    return _parse_json_object(raw)


def _call_anthropic_json(api_key: str, prompt: str, model: str) -> Dict[str, Any]:
    try:
        return call_anthropic_via_sdk(api_key, prompt, model=model)
    except ImportError:
        return call_anthropic_via_http(api_key, prompt, model=model)
    except urlerror.URLError:
        raise


def _call_gemini_critique(prompt: str) -> Dict[str, Any]:
    result = subprocess.run(
        ["gemini", "-m", GEMINI_MODEL, "--output-format", "json", prompt],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"Gemini CLI failed ({result.returncode}): {stderr}")
    return _parse_json_object(result.stdout or "")


def get_ai_suggestions(
    metadata: Dict[str, Any], readme: str, spec: str, phase1: Dict[str, Any], dry_run: bool = False
) -> Dict[str, Any]:
    if dry_run:
        return json.loads(json.dumps(MOCK_AI_SUGGESTIONS))

    prompt = build_ai_prompt(metadata, readme, spec, phase1)
    api_key = resolve_anthropic_api_key()
    if not api_key:
        raise RuntimeError("Could not resolve Anthropic API key from ~/.openclaw auth store.")
    return _call_anthropic_json(api_key, prompt, model=SONNET_MODEL)


def _debate_log_markdown(log: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Intake Debate Log - {log.get('design_name', '')}")
    lines.append(f"Date: {log.get('today', '')}")
    lines.append(f"Rounds run: {log.get('rounds_run', 0)}")
    lines.append("")
    lines.append("## Initial Suggestion Summary")
    lines.append(log.get("initial_summary", ""))
    lines.append("")
    lines.append("## Round Details")
    rounds = log.get("rounds", [])
    for round_info in rounds:
        idx = round_info.get("round")
        lines.append(f"### Round {idx}")
        lines.append("")
        lines.append("Opus critique:")
        opus = round_info.get("opus", {})
        lines.append(f"- Issues: {len(opus.get('issues', []))}")
        for issue in opus.get("issues", []):
            lines.append(f"- {issue}")
        lines.append("Gemini critique:")
        gemini = round_info.get("gemini", {})
        lines.append(f"- Issues: {len(gemini.get('issues', []))}")
        for issue in gemini.get("issues", []):
            lines.append(f"- {issue}")
        changes = round_info.get("changes", [])
        disputes = round_info.get("disputes", [])
        if changes:
            lines.append("Changes:")
            for c in changes:
                lines.append(f"- {c}")
        if disputes:
            lines.append("Disputes:")
            for d in disputes:
                lines.append(f"- {d}")
        lines.append("")

    lines.append("## Final Consensus Suggestions")
    lines.append("```json")
    lines.append(json.dumps(log.get("final_suggestions", {}), indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _save_debate_log(design_dir: Path, design_name: str, debate_log: Dict[str, Any], dry_run: bool = False) -> None:
    prompts_dir = design_dir / "prompts"
    today = date.today().isoformat()
    path = prompts_dir / f"intake-debate-{today}.md"
    body = _debate_log_markdown(
        {
            **debate_log,
            "design_name": design_name,
            "today": today,
        }
    )
    if dry_run:
        print(f"[dry-run] Would write debate log: {path}")
        return
    prompts_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    print(f"✓ Wrote debate log {path}")


def run_debate(
    metadata: Dict[str, Any],
    readme: str,
    spec: str,
    phase1: Dict[str, Any],
    max_rounds: int = MAX_DEBATE_ROUNDS_DEFAULT,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    print("\n🤔 Sonnet drafting initial suggestions...")
    base_context = _build_debate_context(metadata, readme, spec, phase1)

    if dry_run:
        suggestions = json.loads(json.dumps(MOCK_AI_SUGGESTIONS))
    else:
        api_key = resolve_anthropic_api_key()
        if not api_key:
            raise RuntimeError("Could not resolve Anthropic API key from ~/.openclaw auth store.")
        suggestions = _call_anthropic_json(api_key, build_ai_prompt(metadata, readme, spec, phase1), model=SONNET_MODEL)

    initial_summary = _summarize_suggestion_counts(suggestions)
    print(f"   → {initial_summary}")

    rounds: List[Dict[str, Any]] = []
    all_changes: List[str] = []
    rounds_run = 0
    api_key_for_debate = resolve_anthropic_api_key() if not dry_run else None

    for round_idx in range(1, max_rounds + 1):
        rounds_run = round_idx
        print(f"\n⚔️  Round {round_idx}: Opus + Gemini critiquing...")

        if dry_run:
            if round_idx == 1:
                opus = json.loads(json.dumps(MOCK_OPUS_CRITIQUE_ROUND1))
                gemini = json.loads(json.dumps(MOCK_GEMINI_CRITIQUE_ROUND1))
            else:
                opus = json.loads(json.dumps(MOCK_OPUS_CRITIQUE_ROUND2))
                gemini = json.loads(json.dumps(MOCK_GEMINI_CRITIQUE_ROUND2))
        else:
            if not api_key_for_debate:
                raise RuntimeError("Could not resolve Anthropic API key from ~/.openclaw auth store.")
            opus_prompt = _build_critique_prompt(base_context, suggestions, critic="opus")
            gemini_prompt = _build_critique_prompt(base_context, suggestions, critic="gemini")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f_opus = pool.submit(_call_anthropic_json, api_key_for_debate, opus_prompt, OPUS_MODEL)
                f_gemini = pool.submit(_call_gemini_critique, gemini_prompt)
                opus = f_opus.result()
                gemini = f_gemini.result()

        opus_issues = opus.get("issues", []) if isinstance(opus.get("issues"), list) else []
        gemini_issues = gemini.get("issues", []) if isinstance(gemini.get("issues"), list) else []
        print(f"📋 Opus raised {len(opus_issues)} issues | Gemini raised {len(gemini_issues)} issues")

        if not opus_issues and not gemini_issues:
            print(f"✅ Consensus reached in round {round_idx}")
            rounds.append(
                {
                    "round": round_idx,
                    "opus": opus,
                    "gemini": gemini,
                    "changes": [],
                    "disputes": [],
                }
            )
            break

        print("🔄 Sonnet revising...")
        if dry_run:
            revised = json.loads(json.dumps(suggestions))
            revised["piece_inventory"] = list(revised.get("piece_inventory", [])) + [
                {"id": "fly-facing", "name": "Fly Facing", "qty": 1, "notes": "Stabilizes fly closure."}
            ]
            revised["grainlines"] = [
                {
                    "piece": "all main panels",
                    "direction": "vertical",
                    "notes": "Parallel to center front/back.",
                },
                {
                    "piece": "waistband",
                    "direction": "cross-grain",
                    "notes": "Stabilize waist edge for production.",
                },
            ]
            revised["additional_flags"] = list(revised.get("additional_flags", [])) + [
                "Raw edge treatment intentional; no seam finishing at panel gaps.",
            ]
            revised["changes"] = [
                "Added fly facing piece.",
                "Updated waistband grainline to cross-grain.",
                "Added explicit raw-edge intent note.",
            ]
            revised["disputes"] = [
                "Raw edge finish remains intentionally omitted because fraying is a design feature.",
            ]
        else:
            if not api_key_for_debate:
                raise RuntimeError("Could not resolve Anthropic API key from ~/.openclaw auth store.")
            revision_prompt = _build_revision_prompt(base_context, suggestions, opus, gemini)
            revised = _call_anthropic_json(api_key_for_debate, revision_prompt, model=SONNET_MODEL)

        changes = revised.get("changes", []) if isinstance(revised.get("changes"), list) else []
        disputes = revised.get("disputes", []) if isinstance(revised.get("disputes"), list) else []
        for c in changes:
            print(f"   Changed: {c}")
        for d in disputes:
            print(f"   Disputed: {d}")
        all_changes.extend([str(c) for c in changes])

        suggestions = {k: revised.get(k, suggestions.get(k)) for k, _ in SUGGESTION_ORDER}
        rounds.append(
            {
                "round": round_idx,
                "opus": opus,
                "gemini": gemini,
                "changes": changes,
                "disputes": disputes,
            }
        )

    print(f"\n━━━ Debate complete ({rounds_run} rounds) ━━━")
    print(f"━━━ {len(all_changes)} changes made during debate ━━━")

    debate_log = {
        "initial_summary": initial_summary,
        "rounds_run": rounds_run,
        "rounds": rounds,
        "final_suggestions": suggestions,
    }
    return suggestions, debate_log


def format_group_items(key: str, value: Any) -> List[str]:
    lines: List[str] = []
    if isinstance(value, list):
        for i, item in enumerate(value, start=1):
            if isinstance(item, dict):
                if key == "piece_inventory":
                    name = item.get("name", "Unnamed")
                    qty = item.get("qty", "?")
                    notes = item.get("notes", "")
                    suffix = f" ({notes})" if notes else ""
                    lines.append(f"  [{i}] {name} x{qty}{suffix}")
                elif key == "seam_allowances":
                    edge = item.get("edge", "edge")
                    amount = item.get("amount", "")
                    notes = item.get("notes", "")
                    suffix = f" - {notes}" if notes else ""
                    lines.append(f"  [{i}] {edge}: {amount}{suffix}")
                elif key == "grainlines":
                    piece = item.get("piece", "piece")
                    direction = item.get("direction", "")
                    notes = item.get("notes", "")
                    suffix = f" - {notes}" if notes else ""
                    lines.append(f"  [{i}] {piece}: {direction}{suffix}")
                elif key == "notches":
                    location = item.get("location", "location")
                    pieces = ", ".join(item.get("on_pieces", [])) if isinstance(item.get("on_pieces"), list) else ""
                    notes = item.get("notes", "")
                    extras = ", ".join([p for p in [pieces, notes] if p])
                    suffix = f" ({extras})" if extras else ""
                    lines.append(f"  [{i}] {location}{suffix}")
                elif key == "fold_lines":
                    piece = item.get("piece", "piece")
                    line = item.get("line", "line")
                    notes = item.get("notes", "")
                    suffix = f" - {notes}" if notes else ""
                    lines.append(f"  [{i}] {piece}: {line}{suffix}")
                else:
                    lines.append(f"  [{i}] {json.dumps(item)}")
            else:
                lines.append(f"  [{i}] {item}")
    else:
        lines.append(f"  {value}")
    return lines


def edit_json_in_editor(value: Any) -> Any:
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        temp_path = Path(tf.name)
        tf.write(json.dumps(value, indent=2))
        tf.flush()

    try:
        subprocess.run([editor, str(temp_path)], check=False)
        raw = temp_path.read_text()
        return json.loads(raw)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def confirm_edit_loop(suggestions: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    confirmed: Dict[str, Any] = {}

    if not is_interactive():
        # Non-interactive: auto-accept all AI suggestions
        for key, _ in SUGGESTION_ORDER:
            confirmed[key] = suggestions.get(key)
        return confirmed

    print("\nPhase 3 - Confirm / edit")
    for key, title in SUGGESTION_ORDER:
        print(f"\n━━━ {title} ━━━")
        group_value = suggestions.get(key, [])
        for line in format_group_items(key, group_value):
            print(line)

        while True:
            action = input("Confirm? [Y/edit/skip]: ").strip().lower()
            if action in ("", "y", "yes"):
                confirmed[key] = group_value
                break
            if action == "edit":
                try:
                    group_value = edit_json_in_editor(group_value)
                except Exception as exc:
                    print(f"Edit failed: {exc}")
                    continue
                for line in format_group_items(key, group_value):
                    print(line)
                continue
            if action == "skip":
                confirmed[key] = "to be determined"
                break
            print("Enter Y, edit, or skip.")

    return confirmed


def render_markdown(design_name: str, today: str, phase1: Dict[str, Any], confirmed: Dict[str, Any]) -> str:
    def dump_list(items: Any) -> str:
        if isinstance(items, str):
            return f"- {items}\n"
        if not items:
            return "- _None_\n"
        out = []
        for item in items:
            if isinstance(item, dict):
                if "name" in item and "qty" in item:
                    notes = f" ({item['notes']})" if item.get("notes") else ""
                    out.append(f"- **{item.get('name', 'Unnamed')}** x{item.get('qty', '?')}{notes}")
                elif "edge" in item and "amount" in item:
                    notes = f" - {item['notes']}" if item.get("notes") else ""
                    out.append(f"- **{item.get('edge', 'Edge')}**: {item.get('amount', '')}{notes}")
                elif "piece" in item and "direction" in item:
                    notes = f" - {item['notes']}" if item.get("notes") else ""
                    out.append(f"- **{item.get('piece', 'Piece')}**: {item.get('direction', '')}{notes}")
                elif "location" in item:
                    pieces = item.get("on_pieces") or []
                    piece_text = ", ".join(pieces) if isinstance(pieces, list) else ""
                    details = "; ".join([x for x in [piece_text, item.get("notes", "")] if x])
                    suffix = f" ({details})" if details else ""
                    out.append(f"- **{item.get('location', 'Location')}**{suffix}")
                elif "piece" in item and "line" in item:
                    notes = f" - {item['notes']}" if item.get("notes") else ""
                    out.append(f"- **{item.get('piece', 'Piece')}**: {item.get('line', '')}{notes}")
                else:
                    out.append(f"- `{json.dumps(item)}`")
            else:
                out.append(f"- {item}")
        return "\n".join(out) + "\n"

    measurements_rows = [
        ("Waist", f"{phase1['waist']}\""),
        ("Hip", f"{phase1['hip']}\""),
        ("Inseam", f"{phase1['inseam']}\""),
        ("Rise - front", f"{phase1['rise_front']}\""),
        ("Rise - back", f"{phase1['rise_back']}\""),
        ("Hem width per leg", f"{phase1['hem_width_per_leg']}\""),
        ("Ease", phase1["ease_preference"]),
        ("Garment type", phase1["garment_type"]),
    ]

    md = [
        f"# Pattern Intake - {design_name}",
        f"**Date:** {today}",
        f"**Size:** {phase1['target_size']}",
        f"**Pipeline mode:** {phase1['pipeline_mode']}",
        "",
        "## Measurements",
        "| Key | Value |",
        "|-----|-------|",
    ]
    for key, value in measurements_rows:
        md.append(f"| {key} | {value} |")

    if phase1.get("tech_pack_path"):
        md.extend(
            [
                "",
                "## Tech Pack",
                f"- Path: `{phase1['tech_pack_path']}`",
                "- Note: `parametric_gen.py` will use this image for Gemini ratio extraction.",
            ]
        )

    if phase1.get("additional_notes"):
        md.extend(["", "## Intake Notes", phase1["additional_notes"]])

    md.extend(["", "## Piece Inventory", dump_list(confirmed.get("piece_inventory"))])
    md.extend(["## Seam Allowances", dump_list(confirmed.get("seam_allowances"))])
    md.extend(["## Grainlines", dump_list(confirmed.get("grainlines"))])
    md.extend(["## Notches", dump_list(confirmed.get("notches"))])
    md.extend(["## Fold Lines", dump_list(confirmed.get("fold_lines"))])
    md.extend(["## Flags / Notes", dump_list(confirmed.get("additional_flags"))])

    return "\n".join(md).strip() + "\n"


def update_metadata_and_index(
    design_dir: Path, metadata: Dict[str, Any], today: str, dry_run: bool = False, draft: bool = False
) -> None:
    metadata_path = design_dir / "metadata.json"
    metadata_out = dict(metadata)

    if draft:
        # Draft mode: keep status at concept, flag intake_mode
        metadata_out["intake_mode"] = "draft"
        metadata_out["updated"] = today
    else:
        # Production mode: advance status, lock measurements
        metadata_out["status"] = "in-pattern"
        metadata_out["updated"] = today
        metadata_out["intake_date"] = today
        metadata_out.pop("intake_mode", None)  # clear any prior draft flag

    index_path = DESIGNS_ROOT / "index.json"
    index_data = read_json(index_path, default={"updated": today, "designs": []})
    if not isinstance(index_data, dict):
        index_data = {"updated": today, "designs": []}
    designs = index_data.get("designs")
    if not isinstance(designs, list):
        designs = []

    design_id = metadata_out.get("id") or design_dir.name
    new_status = metadata_out.get("status", metadata.get("status", "concept"))
    found = False
    for entry in designs:
        if isinstance(entry, dict) and entry.get("id") == design_id:
            if not draft:
                entry["status"] = new_status
            found = True
            break

    if not found and not draft:
        designs.append(
            {
                "id": design_id,
                "name": metadata_out.get("name", design_id),
                "status": new_status,
                "created": metadata_out.get("created", today),
            }
        )

    index_data["designs"] = designs
    index_data["updated"] = today

    draft_tag = " [DRAFT — status unchanged]" if draft else ""
    if dry_run:
        print(f"[dry-run] Would update metadata.json{draft_tag} and designs/index.json")
        return

    write_json(metadata_path, metadata_out)
    if not draft:
        write_json(index_path, index_data)
    print(f"✓ Updated metadata.json{draft_tag}")
    if not draft:
        print("✓ Updated index.json")


def validate_status(metadata: Dict[str, Any], force: bool = False) -> None:
    status = str(metadata.get("status", "")).strip().lower()
    allowed = {"concept", "approved"}
    if status and status not in allowed:
        msg = f"⚠ Design status is '{status}', expected concept/approved."
        if force:
            print(msg + " Proceeding due to --force.")
            return
        print(msg + " Use --force to proceed.")
        sys.exit(1)


def run_qmd(dry_run: bool = False) -> None:
    if dry_run:
        print("[dry-run] Would run: qmd update && qmd embed")
        return
    print("⟳ Reindexing QMD...")
    subprocess.run(["qmd", "update"], check=False)
    subprocess.run(["qmd", "embed"], check=False)
    print("✓ QMD reindexed")


def ask_to_continue_without_ai(dry_run: bool = False) -> bool:
    if dry_run and not is_interactive():
        return True
    while True:
        choice = input("AI suggestion call failed. Continue with mock suggestions? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            return True
        if choice in ("n", "no"):
            return False


def parse_phase1_from_intake_markdown(intake_path: Path) -> Dict[str, Any]:
    if not intake_path.exists():
        raise FileNotFoundError(f"Missing intake file: {intake_path}")

    parsed: Dict[str, Any] = {"tech_pack_path": ""}
    in_tech_pack = False

    for raw_line in intake_path.read_text().splitlines():
        line = raw_line.strip()

        if line.startswith("**Size:**"):
            parsed["target_size"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("**Pipeline mode:**"):
            parsed["pipeline_mode"] = line.split(":", 1)[1].strip()
            continue

        if line.startswith("## "):
            in_tech_pack = line.lower() == "## tech pack"
            continue
        if in_tech_pack and line.startswith("- Path:"):
            value = line.split(":", 1)[1].strip().strip("`")
            parsed["tech_pack_path"] = value
            continue

        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2:
                continue
            key = cells[0].lower()
            value = cells[1].replace('"', "").strip()
            field_map = {
                "waist": "waist",
                "hip": "hip",
                "inseam": "inseam",
                "rise - front": "rise_front",
                "rise - back": "rise_back",
                "hem width per leg": "hem_width_per_leg",
                "ease": "ease_preference",
                "garment type": "garment_type",
            }
            if key in field_map:
                target = field_map[key]
                if target in ("ease_preference", "garment_type"):
                    parsed[target] = value
                else:
                    try:
                        parsed[target] = float(value)
                    except ValueError:
                        pass

    required = [
        "waist",
        "hip",
        "inseam",
        "rise_front",
        "rise_back",
        "hem_width_per_leg",
    ]
    missing = [k for k in required if k not in parsed]
    if missing:
        raise ValueError(f"Missing measurements in intake markdown: {', '.join(missing)}")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Pattern intake workflow for MARE designs")
    parser.add_argument("--name", required=True, help="Design slug (e.g. star-grid-denim-pants)")
    parser.add_argument("--force", action="store_true", help="Proceed even if status is not concept/approved")
    parser.add_argument("--dry-run", action="store_true", help="Run full flow without file writes or API calls")
    parser.add_argument(
        "--recalculate",
        action="store_true",
        help="Skip intake/debate and re-run Mode B solver from existing pattern-intake.md",
    )
    parser.add_argument("--no-debate", action="store_true", help="Skip adversarial debate and use single-pass suggestions")
    parser.add_argument("--max-rounds", type=int, default=MAX_DEBATE_ROUNDS_DEFAULT, help="Maximum debate rounds (default: 3)")
    parser.add_argument(
        "--draft",
        action="store_true",
        help=(
            "Draft mode: writes intake to patterns/mode_b/draft/, keeps status at 'concept', "
            "sets intake_mode='draft' in metadata. Use for placeholder measurement testing. "
            "Run without --draft to advance status to in-pattern and lock measurements."
        ),
    )
    args = parser.parse_args()

    design_dir, metadata, readme, spec = load_design(args.name, dry_run=args.dry_run)
    if not args.recalculate:
        validate_status(metadata, force=args.force)

    if args.recalculate:
        intake_path = design_dir / "pattern-intake.md"
        try:
            prior_phase1 = parse_phase1_from_intake_markdown(intake_path)
        except Exception as exc:
            print(f"❌ Recalculate failed while reading {intake_path}: {exc}")
            sys.exit(1)

        print("\n🔁 Recalculate mode: skipping Phase 1 intake and AI debate.")
        print("Using measurements from existing pattern-intake.md:")
        print(f"- Waist: {prior_phase1['waist']}\"")
        print(f"- Hip: {prior_phase1['hip']}\"")
        print(f"- Inseam: {prior_phase1['inseam']}\"")
        print(f"- Rise front/back: {prior_phase1['rise_front']}\" / {prior_phase1['rise_back']}\"")
        print(f"- Hem width per leg: {prior_phase1['hem_width_per_leg']}\"")

        parametric_gen_path = Path(__file__).resolve().parent / "pattern_engine/mode_b/parametric_gen.py"
        cmd = [
            sys.executable,
            str(parametric_gen_path),
            design_dir.name,
            "--recalculate",
        ]
        if prior_phase1.get("tech_pack_path"):
            cmd.extend(["--tech-pack", str(prior_phase1["tech_pack_path"])])
        if args.dry_run:
            cmd.append("--dry-run")

        print("\nCalling Mode B generator:")
        print("$ " + " ".join(cmd))
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"❌ parametric_gen.py failed with exit code {result.returncode}")
            sys.exit(result.returncode)
        print("✅ Recalculate complete: Mode B panels regenerated from updated intake values.")
        return

    phase1 = collect_phase1(metadata, dry_run=args.dry_run)
    if phase1.get("tech_pack_path"):
        print("ℹ parametric_gen.py will use this image for Gemini ratio extraction.")

    try:
        if args.no_debate:
            print("\n✓ Got it. Generating technical suggestions...")
            suggestions = get_ai_suggestions(metadata, readme, spec, phase1, dry_run=args.dry_run)
        else:
            suggestions, debate_log = run_debate(
                metadata,
                readme,
                spec,
                phase1,
                max_rounds=max(1, args.max_rounds),
                dry_run=args.dry_run,
            )
            design_name_for_log = metadata.get("name") or design_dir.name
            _save_debate_log(design_dir, design_name_for_log, debate_log, dry_run=args.dry_run)
    except Exception as exc:
        print(f"❌ AI suggestion step failed: {exc}")
        if not ask_to_continue_without_ai(dry_run=args.dry_run):
            sys.exit(1)
        suggestions = json.loads(json.dumps(MOCK_AI_SUGGESTIONS))

    confirmed = confirm_edit_loop(suggestions, dry_run=args.dry_run)

    today = date.today().isoformat()
    design_name = metadata.get("name") or design_dir.name
    output_md = render_markdown(design_name, today, phase1, confirmed)

    if args.draft:
        draft_dir = design_dir / "patterns" / "mode_b" / "draft"
        intake_path = draft_dir / "pattern-intake-draft.md"
        mode_tag = " [DRAFT]"
    else:
        intake_path = design_dir / "pattern-intake.md"
        mode_tag = ""

    if args.dry_run:
        print(f"[dry-run] Would write{mode_tag}: {intake_path}")
    else:
        intake_path.parent.mkdir(parents=True, exist_ok=True)
        intake_path.write_text(output_md)
        print(f"✓ Wrote{mode_tag}: {intake_path}")

    update_metadata_and_index(design_dir, metadata, today, dry_run=args.dry_run, draft=args.draft)
    if not args.draft:
        run_qmd(dry_run=args.dry_run)

    if args.draft:
        print("\n📐 Draft mode — Mode B parametric generator:")
        parametric_gen_path = Path(__file__).resolve().parent / "pattern_engine/mode_b/parametric_gen.py"
        cmd = [sys.executable, str(parametric_gen_path), design_dir.name, "--draft"]
        if phase1.get("tech_pack_path"):
            cmd.extend(["--tech-pack", str(phase1["tech_pack_path"])])
        print("$ " + " ".join(cmd))
        if args.dry_run:
            print("[dry-run] Intake file not written — skipping parametric_gen call.")
            print("[dry-run] To generate DXF from draft, also provide --ratios or --tech-pack:")
            print(f"[dry-run] $ parametric_gen {design_dir.name} --draft --ratios '{{\"panels_per_row\":3,...}}'")
        else:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                print(f"⚠ parametric_gen.py exited {result.returncode} — check output above")
            else:
                print("✅ Mode B draft DXF generated")

    print(f"\n{'📝 Draft' if args.draft else '✅'} Pattern intake flow complete{mode_tag}")


if __name__ == "__main__":
    main()
