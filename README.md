# mare-pipeline

FDLC (Fashion Design Life Cycle) tooling for MARE. Sketch → CLO3D.

> North star: package as a reusable "fashion factory" for any brand.

## Pipeline Overview

```
IDEATION → CONCEPT → APPROVED → IN-PATTERN → PATTERN-READY → SIMULATED → TECH-PACK-READY → IN-PRODUCTION
```

See `~/base/creative/MAREv2/pipeline/FDLC.md` for the full living spec.

## Structure

```
fdlc/
  scaffold.py           # Stage 2 — Design scaffold (concept lock → design repo entry)
  pattern_intake.py     # Stage 3 — Pattern intake (approved → in-pattern)
  generate_silhouette.py # Stage 2.5 — Render → B&W silhouette → SVG [TODO]
  pattern_engine/
    mode_a/
      illustrator_bridge.py  # SVG → seam allowance → AAMA DXF [TODO]
    mode_b/
      parametric_gen.py      # Measurements + ratios → DXF [TODO]
      solvers/
        rect_panel_grid.py   # Rounded rectangle grid solver (star-grid etc) [TODO]

image_gen/
  kontext.py            # FLUX.1 Kontext [pro] via BFL API ($0.04/img)
  flux_generate.py      # FLUX.1 dev via ComfyUI headless API (free, local)

archive/
  vision_sweep.py       # Gemini 2.5 Flash archive triage
  vision_sweep_local.py # Qwen local archive triage

research/
  research_extract.py   # Narrative research extraction via Ollama (qwen2.5:14b)
```

## Canonical Source

This repo (`~/base/mare-pipeline/`) is the canonical source for all pipeline scripts.
All other locations (OpenClaw skills, etc.) reference or symlink here.

## Dependencies

```bash
pip install -r requirements.txt
```

## Key Paths

| Resource | Path |
|----------|------|
| FDLC spec | `~/base/creative/MAREv2/pipeline/FDLC.md` |
| Design repo | `~/base/creative/MAREv2/designs/` |
| ComfyUI | `~/base/ai/ComfyUI/` |
| Archive DSS | `~/.openclaw/workspace/creative/MARE/dss/` |
| new-design skill | `~/.openclaw/skills/new-design/` |
