# fdlc/ — Fashion Design Life Cycle Scripts

Core stage scripts for moving a design from concept to production-ready pattern.

## Scripts

| Script | Stage | Trigger |
|--------|-------|---------|
| `scaffold.py` | Stage 2 — Concept lock | Visual design approved |
| `pattern_intake.py` | Stage 3 — Pattern initiation | Design moved to `approved` status |
| `generate_silhouette.py` | Stage 2.5 — Silhouette gen | After scaffold, before intake |

## Usage

### scaffold.py
Creates the full design repository entry. Run once per design at visual lock.
```bash
python3 fdlc/scaffold.py \
  --name "kimimaro-puffer" \
  --title "Kimimaro Puffer Jacket" \
  --description "Technical puffer with organic panel cutouts..." \
  --colorways "black,cream" \
  --status "concept" \
  --tags "puffer,outerwear" \
  [--image-flat "/path/flat.png,black"]
```

### pattern_intake.py
Guided intake form for pattern generation. Runs Opus↔Sonnet adversarial debate
(max 4 rounds) for technical suggestions. Optionally accepts a tech pack image
to extract proportional ratios and compute panel dimensions automatically.
```bash
python3 fdlc/pattern_intake.py
python3 fdlc/pattern_intake.py --recalculate <design-name>  # post-CLO3D adjustment
```

### generate_silhouette.py _(TODO)_
Takes the approved render, calls Kontext to produce a clean B&W technical flat,
then runs `potrace` to output a traced SVG ready for Stage 4 Mode A.
```bash
python3 fdlc/generate_silhouette.py --input render.png --output silhouette.svg
```

## Subdirectory

- `pattern_engine/` — Stage 4 scripts: SVG/measurements → AAMA DXF → CLO3D
