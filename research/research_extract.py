#!/usr/bin/env python3
"""
MARE Narrative Research Extractor

Feeds text (synopsis, wiki summary, fan analysis) into a local LLM and extracts
structured findings in the MARE narrative framework format.

Usage:
  python research_extract.py --source "Berserk" --text berserk_summary.txt
  python research_extract.py --source "ASOIAF" --text asoiaf_notes.txt --category character
  echo "paste text here" | python research_extract.py --source "Vagabond" --stdin
  python research_extract.py --source "Berserk" --text notes.txt --append sources/berserk.md

Categories: character | story-beats | world-building | tone | power-dynamics |
            visual-grammar | silence-absence | all (default)

Model: Qwen3.5-35B-A3B via MLX (primary), qwen2.5:14b via Ollama (fallback)
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
import subprocess
import time
import atexit

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MLX_URL = "http://127.0.0.1:8088/v1/chat/completions"
MLX_MODEL = "/Users/al/.cache/mlx/Qwen3.5-35B-A3B-4bit"

# ── MLX lifecycle ─────────────────────────────────────────────────────────────
_MLX_STARTED_BY_US = False

def ensure_mlx_running():
    """Start MLX server if not running. Register atexit to stop it if we started it."""
    global _MLX_STARTED_BY_US
    if mlx_available():
        return  # already up — not our server to stop
    _MLX_STARTED_BY_US = True
    subprocess.Popen(
        ["bash", "-c",
         "source ~/mlx-env/bin/activate && python -m mlx_lm.server "
         "--model ~/.cache/mlx/Qwen3.5-35B-A3B-4bit "
         "--port 8088 --host 127.0.0.1 "
         "--chat-template-args \'{\"enable_thinking\":false}\'"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print("⏳ Starting MLX server...", file=sys.stderr)
    for _ in range(30):
        if mlx_available():
            print("✅ MLX server ready", file=sys.stderr)
            return
        time.sleep(1)
    raise RuntimeError("MLX server failed to start after 30s")

def _stop_mlx_if_we_started():
    if _MLX_STARTED_BY_US:
        subprocess.run(["pkill", "-f", "mlx_lm.server"], capture_output=True)

atexit.register(_stop_mlx_if_we_started)

CATEGORIES = [
    "character",
    "story-beats",
    "world-building",
    "tone",
    "power-dynamics",
    "visual-grammar",
    "silence-absence",
]

CATEGORY_DESCRIPTIONS = {
    "character": "character archetypes, motivations, wounds, contradictions, what characters refuse to do",
    "story-beats": "narrative structure, tension building, pacing, setup/escalation/resolution patterns",
    "world-building": "how environment reflects character and theme, what the world carries from history",
    "tone": "word choice, register, silence, restraint, how style carries emotional weight",
    "power-dynamics": "hierarchy, rebellion, loyalty, betrayal, the cost of each",
    "visual-grammar": "panel composition, negative space, line weight, pacing in visual storytelling",
    "silence-absence": "strategic withholding, what the work refuses to show or explain and why it works",
}

SYSTEM_PROMPT = """You are a narrative craft analyst helping build a storytelling research library for MARE — a streetwear brand building a world with characters, lore, and visual narratives.

MARE's DNA: confrontational, post-something, earned rather than performed. Dark utilitarian aesthetic. Collections as chapters of a larger story. The battle cry is "Now what?" — the tension after winning when you realize winning wasn't the answer.

Your job is to extract PATTERNS from the text provided — not plot summaries. You're looking for craft moves: specific techniques that great writers or artists use that could inform MARE's brand storytelling.

For each pattern you identify, structure your response EXACTLY as:

### Finding: [Descriptive title]
- **Pattern type:** [category]
- **Observation:** [What this work does — the technique, the craft move]
- **Example:** [Specific moment, scene, or element from the work that demonstrates it]
- **Why it lands:** [The emotional or structural reason this technique works]
- **MARE application:** [Concise, specific — how this could inform MARE's characters, collections, world, or visual language]

Extract 3-6 findings. Be specific. Generic observations are useless. Look for patterns that appear across the text and would be genuinely useful for dark, confrontational brand storytelling."""

def mlx_available() -> bool:
    """Check if MLX server is running."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8088/v1/models")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_available_model():
    """Return ('mlx', None) if MLX is up, else ('ollama', model_id) fallback."""
    if mlx_available():
        return ("mlx", MLX_MODEL)
    # Fallback to Ollama
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        models = [m["name"] for m in data.get("models", [])]
        if any("qwen2.5:14b" in m for m in models):
            print("⚠️  MLX not running, falling back to qwen2.5:14b", file=sys.stderr)
            return ("ollama", "qwen2.5:14b")
        print("❌ No model available. Start MLX or Ollama.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot reach any LLM backend: {e}", file=sys.stderr)
        sys.exit(1)


def build_prompt(source: str, text: str, categories: list) -> str:
    if len(categories) == len(CATEGORIES) or "all" in categories:
        cat_desc = "all pattern types: " + ", ".join(CATEGORIES)
    else:
        cat_desc = " and ".join(
            f"{c} ({CATEGORY_DESCRIPTIONS[c]})" for c in categories if c in CATEGORY_DESCRIPTIONS
        )

    return f"""SOURCE WORK: {source}

FOCUS: Extract findings related to {cat_desc}.

TEXT TO ANALYZE:
---
{text[:12000]}
---

Extract 3-6 specific narrative craft findings from this text. Focus on techniques relevant to dark, confrontational brand storytelling. Be concrete — name the specific technique, give a specific example, explain why it works emotionally/structurally, then connect it to MARE."""


def run_llm(backend: str, model: str, system: str, prompt: str) -> str:
    """Dispatch to MLX or Ollama based on backend."""
    if backend == "mlx":
        import urllib.request as ur
        full_prompt = system + "\n\n" + prompt if system else prompt
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "max_tokens": 2000,
            "temperature": 0.3,
        }
        req = ur.Request(
            MLX_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with ur.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
            return data["choices"][0]["message"]["content"].strip()
    # Ollama path
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "num_predict": 2000,
        }
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    output = []
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if line.strip():
                    chunk = json.loads(line.decode())
                    token = chunk.get("response", "")
                    output.append(token)
                    print(token, end="", flush=True)
                    if chunk.get("done"):
                        break
    except urllib.error.URLError as e:
        print(f"\n❌ Ollama error: {e}", file=sys.stderr)
        sys.exit(1)
    print()  # newline after streaming
    return "".join(output)


def format_output(source: str, categories: list, findings: str) -> str:
    cat_str = ", ".join(categories) if categories else "all"
    date = datetime.now().strftime("%Y-%m-%d")
    return f"""
---
*Extracted: {date} | Source: {source} | Categories: {cat_str}*

{findings.strip()}

---
"""


def main():
    parser = argparse.ArgumentParser(
        description="Extract narrative research findings using local LLM"
    )
    parser.add_argument("--source", required=True, help="Work title (e.g. 'Berserk', 'ASOIAF')")
    parser.add_argument("--text", help="Path to text file to analyze")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
    parser.add_argument(
        "--category", default="all",
        help=f"Pattern category or 'all'. Options: {', '.join(CATEGORIES)}"
    )
    parser.add_argument("--append", help="Path to markdown file to append findings to")
    parser.add_argument("--model", help="Override model (default: auto-detect best available)")
    args = parser.parse_args()

    # Read input text
    if args.stdin or not args.text:
        if sys.stdin.isatty():
            print("Paste text to analyze (Ctrl+D when done):")
        text = sys.stdin.read().strip()
    else:
        text_path = Path(args.text)
        if not text_path.exists():
            print(f"❌ File not found: {args.text}", file=sys.stderr)
            sys.exit(1)
        text = text_path.read_text(encoding="utf-8").strip()

    if not text:
        print("❌ No input text provided.", file=sys.stderr)
        sys.exit(1)

    # Resolve categories
    raw_cats = [c.strip() for c in args.category.split(",")]
    if "all" in raw_cats:
        categories = ["all"]
    else:
        invalid = [c for c in raw_cats if c not in CATEGORIES]
        if invalid:
            print(f"❌ Unknown categories: {invalid}", file=sys.stderr)
            print(f"   Valid: {', '.join(CATEGORIES)}", file=sys.stderr)
            sys.exit(1)
        categories = raw_cats

    # Get model
    ensure_mlx_running()
    backend, model = get_available_model() if not args.model else ('ollama', args.model)
    print(f"🧠 Model: {model}")
    print(f"📖 Source: {args.source}")
    print(f"🏷  Category: {args.category}")
    print(f"📝 Text length: {len(text):,} chars")
    print("─" * 60)

    # Build prompt and run
    prompt = build_prompt(args.source, text, categories)
    findings = run_llm(backend, model, SYSTEM_PROMPT, prompt)

    # Format and optionally append to file
    formatted = format_output(args.source, categories, findings)

    if args.append:
        append_path = Path(args.append)
        if not append_path.exists():
            print(f"⚠️  File not found, will create: {args.append}", file=sys.stderr)
        with open(append_path, "a", encoding="utf-8") as f:
            f.write(formatted)
        print(f"\n✅ Findings appended to: {args.append}")
    else:
        print("\n" + "─" * 60)
        print("💡 To save, re-run with: --append sources/<work>.md")


if __name__ == "__main__":
    main()
