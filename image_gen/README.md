# image_gen/ — AI Image Generation Tools

Two tools covering different stages of the generation pipeline.

## Tool Selection

| Tool | Script | Use When | Cost |
|------|--------|----------|------|
| **FLUX.1 Kontext [pro]** | `kontext.py` | Editing existing images, colorway iteration, silhouette generation, multi-ref composition | $0.04/img |
| **FLUX.1 dev (local)** | `flux_generate.py` | Free exploration, text-only generation, seeded iteration before committing to Kontext | Free |

## kontext.py — BFL API

Surgical image editing via FLUX.1 Kontext [pro] (Black Forest Labs API).
API key pulled from Bitwarden at runtime — never hardcoded.

```bash
# Edit existing image
kontext "change panels to raw indigo selvedge denim" --input garment.png --seed 42

# Render → B&W silhouette for potrace
kontext "Convert to a technical flat line drawing. Pure white background.
Solid black outlines only, uniform stroke weight throughout.
Every construction seam and panel boundary rendered as a distinct black line.
Panel interiors solid white — no fill, no shading, no gradients, no texture.
Garment silhouette edge in black. No labels, no annotations, no shadows.
Result must be high-contrast black-on-white suitable for vector auto-tracing
where each panel becomes a separate closed path." \
  --input render.png --output silhouette.png

# Multi-reference (up to 4 images)
kontext "match the construction from ref1, apply to silhouette in ref2" \
  --input ref1.png --input2 ref2.png --output result.png

# Model variants
kontext "..." --model kontext-pro   # $0.04 (default)
kontext "..." --model kontext-max   # $0.08 (higher quality)
```

## flux_generate.py — ComfyUI Headless API

Local FLUX.1 dev generation via ComfyUI API server.
Requires ComfyUI running (`~/base/ai/ComfyUI/run_comfy.sh`).
Uses `flux` bash wrapper which auto-starts ComfyUI if not running.

```bash
flux "wide-leg denim pants, star grid panels, white background" \
  --output gen.png --seed 42 --steps 28

flux "..." --lora techwear          # apply Techwear LoRA
flux "..." --lora analog            # apply 2000s Analog Core LoRA
flux "..." --width 832 --height 1216  # portrait
```

## Generation Workflow (Stage 1 → Stage 2.5)

```
1. Gemini (multi-ref + prompt) → initial concept render
2. Kontext → colorway/fabric iterations ($0.04 each)
3. FLUX local → free text-only exploration
4. Visual lock → scaffold.py
5. Kontext silhouette prompt → silhouette.png
6. potrace silhouette.png -s -o silhouette.svg
7. SVG → Stage 4 pattern engine
```
