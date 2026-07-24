"""Resource admission controller for AI Station providers.

Decisions:
  START
  START_WITH_REDUCED_CONTEXT
  STOP_CONFLICTING_PROVIDER_AND_START
  QUEUE
  FALLBACK
  REJECT
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(os.getenv("AI_STATION_PROJECT_DIR", "/opt/ai-station"))
PROVIDERS_PATH = Path(
    os.getenv("AI_STATION_PROVIDERS", str(PROJECT_DIR / "config/providers.yaml"))
)
HARDWARE_PATH = Path(
    os.getenv(
        "AI_STATION_HARDWARE_PROFILE",
        str(PROJECT_DIR / "config/hardware-profile.json"),
    )
)
ACTIVE_PROFILE_FILE = Path(
    os.getenv(
        "AI_STATION_ACTIVE_PROFILE_FILE",
        "/srv/ai-station/runtime/active-heavy-profile",
    )
)

DecisionName = str


@dataclass
class AdmissionDecision:
    decision: DecisionName
    provider_id: str
    requested_context: int
    effective_context: int
    required_vram_mib: int
    free_vram_mib: int
    free_ram_mib: int
    free_storage_mib: int
    active_heavy: list[str] = field(default_factory=list)
    stop_providers: list[str] = field(default_factory=list)
    fallback_provider: str | None = None
    reasons: list[str] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def explain(self) -> str:
        lines = [
            f"decision: {self.decision}",
            f"provider: {self.provider_id}",
            f"requested_context: {self.requested_context}",
            f"effective_context: {self.effective_context}",
            f"required_vram_mib: {self.required_vram_mib}",
            f"free_vram_mib: {self.free_vram_mib}",
            f"free_ram_mib: {self.free_ram_mib}",
            f"free_storage_mib: {self.free_storage_mib}",
            f"active_heavy: {', '.join(self.active_heavy) or '(none)'}",
        ]
        if self.stop_providers:
            lines.append(f"stop_providers: {', '.join(self.stop_providers)}")
        if self.fallback_provider:
            lines.append(f"fallback_provider: {self.fallback_provider}")
        lines.append("reasons:")
        for reason in self.reasons:
            lines.append(f"  - {reason}")
        lines.append("budget:")
        for key, value in self.budget.items():
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PyYAML is required to load config/providers.yaml"
            ) from exc
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid provider registry: {path}")
    return data


def load_providers(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml_or_json(path or PROVIDERS_PATH)


def load_hardware(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or HARDWARE_PATH).read_text(encoding="utf-8"))


def get_provider(registry: dict[str, Any], provider_id: str) -> dict[str, Any]:
    providers = registry.get("providers") or {}
    if provider_id in providers:
        return dict(providers[provider_id])
    for provider in providers.values():
        if provider_id in (provider.get("catalog_ids") or []):
            return dict(provider)
        if provider_id in (provider.get("model_aliases") or []):
            return dict(provider)
        if provider_id == provider.get("profile"):
            return dict(provider)
        if provider_id == provider.get("service"):
            return dict(provider)
    raise KeyError(f"Unknown provider: {provider_id}")


def list_heavy_provider_ids(registry: dict[str, Any]) -> list[str]:
    return [
        pid
        for pid, provider in (registry.get("providers") or {}).items()
        if provider.get("heavy") is True
    ]


def read_active_heavy_profiles() -> list[str]:
    if not ACTIVE_PROFILE_FILE.is_file():
        return []
    value = ACTIVE_PROFILE_FILE.read_text(encoding="utf-8").strip()
    return [value] if value else []


def probe_free_vram_mib() -> int:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = (result.stdout or "").strip().splitlines()[0]
        return int(line.strip())
    except Exception:
        return 0


def probe_free_ram_mib() -> int:
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                kb = int(line.split()[1])
                return kb // 1024
    except Exception:
        pass
    return 0


def probe_free_storage_mib(path: str = "/srv/ai-station") -> int:
    try:
        usage = shutil.disk_usage(path)
        return usage.free // (1024 * 1024)
    except Exception:
        return 0


def estimate_required_vram_mib(provider: dict[str, Any], context: int) -> int:
    base = int(provider.get("minimum_vram_mib") or 0)
    per_1k = float(provider.get("kv_cache_mib_per_1k_context") or 0)
    kv = int((max(context, 0) / 1000.0) * per_1k)
    return base + kv


def admit(
    provider_id: str,
    *,
    context: int | None = None,
    registry: dict[str, Any] | None = None,
    hardware: dict[str, Any] | None = None,
    free_vram_mib: int | None = None,
    free_ram_mib: int | None = None,
    free_storage_mib: int | None = None,
    active_heavy: list[str] | None = None,
    queue_depth: int = 0,
) -> AdmissionDecision:
    registry = registry or load_providers()
    hardware = hardware or load_hardware()
    policy = dict(registry.get("admission") or {})
    provider = get_provider(registry, provider_id)
    provider_id = provider["id"]

    requested_context = int(
        context
        if context is not None
        else provider.get("default_context") or 8192
    )
    max_context = int(provider.get("max_context") or requested_context)
    requested_context = min(requested_context, max_context)

    margin_vram = int(policy.get("safety_margin_vram_mib") or 1024)
    margin_ram = int(policy.get("safety_margin_ram_mib") or 4096)
    max_heavy = int(policy.get("max_active_heavy") or 1)
    allow_auto_stop = bool(policy.get("allow_auto_stop_production", True))
    fallback = provider.get("fallback_provider") or policy.get(
        "default_fallback_provider"
    )

    if free_vram_mib is None:
        free_vram_mib = probe_free_vram_mib()
    if free_ram_mib is None:
        free_ram_mib = probe_free_ram_mib()
    if free_storage_mib is None:
        free_storage_mib = probe_free_storage_mib()
    if active_heavy is None:
        # Map profile names to provider ids.
        profiles = read_active_heavy_profiles()
        active_heavy = []
        for profile in profiles:
            try:
                active_heavy.append(get_provider(registry, profile)["id"])
            except KeyError:
                active_heavy.append(profile)

    required_storage = int(provider.get("minimum_storage_mib") or 0)
    required_ram = int(provider.get("minimum_ram_mib") or 0) + margin_ram

    reasons: list[str] = []
    budget = {
        "safety_margin_vram_mib": margin_vram,
        "safety_margin_ram_mib": margin_ram,
        "max_active_heavy": max_heavy,
        "gpu_vram_total_mib": (
            hardware.get("gpu", {}).get("vram_total_mib")
        ),
        "wsl_visible_ram_gib": (
            hardware.get("memory", {}).get("wsl_visible_total_gib")
        ),
    }

    if free_storage_mib < required_storage + 2048:
        return AdmissionDecision(
            decision="REJECT",
            provider_id=provider_id,
            requested_context=requested_context,
            effective_context=requested_context,
            required_vram_mib=estimate_required_vram_mib(
                provider, requested_context
            ),
            free_vram_mib=free_vram_mib,
            free_ram_mib=free_ram_mib,
            free_storage_mib=free_storage_mib,
            active_heavy=list(active_heavy),
            fallback_provider=fallback if fallback != provider_id else None,
            reasons=[
                "insufficient storage for model artifact footprint",
                f"need>={required_storage + 2048} MiB free, have={free_storage_mib}",
            ],
            budget=budget,
        )

    if free_ram_mib < required_ram:
        return AdmissionDecision(
            decision="REJECT",
            provider_id=provider_id,
            requested_context=requested_context,
            effective_context=requested_context,
            required_vram_mib=estimate_required_vram_mib(
                provider, requested_context
            ),
            free_vram_mib=free_vram_mib,
            free_ram_mib=free_ram_mib,
            free_storage_mib=free_storage_mib,
            active_heavy=list(active_heavy),
            fallback_provider=fallback if fallback != provider_id else None,
            reasons=[
                "insufficient system RAM including safety margin",
                f"need>={required_ram} MiB available, have={free_ram_mib}",
            ],
            budget=budget,
        )

    required_full = estimate_required_vram_mib(provider, requested_context)
    conflicts = [pid for pid in active_heavy if pid != provider_id]

    if provider.get("heavy") and conflicts and len(conflicts) >= max_heavy:
        if allow_auto_stop:
            # After stop, assume nearly full GPU VRAM becomes available.
            gpu_total = int(
                hardware.get("gpu", {}).get("vram_total_mib")
                or (free_vram_mib + 1)
            )
            projected_free = max(free_vram_mib, gpu_total - margin_vram)
            if projected_free >= required_full + margin_vram:
                reasons.append(
                    "conflicting heavy provider will be stopped before start"
                )
                reasons.append(
                    f"projected_free_vram_mib={projected_free} covers "
                    f"required={required_full}+margin={margin_vram}"
                )
                return AdmissionDecision(
                    decision="STOP_CONFLICTING_PROVIDER_AND_START",
                    provider_id=provider_id,
                    requested_context=requested_context,
                    effective_context=requested_context,
                    required_vram_mib=required_full,
                    free_vram_mib=free_vram_mib,
                    free_ram_mib=free_ram_mib,
                    free_storage_mib=free_storage_mib,
                    active_heavy=list(active_heavy),
                    stop_providers=conflicts,
                    reasons=reasons,
                    budget=budget,
                )
            reasons.append(
                "conflicting heavy provider present but projected VRAM "
                "still insufficient after stop"
            )
        else:
            if queue_depth >= 0:
                return AdmissionDecision(
                    decision="QUEUE",
                    provider_id=provider_id,
                    requested_context=requested_context,
                    effective_context=requested_context,
                    required_vram_mib=required_full,
                    free_vram_mib=free_vram_mib,
                    free_ram_mib=free_ram_mib,
                    free_storage_mib=free_storage_mib,
                    active_heavy=list(active_heavy),
                    reasons=[
                        "heavy provider conflict and auto-stop is disabled",
                        "request may wait until the active heavy provider stops",
                    ],
                    budget=budget,
                )

    # Already active same provider: start is a no-op path.
    if provider_id in active_heavy and not conflicts:
        reasons.append("provider already active")
        return AdmissionDecision(
            decision="START",
            provider_id=provider_id,
            requested_context=requested_context,
            effective_context=requested_context,
            required_vram_mib=required_full,
            free_vram_mib=free_vram_mib,
            free_ram_mib=free_ram_mib,
            free_storage_mib=free_storage_mib,
            active_heavy=list(active_heavy),
            reasons=reasons,
            budget=budget,
        )

    available = free_vram_mib
    # If we will stop conflicts, recompute against projected free.
    if conflicts and allow_auto_stop and provider.get("heavy"):
        gpu_total = int(
            hardware.get("gpu", {}).get("vram_total_mib") or free_vram_mib
        )
        available = max(free_vram_mib, gpu_total - margin_vram)

    if available >= required_full + margin_vram:
        decision = (
            "STOP_CONFLICTING_PROVIDER_AND_START"
            if conflicts and provider.get("heavy") and allow_auto_stop
            else "START"
        )
        if decision == "STOP_CONFLICTING_PROVIDER_AND_START":
            reasons.append("stop conflicting heavy provider then start")
        else:
            reasons.append("VRAM/RAM/storage budgets satisfied at full context")
        return AdmissionDecision(
            decision=decision,
            provider_id=provider_id,
            requested_context=requested_context,
            effective_context=requested_context,
            required_vram_mib=required_full,
            free_vram_mib=free_vram_mib,
            free_ram_mib=free_ram_mib,
            free_storage_mib=free_storage_mib,
            active_heavy=list(active_heavy),
            stop_providers=conflicts if decision.startswith("STOP") else [],
            reasons=reasons,
            budget=budget,
        )

    # Try reduced context.
    reduced = requested_context
    while reduced >= 2048:
        reduced //= 2
        required_reduced = estimate_required_vram_mib(provider, reduced)
        if available >= required_reduced + margin_vram:
            reasons.append(
                "full context exceeds VRAM budget; reduced context fits"
            )
            reasons.append(
                f"reduced_context={reduced} requires={required_reduced} MiB"
            )
            decision = (
                "STOP_CONFLICTING_PROVIDER_AND_START"
                if conflicts and provider.get("heavy") and allow_auto_stop
                else "START_WITH_REDUCED_CONTEXT"
            )
            # Prefer explicit reduced-context decision name when no stop needed.
            if not (conflicts and provider.get("heavy") and allow_auto_stop):
                decision = "START_WITH_REDUCED_CONTEXT"
            else:
                # Still communicate reduced context via effective_context.
                reasons.append(
                    "will stop conflicting provider and start with reduced context"
                )
                decision = "START_WITH_REDUCED_CONTEXT"
            return AdmissionDecision(
                decision=decision,
                provider_id=provider_id,
                requested_context=requested_context,
                effective_context=reduced,
                required_vram_mib=required_reduced,
                free_vram_mib=free_vram_mib,
                free_ram_mib=free_ram_mib,
                free_storage_mib=free_storage_mib,
                active_heavy=list(active_heavy),
                stop_providers=(
                    conflicts
                    if conflicts and provider.get("heavy") and allow_auto_stop
                    else []
                ),
                reasons=reasons,
                budget=budget,
            )

    if fallback and fallback != provider_id:
        return AdmissionDecision(
            decision="FALLBACK",
            provider_id=provider_id,
            requested_context=requested_context,
            effective_context=requested_context,
            required_vram_mib=required_full,
            free_vram_mib=free_vram_mib,
            free_ram_mib=free_ram_mib,
            free_storage_mib=free_storage_mib,
            active_heavy=list(active_heavy),
            fallback_provider=fallback,
            reasons=[
                "insufficient VRAM even after context reduction",
                f"suggest fallback provider {fallback}",
            ],
            budget=budget,
        )

    return AdmissionDecision(
        decision="REJECT",
        provider_id=provider_id,
        requested_context=requested_context,
        effective_context=requested_context,
        required_vram_mib=required_full,
        free_vram_mib=free_vram_mib,
        free_ram_mib=free_ram_mib,
        free_storage_mib=free_storage_mib,
        active_heavy=list(active_heavy),
        reasons=[
            "insufficient VRAM for provider weights and KV cache",
            f"need>={required_full + margin_vram} MiB, available={available}",
        ],
        budget=budget,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AI Station admission dry-run")
    parser.add_argument("provider_id")
    parser.add_argument("--context", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--free-vram-mib", type=int, default=None)
    parser.add_argument("--free-ram-mib", type=int, default=None)
    parser.add_argument("--free-storage-mib", type=int, default=None)
    parser.add_argument(
        "--active-heavy",
        default=None,
        help="Comma-separated active heavy provider ids (override)",
    )
    args = parser.parse_args(argv)

    active = None
    if args.active_heavy is not None:
        active = [part.strip() for part in args.active_heavy.split(",") if part.strip()]

    decision = admit(
        args.provider_id,
        context=args.context,
        free_vram_mib=args.free_vram_mib,
        free_ram_mib=args.free_ram_mib,
        free_storage_mib=args.free_storage_mib,
        active_heavy=active,
    )
    if args.json:
        print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    else:
        print(decision.explain())
    return 0 if decision.decision != "REJECT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
