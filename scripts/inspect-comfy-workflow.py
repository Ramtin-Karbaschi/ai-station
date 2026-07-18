#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print("Usage: inspect-comfy-workflow.py workflow_api.json")
    sys.exit(2)

path = Path(sys.argv[1])
data = json.loads(path.read_text())

if not (isinstance(data, dict) and all(str(k).isdigit() for k in data.keys())):
    print("ERROR: This is not API Format. Open WebUI requires API Format.")
    sys.exit(1)

for node_id, node in data.items():
    cls = node.get("class_type", "")
    inputs = node.get("inputs", {})
    title = node.get("_meta", {}).get("title", "")

    interesting_keys = {
        "text", "prompt", "unet_name", "ckpt_name",
        "width", "height", "steps", "seed", "noise_seed",
        "cfg", "sampler_name", "scheduler"
    }

    if interesting_keys & set(inputs.keys()) or any(s in cls.lower() for s in [
        "clip", "text", "sampler", "latent", "unet", "vae", "model"
    ]):
        print(f"Node ID: {node_id}")
        print(f"Class:   {cls}")
        if title:
            print(f"Title:   {title}")
        print("Inputs:")
        for k, v in inputs.items():
            if k in interesting_keys:
                print(f"  - {k}: {v}")
        print()
