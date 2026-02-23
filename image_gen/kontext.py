#!/usr/bin/env python3
"""
kontext.py — FLUX.1 Kontext [pro] via BFL API

Modes:
    edit:        input image + prompt → surgically edited image  ($0.04/img)
    text-to-img: prompt only → new image (no input)
    multi-ref:   up to 4 reference images + prompt → composite edit

Usage:
    kontext "change the panels to light grey washed denim" --input garment.png
    kontext "wide-leg denim pants, plain white background" --output gen.png
    kontext "keep the character, put them in a snow storm" --input char.png --seed 42
    kontext "match the style of image 1 applied to image 2" --input ref.png --input2 target.png

API: https://api.bfl.ai/v1/flux-kontext-pro
Auth: x-key header (pulled from Bitwarden at runtime — never hardcoded)
"""

import argparse
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

API_BASE = "https://api.bfl.ai"
BW_SCRIPT = Path.home() / ".openclaw/skills/bitwarden/scripts/bw_get_field.sh"

# Model endpoints + pricing reference
MODELS = {
    "kontext-pro":  ("flux-kontext-pro",  "$0.04 flat — surgical editing, best for garments"),
    "kontext-max":  ("flux-kontext-max",  "$0.08 flat — higher quality editing"),
    "flux2-klein":  ("flux-2-max",        "from $0.014 — scales w/ resolution, up to 10 refs"),
    "flux2-pro":    ("flux-2-max",        "from $0.03 — production quality, scales w/ resolution"),
}
DEFAULT_MODEL = "kontext-pro"


def get_bfl_key() -> str:
    """Pull BFL API key from Bitwarden. Key never touches disk."""
    session = subprocess.check_output(
        ["bash", str(BW_SCRIPT), "--unlock"],
        stderr=subprocess.DEVNULL
    ).decode().strip()
    key = subprocess.check_output(
        ["bash", str(BW_SCRIPT), "black forest labs bfl.ai", "API-KEY", session],
        stderr=subprocess.DEVNULL
    ).decode().strip()
    if not key:
        raise RuntimeError("BFL API key not found in Bitwarden")
    return key


def encode_image(path: str) -> str:
    """Base64-encode a local image file."""
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else "png"
    return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"


def image_arg(val: str) -> str:
    """Accept local path (encode) or URL (pass through)."""
    if val and Path(val).exists():
        return encode_image(val)
    return val  # assume URL


def submit_task(api_key: str, payload: dict, model: str = DEFAULT_MODEL) -> str:
    """POST to BFL endpoint, return async task ID."""
    endpoint = MODELS[model][0]
    req = urllib.request.Request(
        f"{API_BASE}/v1/{endpoint}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-key": api_key},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["id"]


def poll_result(api_key: str, task_id: str, timeout=180) -> str:
    """Poll /v1/get_result until status=Ready. Returns image URL."""
    start = time.time()
    while time.time() - start < timeout:
        req = urllib.request.Request(
            f"{API_BASE}/v1/get_result?id={task_id}",
            headers={"x-key": api_key},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        status = data.get("status")
        if status == "Ready":
            return data["result"]["sample"]
        elif status in ("Error", "Failed", "Content Moderated"):
            raise RuntimeError(f"Task {status}: {data}")
        time.sleep(2)
        print(".", end="", flush=True)
    raise TimeoutError(f"Generation timed out after {timeout}s")


def save_image(url: str, output: str):
    """Download result image from BFL CDN URL."""
    with urllib.request.urlopen(url) as resp:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.read())


def run(
    prompt: str,
    output: str = "kontext-output.png",
    input_image: str = None,
    input_image_2: str = None,
    input_image_3: str = None,
    input_image_4: str = None,
    seed: int = None,
    aspect_ratio: str = None,
    output_format: str = "png",
    model: str = DEFAULT_MODEL,
) -> str:
    mode = "edit" if input_image else "text-to-image"
    ref_count = sum(1 for x in [input_image, input_image_2, input_image_3, input_image_4] if x)
    if ref_count > 1:
        mode = f"multi-ref ({ref_count} images)"

    model_info = MODELS.get(model, (model, "custom"))
    print(f"Model  : {model} — {model_info[1]}")
    print(f"Mode   : {mode}")
    print(f"Prompt : {prompt}")
    if input_image:
        print(f"Input  : {input_image}")
    if seed:
        print(f"Seed   : {seed}")

    api_key = get_bfl_key()

    payload = {"prompt": prompt, "output_format": output_format}
    if input_image:   payload["input_image"]   = image_arg(input_image)
    if input_image_2: payload["input_image_2"] = image_arg(input_image_2)
    if input_image_3: payload["input_image_3"] = image_arg(input_image_3)
    if input_image_4: payload["input_image_4"] = image_arg(input_image_4)
    if seed is not None:   payload["seed"] = seed
    if aspect_ratio:       payload["aspect_ratio"] = aspect_ratio

    print("Submitting", end="", flush=True)
    task_id = submit_task(api_key, payload, model=model)
    print(f" → {task_id}")
    print("Generating", end="", flush=True)

    img_url = poll_result(api_key, task_id)
    print(" done.")

    save_image(img_url, output)
    size_kb = Path(output).stat().st_size // 1024
    print(f"Saved  : {output} ({size_kb}KB)")
    if seed:
        print(f"Seed   : {seed}  ← save to reproduce")
    return output


def main():
    p = argparse.ArgumentParser(
        description="FLUX.1 Kontext [pro] — surgical image editing + generation via BFL API"
    )
    p.add_argument("prompt", help="Edit or generation prompt")
    p.add_argument("--output", "-o", default="kontext-output.png")
    p.add_argument("--input",  "-i", default=None, help="Input image to edit (path or URL)")
    p.add_argument("--input2", default=None, help="2nd reference image (multi-ref, experimental)")
    p.add_argument("--input3", default=None, help="3rd reference image")
    p.add_argument("--input4", default=None, help="4th reference image")
    p.add_argument("--seed",   "-s", type=int, default=None, help="Fixed seed for reproducibility")
    p.add_argument("--aspect-ratio", "-a", default=None, help="e.g. 1:1, 16:9, 3:4, 9:16")
    p.add_argument("--format", "-f", default="png", choices=["png", "jpeg"])
    p.add_argument("--model", "-m", default=DEFAULT_MODEL, choices=list(MODELS.keys()),
                   help=f"Model to use. Default: {DEFAULT_MODEL}. Options: {', '.join(MODELS.keys())}")
    args = p.parse_args()

    run(
        prompt=args.prompt,
        output=args.output,
        input_image=args.input,
        input_image_2=args.input2,
        input_image_3=args.input3,
        input_image_4=args.input4,
        seed=args.seed,
        aspect_ratio=args.aspect_ratio,
        output_format=args.format,
        model=args.model,
    )


if __name__ == "__main__":
    main()
