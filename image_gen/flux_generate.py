#!/usr/bin/env python3
"""
flux_generate.py — Headless FLUX image generation via ComfyUI API

Usage:
    # Make sure ComfyUI is running first: ~/base/ai/ComfyUI/run_comfy.sh
    python flux_generate.py "wide-leg denim pants with rounded rectangular panels in a 3x4 grid" --output out.png
    python flux_generate.py "..." --width 1024 --height 1280 --steps 28 --seed 42 --lora techwear
"""

import argparse
import json
import random
import time
import urllib.request
import urllib.error
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"

# --- FLUX.1 dev workflow template ---
# Uses: UNETLoader, DualCLIPLoader, VAELoader, CLIPTextEncodeFlux,
#       EmptySD3LatentImage, SamplerCustomAdvanced, VAEDecode, SaveImage
WORKFLOW = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"}
    },
    "2": {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": "t5xxl_fp16.safetensors",
            "clip_name2": "clip_l.safetensors",
            "type": "flux"
        }
    },
    "3": {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "ae.safetensors"}
    },
    "4": {
        "class_type": "CLIPTextEncodeFlux",
        "inputs": {
            "clip": ["2", 0],
            "clip_l": "__PROMPT__",
            "t5xxl": "__PROMPT__",
            "guidance": 3.5
        }
    },
    "5": {
        "class_type": "EmptySD3LatentImage",
        "inputs": {
            "width": "__WIDTH__",
            "height": "__HEIGHT__",
            "batch_size": 1
        }
    },
    "6": {
        "class_type": "ModelSamplingFlux",
        "inputs": {
            "model": ["1", 0],
            "max_shift": 1.15,
            "base_shift": 0.5,
            "width": "__WIDTH__",
            "height": "__HEIGHT__"
        }
    },
    "7": {
        "class_type": "BasicGuider",
        "inputs": {
            "model": ["6", 0],
            "conditioning": ["4", 0]
        }
    },
    "8": {
        "class_type": "BasicScheduler",
        "inputs": {
            "model": ["6", 0],
            "scheduler": "simple",
            "steps": "__STEPS__",
            "denoise": 1.0
        }
    },
    "9": {
        "class_type": "KSamplerSelect",
        "inputs": {"sampler_name": "euler"}
    },
    "10": {
        "class_type": "RandomNoise",
        "inputs": {"noise_seed": "__SEED__"}
    },
    "11": {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["10", 0],
            "guider": ["7", 0],
            "sampler": ["9", 0],
            "sigmas": ["8", 0],
            "latent_image": ["5", 0]
        }
    },
    "12": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["11", 0],
            "vae": ["3", 0]
        }
    },
    "13": {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["12", 0],
            "filename_prefix": "__PREFIX__"
        }
    }
}

LORA_NODE = {
    "class_type": "LoraLoader",
    "inputs": {
        "model": ["1", 0],
        "clip": ["2", 0],
        "lora_name": "__LORA__",
        "strength_model": 0.8,
        "strength_clip": 0.8
    }
}

LORA_MAP = {
    "techwear": "Techwear_Fashion_Flux.safetensors",
    "analog":   "2000analogcore_v3.safetensors",
}


def wait_for_comfy(timeout=30):
    """Wait until ComfyUI server is ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def submit_prompt(workflow: dict) -> str:
    """Submit workflow to ComfyUI, return prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["prompt_id"]


def poll_until_done(prompt_id: str, poll_interval=2, timeout=600) -> dict:
    """Poll /history until the prompt is complete."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{COMFY_URL}/history/{prompt_id}") as resp:
                history = json.loads(resp.read())
                if prompt_id in history:
                    return history[prompt_id]
        except Exception:
            pass
        time.sleep(poll_interval)
    raise TimeoutError(f"Generation timed out after {timeout}s")


def fetch_image(filename: str, subfolder: str, folder_type: str) -> bytes:
    """Download generated image bytes from ComfyUI."""
    params = f"filename={filename}&subfolder={subfolder}&type={folder_type}"
    with urllib.request.urlopen(f"{COMFY_URL}/view?{params}") as resp:
        return resp.read()


def generate(
    prompt: str,
    output: str = "output.png",
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    seed: int = None,
    lora: str = None,
    lora_strength: float = 0.8,
    guidance: float = 3.5,
):
    seed = seed if seed is not None else random.randint(0, 2**32 - 1)
    prefix = Path(output).stem

    print(f"Prompt : {prompt}")
    print(f"Size   : {width}x{height} | Steps: {steps} | Seed: {seed}")
    if lora:
        print(f"LoRA   : {lora} (strength {lora_strength})")

    if not wait_for_comfy():
        raise RuntimeError("ComfyUI not reachable at 127.0.0.1:8188 — is it running?")

    # Build workflow from template
    wf = json.loads(json.dumps(WORKFLOW))  # deep copy

    # Inject LoRA if requested
    if lora:
        lora_file = LORA_MAP.get(lora, lora)  # allow raw filename too
        lora_node = json.loads(json.dumps(LORA_NODE))
        lora_node["inputs"]["lora_name"] = lora_file
        lora_node["inputs"]["strength_model"] = lora_strength
        lora_node["inputs"]["strength_clip"] = lora_strength
        wf["14"] = lora_node
        # Rewire model + clip through LoRA node
        wf["6"]["inputs"]["model"] = ["14", 0]
        wf["4"]["inputs"]["clip"] = ["14", 1]

    # Substitute placeholders
    wf_str = json.dumps(wf)
    wf_str = wf_str.replace('"__PROMPT__"', json.dumps(prompt))
    wf_str = wf_str.replace('"__WIDTH__"', str(width))
    wf_str = wf_str.replace('"__HEIGHT__"', str(height))
    wf_str = wf_str.replace('"__STEPS__"', str(steps))
    wf_str = wf_str.replace('"__SEED__"', str(seed))
    wf_str = wf_str.replace('"__PREFIX__"', json.dumps(prefix))
    wf = json.loads(wf_str)
    wf["4"]["inputs"]["guidance"] = guidance

    print("Submitting to ComfyUI...")
    prompt_id = submit_prompt(wf)
    print(f"Prompt ID: {prompt_id}")

    print("Generating", end="", flush=True)
    result = poll_until_done(prompt_id)
    print(" done.")

    # Extract output image
    outputs = result.get("outputs", {})
    for node_id, node_out in outputs.items():
        images = node_out.get("images", [])
        if images:
            img_info = images[0]
            img_bytes = fetch_image(
                img_info["filename"],
                img_info.get("subfolder", ""),
                img_info.get("type", "output")
            )
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            print(f"Saved  : {out_path} ({len(img_bytes) // 1024}KB)")
            print(f"Seed   : {seed}  ← save this to reproduce")
            return str(out_path)

    raise RuntimeError("No output images found in ComfyUI response")


def main():
    parser = argparse.ArgumentParser(description="Headless FLUX generation via ComfyUI API")
    parser.add_argument("prompt", help="Text prompt")
    parser.add_argument("--output", "-o", default="output.png", help="Output image path")
    parser.add_argument("--width",  "-W", type=int, default=1024)
    parser.add_argument("--height", "-H", type=int, default=1024)
    parser.add_argument("--steps",  "-s", type=int, default=28)
    parser.add_argument("--seed",   "-S", type=int, default=None, help="Fixed seed for reproducibility")
    parser.add_argument("--lora",   "-l", default=None, help="LoRA name: techwear, analog, or filename")
    parser.add_argument("--lora-strength", type=float, default=0.8)
    parser.add_argument("--guidance", "-g", type=float, default=3.5)
    args = parser.parse_args()

    generate(
        prompt=args.prompt,
        output=args.output,
        width=args.width,
        height=args.height,
        steps=args.steps,
        seed=args.seed,
        lora=args.lora,
        lora_strength=args.lora_strength,
        guidance=args.guidance,
    )


if __name__ == "__main__":
    main()
