from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import httpx
import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from apps.gateway.app.admission import admit, probe_free_ram_mib
from apps.gateway.app.catalog import (
    CATALOG_PATH,
    cached_catalog,
    catalog_models,
    load_catalog,
    model_matches,
    normalize_model_id,
    public_model_id,
    selectable_models,
    valid_public_model_ids,
)
from apps.gateway.app.media import assert_media_idle
from apps.gateway.app.lifecycle_lock import HELD_FD, LifecycleBusy, LifecycleLock
from apps.gateway.app.lifecycle import (
    clear_active_profile,
    preferred_provider_by_service,
    publish_active_profile,
    read_active_profile,
)
from apps.gateway.app.paths import PROJECT_DIR
from apps.gateway.app.stt import (
    CALL_ASR_UPSTREAM_MODEL,
    extract_audio_request,
    transcribe_station_audio,
)
from apps.gateway.app.providers import (
    heavy_services,
    provider_for_catalog_model,
    registry,
    service_profiles,
)
from apps.gateway.app.readiness import wait_ready
from apps.gateway.app import translation as openai_translation

COMPOSE_HELPER = Path(
    os.getenv(
        "AI_STATION_COMPOSE_HELPER",
        str(PROJECT_DIR / "scripts" / "compose-ai-station.sh"),
    )
)
COMPOSE_BASE = (
    [str(COMPOSE_HELPER)]
    if COMPOSE_HELPER.is_file()
    else [
        "docker",
        "compose",
        "--project-name",
        os.getenv("COMPOSE_PROJECT_NAME", "ai-station"),
        "--env-file",
        str(PROJECT_DIR / ".env"),
    ]
)

MODEL_LOCK = asyncio.Lock()
QUEUE: list[dict[str, Any]] = []
ACTIVE_MODEL_ID: str | None = None
ACTIVE_RUNTIME_MODE: str | None = None
GATEWAY_VERSION = "0.6.0"

app = FastAPI(title="AI Station Gateway", version=GATEWAY_VERSION)


def emit_contract_telemetry(event: str, **fields: Any) -> None:
    """Emit content-free OpenAI contract telemetry for client debugging."""
    print(
        json.dumps({"event": event, **fields}, ensure_ascii=True, sort_keys=True),
        file=sys.stderr,
        flush=True,
    )


def response_shape(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    return {
        "content_chars": len(content) if isinstance(content, str) else 0,
        "finish_reason": choice.get("finish_reason"),
        "tool_calls": len(message.get("tool_calls") or []),
    }


def safe_upstream_error(error_bytes: bytes, status_code: int) -> tuple[str, str]:
    """Return a useful client error and a content-free telemetry category."""
    message = ""
    category = f"http_{status_code}"
    try:
        payload = json.loads(error_bytes)
        detail = payload.get("error") or payload.get("detail")
        if isinstance(detail, dict):
            message = str(detail.get("message") or "")
            declared = detail.get("type") or detail.get("code")
            if declared:
                category = str(declared)[:80]
        elif detail is not None:
            message = str(detail)
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        pass

    if "exceeds the available context size" in message:
        return message[:300], "context_window_exceeded"
    return f"Local model returned HTTP {status_code}.", category


def get_model(model_id: str) -> dict[str, Any]:
    requested_id = normalize_model_id(model_id)
    for model in selectable_models():
        if model_matches(model, requested_id):
            return model
    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Unknown model '{requested_id}'.",
            "valid_model_names": valid_public_model_ids(),
        },
    )


def run_compose(
    args: list[str],
    timeout: int = 180,
    lifecycle_fd: int | None = None,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if env_overrides:
        environment.update(env_overrides)
    return subprocess.run(
        COMPOSE_BASE + args,
        cwd=str(PROJECT_DIR),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        pass_fds=(lifecycle_fd,) if lifecycle_fd is not None else (),
        env=environment,
    )


async def compose(
    args: list[str],
    timeout: int = 180,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # Do not release the cross-process lifecycle lock while Docker is still
    # mutating state if the HTTP caller disconnects/cancels.  Drain the worker
    # before propagating cancellation so the transition has a clear boundary.
    task = asyncio.create_task(
        asyncio.to_thread(run_compose, args, timeout, HELD_FD.get(), env_overrides)
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        current = asyncio.current_task()
        worker_error: BaseException | None = None
        with anyio.CancelScope(shield=True):
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    if current is not None and hasattr(current, "uncancel"):
                        current.uncancel()
                except BaseException as exc:
                    worker_error = exc
                    break
        if worker_error is not None and not task.done():
            task.cancel()
        if task.done() and not task.cancelled():
            task.exception()
        raise


def profile_args_for_services(services: list[str]) -> list[str]:
    args: list[str] = []
    seen: set[str] = set()
    profiles = service_profiles()
    for service in services:
        profile = profiles.get(service)
        if profile and profile not in seen:
            args.extend(["--profile", profile])
            seen.add(profile)
    return args


async def stop_other_heavy(
    target_service: str,
    active_provider_ids: list[str] | None = None,
    stop_provider_ids: list[str] | None = None,
) -> None:
    global ACTIVE_MODEL_ID, ACTIVE_RUNTIME_MODE
    services = heavy_services()
    if active_provider_ids is not None:
        owners = preferred_provider_by_service((registry().get("providers") or {}).values())
        active_services = {
            str(owners[service].get("service"))
            for service in owners
            if str(owners[service].get("id"))
            in (stop_provider_ids if stop_provider_ids is not None else active_provider_ids)
        }
        services = [service for service in services if service in active_services]
    to_stop = [s for s in services if s != target_service]
    if not to_stop:
        return
    result = await compose(
        [*profile_args_for_services(to_stop), "stop", *to_stop], timeout=240
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "stop_runtime",
                "target_service": target_service,
                "services": to_stop,
                "returncode": result.returncode,
                "message": (
                    "Unable to stop conflicting runtime; launch was not attempted. "
                    "Retry after the active runtime is stopped."
                ),
            },
        )
    ACTIVE_MODEL_ID = None
    ACTIVE_RUNTIME_MODE = None


async def verify_active_gpu_placements(
    target_service: str,
    active_provider_ids: list[str],
    excluded_provider_ids: list[str] | None = None,
) -> bool:
    """Fail closed when an existing container's GPU reservation is unknown."""
    owners = preferred_provider_by_service(
        provider for provider in (registry().get("providers") or {}).values()
        if provider.get("heavy") is True
    )
    excluded = set(excluded_provider_ids or [])
    for provider in owners.values():
        provider_id = str(provider.get("id"))
        service = str(provider.get("service") or "")
        if provider_id not in active_provider_ids or provider_id in excluded or service == target_service:
            continue
        try:
            expected = str(int(provider.get("gpu_index") or 0))
        except (TypeError, ValueError):
            return False
        observed = await compose(
            [*profile_args_for_services([service]), "ps", "-q", service], timeout=30
        )
        container_id = next((line.strip() for line in observed.stdout.splitlines() if line.strip()), "")
        if observed.returncode != 0 or not container_id:
            return False
        inspected = await asyncio.to_thread(
            subprocess.run,
            ["docker", "inspect", "--format", "{{json .HostConfig.DeviceRequests}}", container_id],
            cwd=str(PROJECT_DIR),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if inspected.returncode != 0:
            return False
        try:
            requests = json.loads(inspected.stdout.strip() or "null")
        except (json.JSONDecodeError, TypeError):
            return False
        if not valid_gpu_device_requests(requests, expected):
            return False
    return True


def valid_gpu_device_requests(requests: Any, expected: str) -> bool:
    """Accept only one explicit NVIDIA device reservation, never ``all``."""
    if not isinstance(requests, list) or len(requests) != 1:
        return False
    request = requests[0]
    if not isinstance(request, dict):
        return False
    driver = request.get("Driver") or request.get("driver")
    count = request.get("Count", request.get("count"))
    device_ids = request.get("DeviceIDs", request.get("device_ids"))
    if str(driver).casefold() != "nvidia" or count not in (0, "0"):
        return False
    return isinstance(device_ids, list) and device_ids == [expected]


async def rollback_started_target(service: str) -> None:
    """Best-effort stop for a target this transition started itself."""
    emit_contract_telemetry("lifecycle_transition", state="stopping", service=service)
    task = asyncio.create_task(
        compose([*profile_args_for_services([service]), "stop", service], timeout=240)
    )
    current = asyncio.current_task()
    error: BaseException | None = None
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if current is not None and hasattr(current, "uncancel"):
                    current.uncancel()
            except BaseException as exc:
                error = exc
                break
    if error is not None:
        emit_contract_telemetry("lifecycle_transition", state="rollback_failed", service=service, reason=type(error).__name__)
        return
    if task.cancelled():
        emit_contract_telemetry("lifecycle_transition", state="rollback_failed", service=service, reason="cancelled")
        return
    try:
        result = task.result()
    except BaseException as exc:
        emit_contract_telemetry("lifecycle_transition", state="rollback_failed", service=service, reason=type(exc).__name__)
        return
    if result.returncode != 0:
        emit_contract_telemetry("lifecycle_transition", state="rollback_failed", service=service, reason=f"returncode_{result.returncode}")
        return
    emit_contract_telemetry("lifecycle_transition", state="rolled_back", service=service)


async def reconcile_active_profile() -> list[str] | None:
    """Reconcile the shared marker with known running and healthy services.

    A Docker query failure is treated as unknown state: preserve the marker
    and do not infer ownership.  When Docker is observable, registered heavy
    services are returned as active even when health probes fail; health only
    controls whether the shared ready marker may be published.  This also
    catches a live ComfyUI runtime when the saved marker is stale.
    """
    saved = read_active_profile()
    owners = preferred_provider_by_service(
        provider for provider in (registry().get("providers") or {}).values()
        if provider.get("heavy") is True
    )
    # Explicit profiles are required for Compose to include stopped/optional
    # profile definitions in `ps`; without this, a live ComfyUI service can be
    # mistaken for a missing workload.
    try:
        result = await compose(
            [*profile_args_for_services(list(owners)), "ps", "--status", "running", "--services"],
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        emit_contract_telemetry("lifecycle_reconcile", state="unknown", reason="TimeoutExpired")
        return None
    if result.returncode != 0:
        emit_contract_telemetry("lifecycle_reconcile", state="unknown", reason="compose_observation_failed")
        return None
    running = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    observed: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=3) as client:
        for service, provider in owners.items():
            if service not in running:
                continue
            observed.append(provider)
            endpoint = provider.get("health_endpoint")
            if not endpoint:
                continue
            try:
                response = await client.get(str(endpoint))
            except Exception:
                continue
            if response.status_code == 200:
                healthy.append(provider)

    if len(healthy) == 1 and len(observed) == 1:
        profile = str(healthy[0].get("profile") or "")
        if profile:
            if saved != profile:
                publish_active_profile(profile)
                emit_contract_telemetry("lifecycle_reconcile", state="ready", profile=profile)
            return [str(observed[0].get("id"))]

    # Docker is authoritative here.  A marker whose service disappeared or
    # failed health is stale; multiple healthy owners are ambiguous, so clear
    # rather than claim ownership of one of them.
    if saved:
        clear_active_profile(saved)
        emit_contract_telemetry("lifecycle_reconcile", state="cleared", reason="stale_or_ambiguous")
    return [str(provider.get("id")) for provider in observed]


def evaluate_admission(model: dict[str, Any], active_heavy: list[str] | None = None) -> dict[str, Any]:
    provider = provider_for_catalog_model(model)
    policy = (registry().get("admission") or {})
    decision = admit(provider["id"], active_heavy=active_heavy) if active_heavy is not None else admit(provider["id"])
    payload = decision.to_dict()
    payload["enforce"] = bool(policy.get("enforce", True))
    if decision.decision in {
        "REJECT",
        "FALLBACK",
        "QUEUE",
        "START_WITH_REDUCED_CONTEXT",
    } and payload["enforce"]:
        message = {
            "REJECT": None,
            "FALLBACK": "Provider rejected; use fallback explicitly",
            "QUEUE": "Wait until the conflicting runtime stops, then retry.",
            "START_WITH_REDUCED_CONTEXT": (
                "Provider requires reduced context, but this runtime uses its fixed configured context. "
                "Retry after resources are available or choose a smaller provider."
            ),
        }[decision.decision]
        detail = {"stage": "admission", "decision": payload}
        if message:
            detail["message"] = message
        raise HTTPException(
            status_code=503,
            detail=detail,
        )
    return payload


def live_gpu_visibility() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable and Path("/usr/lib/wsl/lib/nvidia-smi").is_file():
        executable = "/usr/lib/wsl/lib/nvidia-smi"
    if not executable:
        return {"available": False, "status": "tool_missing"}
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "status": "query_failed"}
    if result.returncode != 0:
        # WSL2 can expose the Windows GPU to the host while its guest-side
        # NVML initialization fails.  Treat only the verified, specific
        # WSL failure as adapter-unavailable; generic query failures remain
        # unknown and do not authorize the CPU fallback.
        try:
            release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").casefold()
        except OSError:
            release = ""
        wsl = "microsoft" in release or bool(os.environ.get("WSL_INTEROP"))
        diagnostic = (result.stdout + "\n" + result.stderr).casefold()
        known_wsl_nvml_failure = (
            "failed to initialize nvml" in diagnostic
            and "generic operating system error" in diagnostic
        )
        if wsl and known_wsl_nvml_failure:
            return {"available": False, "status": "wsl_gpu_unavailable"}
        return {"available": False, "status": "query_failed"}
    adapters = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not adapters:
        return {"available": False, "status": "no_adapters"}
    return {"available": True, "status": "available", "adapter_count": len(adapters)}


def cpu_fallback_policy() -> dict[str, Any]:
    return dict((registry().get("runtime_policy") or {}).get("cpu_chat_fallback") or {})


def cpu_chat_unsupported_reason(body: dict[str, Any] | None, policy: dict[str, Any]) -> str | None:
    """Fail explicitly when the bounded CPU profile cannot preserve request intent."""
    if not isinstance(body, dict):
        return "CPU fallback requires a text chat request."
    if body.get("tools") or body.get("tool_choice") not in (None, "none"):
        return "CPU fallback supports plain text chat without tools."
    if body.get("response_format") is not None:
        return "CPU fallback does not support structured output."
    try:
        if int(body.get("n", 1)) != 1:
            return "CPU fallback supports one completion per request."
    except (TypeError, ValueError):
        return "CPU fallback supports one completion per request."
    max_output = int(policy.get("max_output_tokens") or 512)
    for key in ("max_tokens", "max_completion_tokens"):
        if key in body:
            try:
                if int(body[key]) > max_output:
                    return f"CPU fallback caps output at {max_output} tokens; reduce the request limit."
            except (TypeError, ValueError):
                return "CPU fallback requires an integer output-token limit."
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return "CPU fallback requires text messages."
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant"}:
            return "CPU fallback supports system, user, and assistant text messages only."
        if not isinstance(message.get("content"), str):
            return "CPU fallback supports text-only message content; image and multipart inputs are unavailable."
    return None


def cpu_runtime_model(model: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    runtime_model = dict(model)
    provider_id = str(policy.get("provider_id") or "llama-cpp-general-cpu")
    provider = (registry().get("providers") or {}).get(provider_id) or {}
    endpoint = str(provider.get("endpoint") or "http://127.0.0.1:8089/v1")
    parsed_endpoint = urlsplit(endpoint)
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    try:
        endpoint_port = parsed_endpoint.port
    except ValueError:
        endpoint_port = None
    if policy.get("local_only") is not True or (
        parsed_endpoint.scheme != "http"
        or parsed_endpoint.hostname not in local_hosts
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or endpoint_port != int(provider.get("port") or 8089)
    ):
        raise HTTPException(
            status_code=503,
            detail={"stage": "cpu_fallback_config", "message": "CPU fallback must use the configured loopback-only local endpoint."},
        )
    runtime_model.update(
        {
            "_provider_id": provider_id,
            "_cpu_fallback": True,
            "service": str(provider.get("service") or "llm-general-cpu"),
            "profile": str(provider.get("profile") or "cpu-chat"),
            "port": int(provider.get("port") or 8089),
            "base_url": endpoint,
            "backend_model": "ai-station-general-cpu",
            "heavy": False,
            "supports_vision": False,
            "supports_tools": False,
            "supports_json_schema": False,
        }
    )
    return runtime_model


async def runtime_endpoint_ready(model: dict[str, Any]) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{model['base_url']}/models")
        if response.status_code != 200:
            return False
        if not model.get("_cpu_fallback"):
            return True
        payload = response.json()
        expected = str(model.get("backend_model") or "")
        listed = {
            str(item.get("id"))
            for item in (payload.get("data") or [])
            if isinstance(item, dict)
        }
        return bool(expected and expected in listed)
    except Exception:
        return False


async def start_runtime(
    model: dict[str, Any], request_body: dict[str, Any] | None = None
) -> dict[str, Any]:
    global ACTIVE_MODEL_ID, ACTIVE_RUNTIME_MODE

    service = model.get("service")
    if not service:
        raise HTTPException(status_code=400, detail=f"Model has no runtime service: {model['id']}")

    try:
        async with LifecycleLock(f"gateway-start:{service}"):
            emit_contract_telemetry("lifecycle_transition", state="requested", service=service)
            # Repair a marker left by a failed start or a dead Gateway before
            # admission.  This is observation-only and remains under the
            # shared lock with the subsequent Compose transition.
            observed_active = await reconcile_active_profile()
            if model.get("heavy") and observed_active is None:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "stage": "lifecycle_reconcile",
                        "message": "Unable to observe Docker runtime safely; retry without stopping workloads.",
                    },
                )
            cpu_reused = False
            policy = cpu_fallback_policy()
            if model.get("id") == str(policy.get("model_id") or "general-qwen38-27b"):
                gpu_visibility = live_gpu_visibility()
                if gpu_visibility.get("status") in {"no_adapters", "wsl_gpu_unavailable"} and policy.get("enabled") is True:
                    if observed_active is None:
                        raise HTTPException(
                            status_code=503,
                            detail={
                                "stage": "cpu_fallback_observation",
                                "message": "Cannot verify active workloads safely; CPU fallback was not started.",
                            },
                        )
                    # Keep a still-serving general runtime; a failed NVIDIA
                    # utility probe alone is not reason to replace it.
                    if await runtime_endpoint_ready(model):
                        admission = {
                            "decision": "REUSE_HEALTHY_RUNTIME",
                            "runtime_mode": "existing_runtime",
                            "gpu_visibility": gpu_visibility["status"],
                        }
                        ACTIVE_MODEL_ID = public_model_id(model)
                        ACTIVE_RUNTIME_MODE = "existing_runtime"
                        return admission

                    unsupported = cpu_chat_unsupported_reason(request_body, policy)
                    if unsupported:
                        raise HTTPException(
                            status_code=400,
                            detail={"stage": "cpu_fallback_request", "message": unsupported},
                        )
                    model.update(cpu_runtime_model(model, policy))
                    service = str(model.get("service") or service)
                    if isinstance(request_body, dict):
                        request_body["model"] = model["backend_model"]
                    cpu_reused = await runtime_endpoint_ready(model)
                    if cpu_reused:
                        admission = {
                            "decision": "REUSE_READY_CPU_RUNTIME",
                            "provider_id": model["_provider_id"],
                            "runtime_mode": "cpu_fallback",
                            "degraded": True,
                            "gpu_visibility": gpu_visibility["status"],
                            "max_context_tokens": int(policy.get("max_context_tokens") or 2048),
                        }
                        ACTIVE_MODEL_ID = public_model_id(model)
                        ACTIVE_RUNTIME_MODE = "cpu_fallback"
                        return admission
                    admission = evaluate_admission(model, observed_active)
                    admission.update(
                        {
                            "runtime_mode": "cpu_fallback",
                            "degraded": True,
                            "gpu_visibility": gpu_visibility["status"],
                            "max_context_tokens": int(policy.get("max_context_tokens") or 2048),
                        }
                    )
                else:
                    admission = evaluate_admission(model, observed_active)
                    admission["runtime_mode"] = "gpu"
            else:
                admission = evaluate_admission(model, observed_active)

            if any("tensor-parallel" in str(reason).casefold() for reason in admission.get("reasons", [])):
                raise HTTPException(
                    status_code=503,
                    detail={"stage": "admission", "message": "Tensor-parallel placement is unsupported and cannot launch on one GPU."},
                )

            target_was_running = cpu_reused
            if model.get("heavy"):
                await assert_media_idle(admission, registry().get("providers", {}))
                if (
                    "stop_providers" in admission
                    and observed_active
                    and not await verify_active_gpu_placements(
                        service,
                        observed_active,
                        admission.get("stop_providers") or [],
                    )
                ):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "stage": "gpu_placement",
                            "message": "Cannot verify active GPU placement; refusing concurrent heavy launch.",
                        },
                    )
                target_was_running = False
                try:
                    target_provider = provider_for_catalog_model(model)
                    owners = preferred_provider_by_service((registry().get("providers") or {}).values())
                    observed_services = {
                        str(provider.get("service"))
                        for provider in owners.values()
                        if str(provider.get("id")) in (observed_active or [])
                    }
                    target_was_running = str(target_provider.get("service") or service) in observed_services
                except KeyError:
                    pass
                # Admission already resolved GPU placement.  Stop only the
                # providers it identified as conflicts; an empty list is a
                # valid multi-GPU START decision and must not stop a distinct
                # GPU owner.  Keep the legacy fallback for mocked/older
                # admission payloads that omit stop_providers.
                stop_provider_ids = (
                    admission["stop_providers"]
                    if "stop_providers" in admission
                    else None
                )
                await stop_other_heavy(service, observed_active, stop_provider_ids)
                # The previous owner was deliberately stopped.  Do not leave
                # its marker visible while the replacement is warming up.
                previous = read_active_profile()
                target_profile = str(model.get("profile") or "")
                if previous and previous != target_profile:
                    clear_active_profile(previous)

            emit_contract_telemetry("lifecycle_transition", state="starting", service=service)
            try:
                try:
                    gpu_index = int(admission.get("gpu_index", 0))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=503, detail={"stage": "admission", "message": "Invalid GPU placement decision."})
                if gpu_index < 0:
                    raise HTTPException(status_code=503, detail={"stage": "admission", "message": "Negative GPU placement is invalid."})
                compose_kwargs: dict[str, Any] = {"timeout": 300}
                if "gpu_index" in admission and model.get("heavy"):
                    compose_kwargs["env_overrides"] = {"AI_STATION_GPU_DEVICE_ID": str(gpu_index)}
                result = await compose(
                    [*profile_args_for_services([service]), "up", "-d", service],
                    **compose_kwargs,
                )
                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "stage": "start_runtime",
                            "model": model["id"],
                            "service": service,
                            "stdout": result.stdout[-4000:],
                            "stderr": result.stderr[-4000:],
                            "admission": admission,
                        },
                    )

                emit_contract_telemetry("lifecycle_transition", state="probing", service=service)
                await wait_ready(model)
            except BaseException:
                if (model.get("heavy") or model.get("_cpu_fallback")) and not target_was_running:
                    await rollback_started_target(service)
                raise

            if model.get("heavy"):
                ACTIVE_MODEL_ID = public_model_id(model)
                ACTIVE_RUNTIME_MODE = "gpu"
                profile = str(model.get("profile") or "")
                if profile:
                    # Publication is the final transition: the runtime is
                    # reachable and all preceding lifecycle work succeeded.
                    publish_active_profile(profile)
                    emit_contract_telemetry("lifecycle_transition", state="ready", profile=profile)
            elif model.get("_cpu_fallback"):
                ACTIVE_MODEL_ID = public_model_id(model)
                ACTIVE_RUNTIME_MODE = "cpu_fallback"

            return admission
    except HTTPException:
        # Marker mutation is intentionally confined to the lock body.  A
        # rejected or failed same-profile start therefore preserves a valid
        # prior marker; replacement starts clear the old marker only after the
        # confirmed stop while still holding the lock.
        emit_contract_telemetry("lifecycle_transition", state="failed", service=service)
        raise
    except LifecycleBusy as exc:
        raise HTTPException(status_code=503, detail={"stage": "lifecycle_lock", "message": str(exc)}) from exc

# Compatibility aliases: the public gateway module historically exposed these
# helpers and tests/clients import them directly.  Keep that source contract
# while routing all endpoint calls through the extracted pure boundary.
merge_system_prefix = openai_translation.merge_system_prefix
rewrite_messages = openai_translation.rewrite_messages
responses_content_to_chat = openai_translation.responses_content_to_chat
responses_input_to_messages = openai_translation.responses_input_to_messages
responses_tools_to_chat = openai_translation.responses_tools_to_chat
responses_to_chat_body = openai_translation.responses_to_chat_body
chat_to_responses = openai_translation.chat_to_responses
content_is_empty = openai_translation.content_is_empty
flatten_reasoning_into_content = openai_translation.flatten_reasoning_into_content
flatten_sse_line = openai_translation.flatten_sse_line
iter_flattened_sse = openai_translation.iter_flattened_sse


@app.get("/health")
async def health() -> dict[str, Any]:
    active_model_id = ACTIVE_MODEL_ID
    active_runtime_mode = ACTIVE_RUNTIME_MODE
    if active_runtime_mode == "cpu_fallback":
        # CPU fallback is non-heavy and is intentionally not published as a
        # GPU profile marker.  Recheck its bounded loopback model endpoint so
        # health never advertises a stale CPU model after the service stops.
        try:
            policy = cpu_fallback_policy()
            if policy.get("enabled") is not True:
                raise HTTPException(status_code=503, detail="CPU fallback is disabled")
            model = get_model(str(policy.get("model_id") or "general-qwen38-27b"))
            if active_model_id != public_model_id(model):
                raise HTTPException(status_code=503, detail="CPU fallback model does not match active state")
            runtime_model = cpu_runtime_model(model, policy)
            if not await runtime_endpoint_ready(runtime_model):
                raise HTTPException(status_code=503, detail="CPU fallback model endpoint is not ready")
            active_model_id = public_model_id(model)
        except (HTTPException, KeyError, ValueError):
            active_model_id = None
            active_runtime_mode = None
    return {
        "ok": True,
        "version": GATEWAY_VERSION,
        "active_model_id": active_model_id,
        "active_runtime_mode": active_runtime_mode,
        "queue_length": len(QUEUE),
        "catalog_path": str(CATALOG_PATH),
        "providers": list((registry().get("providers") or {}).keys()),
        "models": valid_public_model_ids(),
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": public_model_id(m),
                "name": m.get("display_name"),
                "object": "model",
                "created": 0,
                "owned_by": "ai-station",
                "root": public_model_id(m),
                "canonical_id": public_model_id(m),
                "parent": None,
                "permission": [],
            }
            for m in selectable_models()
        ],
    }


@app.get("/queue")
async def queue() -> dict[str, Any]:
    return {
        "active_model_id": ACTIVE_MODEL_ID,
        "queue_length": len(QUEUE),
        "queue": QUEUE,
    }


@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    return {
        "admission": registry().get("admission") or {},
        "providers": registry().get("providers") or {},
    }


@app.post("/v1/admission/dry-run")
async def admission_dry_run(request: Request) -> dict[str, Any]:
    body = await request.json()
    provider_id = body.get("provider_id") or body.get("model")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id or model required")
    context = body.get("context")
    decision = admit(str(provider_id), context=context)
    return decision.to_dict()


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(request: Request) -> dict[str, Any]:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio request exceeds 25 MiB")
        body.extend(chunk)
    try:
        audio, language, upstream_model = extract_audio_request(
            bytes(body),
            content_type=request.headers.get("content-type"),
            language=request.query_params.get("language"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    want_timestamps = request.query_params.get("timestamps") in {"1", "true", "yes"}
    result = await asyncio.to_thread(
        transcribe_station_audio,
        audio,
        language=language,
        want_timestamps=want_timestamps,
        whisper_primary=upstream_model == CALL_ASR_UPSTREAM_MODEL,
    )
    payload: dict[str, Any] = {
        "text": result.text,
        "engine": result.engine,
        "fallback_used": result.fallback_used,
    }
    if result.language:
        payload["language"] = result.language
    if result.timestamps:
        payload["segments"] = result.timestamps
    return payload


@app.post("/v1/audio/speech")
async def audio_speech() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "tts_pending_smoke",
            "status": "pending_smoke",
            "message": (
                "No loopback speech synthesizer yet. Return text from "
                "chat completions. Do not start a second heavy GPU TTS "
                "engine beside chat."
            ),
            "asr": "http://127.0.0.1:8888/v1/audio/transcriptions",
        },
    )


async def cancel_on_disconnect(
    request: Request, work: Coroutine[Any, Any, JSONResponse]
) -> Response:
    async def wait_for_disconnect() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass

    # The request body has been consumed. Watch ASGI receive independently of
    # the model lock and the upstream socket, which may both wait indefinitely.
    disconnect = asyncio.create_task(wait_for_disconnect())
    pending_response = asyncio.create_task(work)
    try:
        await asyncio.wait(
            (disconnect, pending_response), return_when=asyncio.FIRST_COMPLETED
        )
        if pending_response.done():
            return pending_response.result()
        disconnect.result()
        return Response(status_code=499)
    finally:
        for task in (disconnect, pending_response):
            if not task.done():
                task.cancel()
        await asyncio.gather(disconnect, pending_response, return_exceptions=True)


@app.post("/v1/chat/completions")
async def chat(request: Request):
    raw_body = await request.json()
    requested = raw_body.get("model")
    if not requested:
        raise HTTPException(status_code=400, detail="Missing model")

    model = dict(get_model(requested))
    body = rewrite_messages(model, raw_body)

    request_id = str(uuid.uuid4())
    item = {
        "id": request_id,
        "model": public_model_id(model),
        "state": "queued",
        "created_at": time.time(),
    }
    QUEUE.append(item)

    if bool(raw_body.get("stream", False)):
        return StreamingResponse(
            stream_proxy(request, model, body, item, requested),
            media_type="text/event-stream",
        )

    async def complete() -> JSONResponse:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model, body)
            item["state"] = "running"
            item["admission"] = admission

            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=body,
                )
                try:
                    content = response.json()
                except Exception:
                    content = {"error": response.text}
                if isinstance(content, dict):
                    flatten_reasoning_into_content(content)
                emit_contract_telemetry(
                    "chat_completion",
                    model=requested,
                    stream=False,
                    messages=len(raw_body.get("messages") or []),
                    tools=len(raw_body.get("tools") or []),
                    **response_shape(content),
                )
                return JSONResponse(content=content, status_code=response.status_code)

    try:
        return await cancel_on_disconnect(request, complete())
    finally:
        if item in QUEUE:
            QUEUE.remove(item)


async def stream_proxy(
    request: Request,
    model: dict[str, Any],
    body: dict[str, Any],
    item: dict[str, Any],
    requested_model: str,
) -> AsyncIterator[bytes]:
    content_chars = 0
    tool_call_events = 0
    finish_reason: str | None = None
    upstream_status: int | None = None
    upstream_content_type: str | None = None
    upstream_error_type: str | None = None
    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            yield b": AI Station is preparing the selected local model\n\n"
            admission = await start_runtime(model, body)
            item["state"] = "running"
            item["admission"] = admission

            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{model['base_url']}/chat/completions",
                    json=body,
                ) as response:
                    upstream_status = response.status_code
                    upstream_content_type = response.headers.get("content-type")
                    if response.status_code >= 400:
                        error_bytes = await response.aread()
                        client_error, upstream_error_type = safe_upstream_error(
                            error_bytes, response.status_code
                        )
                        error_event = json.dumps(
                            {
                                "error": {
                                    "message": client_error,
                                    "type": "upstream_model_error",
                                }
                            }
                        )
                        yield f"data: {error_event}\n\ndata: [DONE]\n\n".encode()
                        return
                    async for chunk in iter_flattened_sse(
                        response.aiter_bytes(), flatten_reasoning=False
                    ):
                        if await request.is_disconnected():
                            break
                        raw = chunk.strip()
                        if raw.startswith(b"data:") and raw[5:].strip() not in {
                            b"",
                            b"[DONE]",
                        }:
                            try:
                                event = json.loads(raw[5:].strip())
                                choice = (event.get("choices") or [{}])[0]
                                delta = choice.get("delta") or {}
                                text = delta.get("content")
                                if isinstance(text, str):
                                    content_chars += len(text)
                                tool_call_events += len(delta.get("tool_calls") or [])
                                if choice.get("finish_reason") is not None:
                                    finish_reason = str(choice["finish_reason"])
                            except (AttributeError, json.JSONDecodeError):
                                pass
                        yield chunk
    except Exception as exc:
        payload = json.dumps(
            {
                "error": {
                    "message": str(exc),
                    "type": "ai_station_gateway_error",
                }
            },
            ensure_ascii=False,
        )
        yield f"data: {payload}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"
    finally:
        emit_contract_telemetry(
            "chat_completion",
            model=requested_model,
            stream=True,
            messages=len(body.get("messages") or []),
            tools=len(body.get("tools") or []),
            content_chars=content_chars,
            tool_call_events=tool_call_events,
            finish_reason=finish_reason,
            upstream_status=upstream_status,
            upstream_content_type=upstream_content_type,
            upstream_error_type=upstream_error_type,
            request_keys=sorted(body),
            tool_choice_type=type(body.get("tool_choice")).__name__,
            message_roles=[
                message.get("role")
                for message in body.get("messages") or []
                if isinstance(message, dict)
            ],
        )
        if item in QUEUE:
            QUEUE.remove(item)


def responses_sse_event(event_type: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    ).encode("utf-8")


async def responses_stream_proxy(
    request: Request,
    model: dict[str, Any],
    chat_body: dict[str, Any],
    item: dict[str, Any],
    requested_model: str,
) -> AsyncIterator[bytes]:
    response_id = f"resp_{uuid.uuid4().hex}"
    sequence = 0
    created = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "in_progress",
        "model": requested_model,
        "output": [],
    }
    yield responses_sse_event(
        "response.created",
        {"type": "response.created", "response": created, "sequence_number": sequence},
    )
    sequence += 1
    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model, chat_body)
            item["state"] = "running"
            item["admission"] = admission
            async with httpx.AsyncClient(timeout=None) as client:
                upstream = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=chat_body,
                )
                payload = upstream.json()
                if upstream.status_code >= 400:
                    raise RuntimeError(str(payload)[:600])
                flatten_reasoning_into_content(payload)
                completed = chat_to_responses(payload, requested_model, response_id)

        for output_index, output_item in enumerate(completed["output"]):
            if await request.is_disconnected():
                return
            in_progress = dict(output_item)
            in_progress["status"] = "in_progress"
            yield responses_sse_event(
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": output_index,
                    "item": in_progress,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            if output_item["type"] == "message":
                part = output_item["content"][0]
                yield responses_sse_event(
                    "response.content_part.added",
                    {
                        "type": "response.content_part.added",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "delta": part["text"],
                        "logprobs": [],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.output_text.done",
                    {
                        "type": "response.output_text.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "text": part["text"],
                        "logprobs": [],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.content_part.done",
                    {
                        "type": "response.content_part.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "part": part,
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
            elif output_item["type"] == "function_call":
                yield responses_sse_event(
                    "response.function_call_arguments.delta",
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "delta": output_item["arguments"],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.function_call_arguments.done",
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "name": output_item["name"],
                        "arguments": output_item["arguments"],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
            yield responses_sse_event(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": output_item,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
        yield responses_sse_event(
            "response.completed",
            {
                "type": "response.completed",
                "response": completed,
                "sequence_number": sequence,
            },
        )
    except Exception as exc:
        failed = dict(created)
        failed["status"] = "failed"
        failed["error"] = {
            "code": "ai_station_gateway_error",
            "message": str(exc),
        }
        yield responses_sse_event(
            "response.failed",
            {
                "type": "response.failed",
                "response": failed,
                "sequence_number": sequence,
            },
        )
    finally:
        if item in QUEUE:
            QUEUE.remove(item)


@app.post("/v1/responses")
async def responses(request: Request):
    raw_body = await request.json()
    requested = raw_body.get("model")
    if not requested:
        raise HTTPException(status_code=400, detail="Missing model")

    model = dict(get_model(str(requested)))
    chat_body = rewrite_messages(model, responses_to_chat_body(raw_body))
    item = {
        "id": str(uuid.uuid4()),
        "model": public_model_id(model),
        "endpoint": "responses",
        "state": "queued",
        "created_at": time.time(),
    }
    QUEUE.append(item)

    if bool(raw_body.get("stream", False)):
        return StreamingResponse(
            responses_stream_proxy(request, model, chat_body, item, str(requested)),
            media_type="text/event-stream",
        )

    async def complete() -> JSONResponse:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model, chat_body)
            item["state"] = "running"
            item["admission"] = admission
            async with httpx.AsyncClient(timeout=None) as client:
                upstream = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=chat_body,
                )
                try:
                    payload = upstream.json()
                except Exception:
                    payload = {"error": upstream.text}
                if upstream.status_code >= 400 or not isinstance(payload, dict):
                    return JSONResponse(content=payload, status_code=upstream.status_code)
                flatten_reasoning_into_content(payload)
                converted = chat_to_responses(payload, str(requested))
                return JSONResponse(content=converted, status_code=upstream.status_code)

    try:
        return await cancel_on_disconnect(request, complete())
    finally:
        if item in QUEUE:
            QUEUE.remove(item)
