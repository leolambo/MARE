# research/ — Narrative Research Extraction

Extracts structured craft findings from literary/visual sources for MARE brand storytelling.
Feeds the narrative framework at `~/base/creative/MAREv2/narrative/`.

## Script: research_extract.py

Uses Ollama (`qwen2.5:14b` preferred, falls back to `qwen2.5vl:7b`) for local inference.
Temperature 0.3 for consistent analytical output. Text truncated at 12,000 chars.

```bash
# Extract character archetypes from Berserk notes
python3 research/research_extract.py \
  --source "Berserk" \
  --text notes.txt \
  --category character \
  --append ~/base/creative/MAREv2/narrative/sources/berserk.md

# All categories at once
python3 research/research_extract.py \
  --source "Vagabond" --text notes.txt --category all
```

## Categories
`character`, `story-beats`, `world-building`, `tone`, `power-dynamics`,
`visual-grammar`, `silence-absence`, `all`

## Source Works
ASOIAF, Berserk, Vagabond, Vinland Saga, Akira, Blade of the Immortal,
No Longer Human, Count of Monte Cristo, Blood Meridian / The Road

## Output Format
Findings use the MARE Finding template:
- Pattern type
- Observation
- Example
- Why it lands
- MARE application
