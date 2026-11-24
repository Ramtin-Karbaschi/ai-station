#!/usr/bin/env python3
"""Offline model/provider contract matrix validator."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

COMPOSE_FILES = (
    "compose.yml", "compose.models.yml", "compose.comfyui.experimental.yaml",
    "compose.hardening.yaml", "compose.local-builds.yaml", "compose.images.lock.yaml",
)


@dataclass(frozen=True)
class ContractRow:
    catalog_id: str
    public_model_id: str
    alias: str
    profile: str
    provider: str | None
    service: str
    port: int | None
    health_endpoint: str | None
    capabilities: tuple[str, ...]
    manifest_id: str | None
    physical_model: str | None
    mmproj: str | None
    logical_backend: str | None
    source_aliases: tuple[str, ...]


def _read(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text) or {}


def load_sources(root: Path) -> dict[str, Any]:
    return {
        "catalog": _read(root / "config/model-catalog.json"),
        "registry": _read(root / "config/registry/models.yaml"),
        "manifest": _read(root / "config/model-manifest.json"),
        "providers": _read(root / "config/providers.yaml"),
        "litellm": _read(root / "config/gateway/litellm.yaml"),
        "compose": [_read(root / name) for name in COMPOSE_FILES if (root / name).is_file()],
    }


def _services(documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = {}
    for document in documents:
        for name, service in (document.get("services") or {}).items():
            services.setdefault(name, {}).update(service or {})
    return services


def _command(service: dict[str, Any]) -> list[str]:
    value = service.get("command") or []
    return value.split() if isinstance(value, str) else [str(item) for item in value]


def _flag(service: dict[str, Any], flag: str) -> str | None:
    command = _command(service)
    try:
        return command[command.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _internal_port(service: dict[str, Any]) -> int | None:
    ports = service.get("ports") or []
    if not ports:
        return None
    value = ports[0]
    if isinstance(value, dict):
        value = value.get("target")
    else:
        value = str(value).rsplit(":", 1)[-1]
    digits = "".join(char for char in str(value) if char.isdigit())
    return int(digits) if digits else None


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def build_matrix(sources: dict[str, Any]) -> list[ContractRow]:
    catalog = sources["catalog"].get("models") or []
    registry = sources["registry"].get("models") or {}
    providers = sources["providers"].get("providers") or {}
    services = _services(sources["compose"])
    rows: list[ContractRow] = []
    for item in catalog:
        catalog_id = str(item["id"])
        public_id = str(item.get("public_model_id") or item.get("display_name") or catalog_id)
        registered = next((value for value in registry.values() if value.get("catalog_id") == catalog_id), None)
        provider_name, provider = next(
            ((name, value) for name, value in providers.items() if catalog_id in (value.get("catalog_ids") or [])),
            (None, None),
        )
        service_name = str(item.get("service") or (provider or {}).get("service") or (registered or {}).get("service") or "")
        compose = services.get(service_name, {})
        aliases = [str(item.get("alias") or ""), str((registered or {}).get("alias") or "")]
        aliases.extend(str(value) for value in (provider or {}).get("model_aliases", []))
        aliases.extend((str(item.get("backend_model") or ""), _flag(compose, "--alias") or ""))
        capabilities = ["chat"] if item.get("kind") in {"chat", "vision"} else [str(item.get("kind"))]
        for field, capability in (("supports_tools", "tools"), ("supports_vision", "vision"), ("supports_json_schema", "json_schema")):
            if item.get(field):
                capabilities.append(capability)
        rows.append(ContractRow(
            catalog_id, public_id, str(item.get("alias") or ""), str(item.get("profile") or ""),
            provider_name, service_name, item.get("port") or (provider or {}).get("port") or _internal_port(compose),
            (provider or {}).get("health_endpoint"), _unique(capabilities), item.get("manifest_id"),
            (registered or {}).get("file"), item.get("mmproj_manifest_id") and (registered or {}).get("mmproj"),
            item.get("backend_model"), _unique(aliases),
        ))
    return rows


def _duplicates(values: list[str | None], label: str) -> list[str]:
    duplicates = sorted({value for value in values if value and values.count(value) > 1})
    return [f"{label}: duplicate {value}" for value in duplicates]


def validate(sources: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    catalog = sources["catalog"].get("models") or []
    registry = sources["registry"].get("models") or {}
    providers = sources["providers"].get("providers") or {}
    routes = sources["litellm"].get("model_list") or []
    services = _services(sources["compose"])
    manifest_ids = {str(item.get("id")) for item in sources["manifest"].get("models") or []}
    errors += _duplicates([item.get("id") for item in catalog], "catalog")
    errors += _duplicates([item.get("public_model_id") for item in catalog], "catalog")
    errors += _duplicates([item.get("catalog_id") for item in registry.values()], "registry catalog_id")
    errors += _duplicates([item.get("model_name") for item in routes], "LiteLLM model_name")
    owners: dict[str, str] = {}
    for provider_name, provider in providers.items():
        for catalog_id in provider.get("catalog_ids") or []:
            if catalog_id in owners:
                errors.append(f"providers: catalog_id owned by {owners[catalog_id]} and {provider_name}")
            owners[catalog_id] = provider_name
    route_by_name = {route.get("model_name"): route for route in routes}
    catalog_by_id = {item.get("id"): item for item in catalog}
    for row in build_matrix(sources):
        item = catalog_by_id[row.catalog_id]
        registered = next((value for value in registry.values() if value.get("catalog_id") == row.catalog_id), None)
        provider = providers.get(row.provider or "") or {}
        compose = services.get(row.service, {})
        route = route_by_name.get(row.public_model_id)
        if not route:
            errors.append(f"{row.catalog_id}: missing LiteLLM route {row.public_model_id}")
        if not row.provider:
            errors.append(f"{row.catalog_id}: missing provider catalog link")
        if row.service not in services:
            errors.append(f"{row.catalog_id}: missing Compose service {row.service}")
        if row.port is None:
            errors.append(f"{row.catalog_id}: missing runtime port")
        for source_name, source in (("registry", registered), ("provider", provider)):
            if source and source.get("service") and source["service"] != row.service:
                errors.append(f"{row.catalog_id}: {source_name} service contradicts catalog")
            if source and source.get("profile") and source["profile"] != row.profile:
                errors.append(f"{row.catalog_id}: {source_name} profile contradicts catalog")
            if source and source.get("port") and int(source["port"]) != row.port:
                errors.append(f"{row.catalog_id}: {source_name} port contradicts catalog")
        if compose:
            if _flag(compose, "--alias") != row.logical_backend:
                errors.append(f"{row.catalog_id}: Compose --alias contradicts backend_model")
            command_port = _flag(compose, "--port")
            if command_port and int(command_port) != row.port:
                errors.append(f"{row.catalog_id}: Compose --port contradicts catalog")
            if _internal_port(compose) and _internal_port(compose) != row.port:
                errors.append(f"{row.catalog_id}: Compose target port contradicts catalog")
        if row.manifest_id and row.manifest_id not in manifest_ids:
            errors.append(f"{row.catalog_id}: manifest_id absent from model-manifest")
        if row.physical_model is None:
            errors.append(f"{row.catalog_id}: registry has no physical model file")
        if "vision" in row.capabilities and not row.mmproj:
            errors.append(f"{row.catalog_id}: vision route missing physical mmproj")
        if route:
            mode = (route.get("model_info") or {}).get("mode")
            expected_mode = "embedding" if item.get("kind") == "embedding" else "rerank" if item.get("kind") == "reranker" else "chat"
            if mode != expected_mode:
                errors.append(f"{row.catalog_id}: LiteLLM mode {mode!r} != {expected_mode!r}")
            params = route.get("litellm_params") or {}
            target = str(params.get("model") or "")
            if expected_mode == "chat" and row.public_model_id not in target:
                errors.append(f"{row.catalog_id}: LiteLLM target does not name public model")
            if expected_mode == "embedding" and "embedder:8090" not in str(params.get("api_base")):
                errors.append(f"{row.catalog_id}: embedding route is not direct embedder")
            if expected_mode == "rerank" and "reranker:8091" not in str(params.get("api_base")):
                errors.append(f"{row.catalog_id}: reranker route is not direct reranker")
    return errors


def compatibility_projections(sources: dict[str, Any]) -> list[dict[str, str]]:
    """Report registry-only compatibility profiles without treating them as catalog rows."""
    catalog_ids = {item.get("id") for item in sources["catalog"].get("models") or []}
    projections = []
    for alias, item in (sources["registry"].get("models") or {}).items():
        if item.get("catalog_id") not in catalog_ids and item.get("status") == "compatibility":
            projections.append({"alias": str(alias), "catalog_id": str(item.get("catalog_id")), "status": "compatibility-only"})
    return sorted(projections, key=lambda item: item["alias"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    sources = load_sources(args.root)
    errors = validate(sources)
    payload = {
        "rows": [asdict(row) for row in build_matrix(sources)],
        "compatibility_projections": compatibility_projections(sources),
        "errors": errors,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Model/provider contract matrix: {len(payload['rows'])} rows")
        for error in errors:
            print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
