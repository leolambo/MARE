# pipeline/ — Attractor Orchestration

DOT graph definitions for the FDLC pipeline.
Future: run stages automatically via Attractor.

## Files

- `fdlc.dot` — Full FDLC pipeline as an Attractor-compatible DOT graph

## Rendering the graph

```bash
# Install graphviz
brew install graphviz

# Render to PNG
dot -Tpng pipeline/fdlc.dot -o pipeline/fdlc.png

# Render to SVG
dot -Tsvg pipeline/fdlc.dot -o pipeline/fdlc.svg
```

## Node Status Legend

| Color | Meaning |
|-------|---------|
| 🟢 Green | Built and working |
| 🟡 Yellow | Partial / wrapper needed |
| 🟠 Orange | Spec complete, not built |
| ⬡ Grey diamond | Human decision point |
| 🔵 Blue | External tool (CLO3D) |

## Attractor Integration (future)

When Attractor is integrated, each DOT node maps to a script command.
A single invocation drives a design through the full pipeline:

```bash
attractor run fdlc --design kimimaro-puffer --mode A
```

Ref: https://github.com/strongdm/attractor
