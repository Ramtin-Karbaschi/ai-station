#!/usr/bin/env python3
"""OpenAI-compatible streaming benchmark runner (public-safe cases)."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required") from exc
    return yaml.safe_load(text) or {}


def probe_vram() -> int | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        return int(out.strip().splitlines()[0].strip())
    except Exception:
        return None


def expand_pad(content: str, pad_tokens_approx: int) -> str:
    # Roughly 4 chars/token for synthetic filler.
    filler = ("lorem " * 200).strip() + "\n"
    need = max(pad_tokens_approx, 0) * 4
    pad = (filler * ((need // len(filler)) + 1))[:need]
    return content.replace("{{PAD}}", pad)


def chat_completion(
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> dict[str, Any]:
    url = endpoint.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    ttft = None
    completion_tokens = 0
    text_parts: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if ttft is None:
                ttft = (time.perf_counter() - started) * 1000.0
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                text_parts.append(content)
                completion_tokens += max(len(content.split()), 1)
            usage = chunk.get("usage") or {}
            if usage.get("completion_tokens"):
                completion_tokens = int(usage["completion_tokens"])

    e2e = (time.perf_counter() - started) * 1000.0
    decode_tps = None
    if ttft is not None and completion_tokens > 0:
        decode_s = max((e2e - ttft) / 1000.0, 0.001)
        decode_tps = completion_tokens / decode_s

    return {
        "ok": True,
        "ttft_ms": ttft,
        "e2e_ms": e2e,
        "completion_tokens": completion_tokens,
        "decode_tokens_per_s": decode_tps,
        "text": "".join(text_parts),
        "error": None,
    }


def run_case(cfg: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    messages = list(case["messages"])
    if case.get("pad_tokens_approx"):
        messages = [
            {
                **messages[0],
                "content": expand_pad(
                    messages[0]["content"],
                    int(case["pad_tokens_approx"]),
                ),
            }
        ]
    vram_before = probe_vram()
    try:
        result = chat_completion(
            cfg["endpoint"],
            cfg["model"],
            messages,
            int(case.get("max_tokens") or 64),
            float(case.get("temperature") or 0),
            float(cfg.get("timeout_seconds") or 180),
        )
    except Exception as exc:
        return {
            "id": case["id"],
            "ok": False,
            "ttft_ms": None,
            "decode_tokens_per_s": None,
            "e2e_ms": None,
            "peak_vram_mib": probe_vram(),
            "error": repr(exc),
        }
    vram_after = probe_vram()
    peak = None
    if vram_before is not None and vram_after is not None:
        peak = max(vram_before, vram_after)
    return {
        "id": case["id"],
        "ok": result["ok"],
        "prompt_tokens": None,
        "completion_tokens": result.get("completion_tokens"),
        "ttft_ms": result.get("ttft_ms"),
        "prompt_tokens_per_s": None,
        "decode_tokens_per_s": result.get("decode_tokens_per_s"),
        "e2e_ms": result.get("e2e_ms"),
        "peak_vram_mib": peak,
        "error": result.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    dataset = Path(cfg["dataset"])
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()

    if args.dry_run:
        print(f"Would run {len(cases)} cases against {cfg['endpoint']}")
        return 0

    for _ in range(int(cfg.get("warmup_requests") or 0)):
        try:
            chat_completion(
                cfg["endpoint"],
                cfg["model"],
                [{"role": "user", "content": "ping"}],
                4,
                0,
                float(cfg.get("timeout_seconds") or 180),
            )
        except Exception as exc:
            print(f"WARNING: warm-up failed: {exc}")

    results = [run_case(cfg, case) for case in cases]
    finished = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "engine": cfg.get("engine"),
        "model": cfg.get("model"),
        "provider_id": cfg.get("provider_id"),
        "endpoint": cfg.get("endpoint"),
        "quantization": cfg.get("quantization"),
        "started_at": started,
        "finished_at": finished,
        "hardware_profile_ref": "config/hardware-profile.json",
        "notes": list(cfg.get("notes") or []),
        "cases": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    ok = sum(1 for case in results if case["ok"])
    print(f"Wrote {out} ({ok}/{len(results)} cases ok)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
