# archive/ — Design Source Archive (DSS) Pipeline

Two-pass vision sweep pipeline for tagging and indexing MARE's reference archive.

## Strategy
- **Pass 1 (local):** `vision_sweep_local.py` — Qwen local model, fast bulk triage
- **Pass 2 (cloud):** `vision_sweep.py` — Gemini 2.5 Flash detail pass, final authority

Gemini always overrides Qwen on relevance judgments.

## State Files
| File | Contents |
|------|----------|
| `vision_state.json` | Local archive (~4,300 images, sweeps complete) |
| `vision_state_online.json` | Online archive (4,031 images, 3,220 high-relevance pending Gemini pass) |
| `vision_state_designs.json` | Design repo DSS (authored entries, no sweep needed) |

State files live at: `~/.openclaw/workspace/creative/MARE/dss/crawl/`

## Usage
```bash
# Qwen local sweep (bulk triage)
python3 archive/vision_sweep_local.py --dir /path/to/archive --state vision_state.json

# Gemini detail pass (tail mode — only processes high-relevance Qwen hits)
python3 archive/vision_sweep.py --state vision_state.json --tail

# Resweep with updated prompt
python3 archive/vision_sweep_local.py --resweep --state vision_state.json
```

## Field Mapping
- `result.relevance` — original Qwen field
- `result_v2.brand_alignment.relaunch_value` — enriched Qwen field (no `relevance` key)
- `gemini.result.relevance` — Gemini field (final authority)

## Pending
- [ ] Gemini detail pass on `vision_state_online.json` (3,220 images)
