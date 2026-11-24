from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urljoin

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request

from apps.tool_gateway.app.contracts import (
    AssetImportRequest,
    CapabilitiesResponse,
    EntityCandidate,
    EntityResolveRequest,
    EntityResolveResponse,
    FetchRequest,
    FetchResponse,
    ImportedAsset,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from apps.tool_gateway.app.extract import extract_readable_html
from apps.tool_gateway.app.security import UnsafeUrlError, validate_external_url

VERSION = "0.1.0"
SEARXNG_URL = os.getenv("AI_STATION_SEARXNG_URL", "http://127.0.0.1:8889").rstrip("/")
ASSET_ROOT = Path(os.getenv("AI_STATION_TOOL_ASSET_ROOT", "/srv/ai-station/data/grounding/assets"))
QWEN_EDIT_WORKFLOW = Path("/opt/ai-station/config/clients/comfyui/workflows/qwen-image-edit-2511.json")
QWEN_EDIT_MODEL = Path(
    "/srv/ai-station/models/comfyui/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors"
)
STUDIO_CAPABILITIES = Path("/opt/ai-station/config/studio/capabilities.yaml")
USER_AGENT = os.getenv(
    "AI_STATION_TOOL_USER_AGENT",
    "AIStationGrounding/0.1 (+https://www.mediawiki.org/wiki/API:Etiquette)",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(20, connect=8),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html,image/*;q=0.8"},
        follow_redirects=False,
    )
    yield
    await app.state.http.aclose()


app = FastAPI(title="AI Station Tool Gateway", version=VERSION, lifespan=lifespan)


def _client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _plain(value: object, limit: int = 2_000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _verified_asset_media_type(raw: bytes, declared: str) -> str:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"%PDF-", "application/pdf"),
    )
    for signature, media_type in signatures:
        if raw.startswith(signature):
            return media_type
    if len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(status_code=415, detail=f"asset signature does not match a supported type ({declared})")


async def _external_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    accept: str,
) -> tuple[httpx.Response, bytes, bool]:
    current = url
    for _ in range(6):
        try:
            await validate_external_url(current)
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        async with client.stream("GET", current, headers={"Accept": accept}) as response:
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    raise HTTPException(status_code=502, detail="redirect has no location")
                current = urljoin(str(response.url), location)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HTTPException(status_code=502, detail=f"upstream HTTP {response.status_code}") from exc
            chunks: list[bytes] = []
            size = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    remaining = max_bytes - (size - len(chunk))
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                    truncated = True
                    break
                chunks.append(chunk)
            return response, b"".join(chunks), truncated
    raise HTTPException(status_code=400, detail="too many redirects")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ai-station-tool-gateway", "version": VERSION}


@app.get("/v1/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    image_edit_ready = QWEN_EDIT_WORKFLOW.is_file() and QWEN_EDIT_MODEL.is_file()
    image_edit_status = "unavailable"
    if image_edit_ready and STUDIO_CAPABILITIES.is_file():
        try:
            configured = yaml.safe_load(STUDIO_CAPABILITIES.read_text(encoding="utf-8")) or {}
            image_edit_status = str(
                ((configured.get("capabilities") or {}).get("image.edit") or {}).get("status")
                or "configured_pending_smoke"
            )
        except (OSError, ValueError, TypeError):
            image_edit_status = "invalid"
    return CapabilitiesResponse(
        version=VERSION,
        tools=["search", "fetch", "entity.resolve", "asset.import"],
        constraints={
            "paid_api_required": False,
            "external_fetch_ssrf_protected": True,
            "browser_javascript": False,
            "search_backend": "local-searxng",
            "asset_max_bytes": 25_000_000,
        },
        capabilities={
            "image.edit": {
                "installed": image_edit_ready,
                "status": image_edit_status,
                "provider": "comfyui-media-experimental",
            }
        },
    )


@app.post("/v1/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    try:
        response = await _client(request).get(
            f"{SEARXNG_URL}/search",
            params={
                "q": payload.query,
                "format": "json",
                "categories": payload.category,
                "language": payload.language,
                "safesearch": 1,
            },
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="local SearXNG is unavailable") from exc
    results: list[SearchResult] = []
    for item in body.get("results", []):
        if len(results) >= payload.limit:
            break
        try:
            results.append(
                SearchResult(
                    title=_plain(item.get("title"), 500),
                    url=item["url"],
                    snippet=_plain(item.get("content")),
                    engine=_plain(item.get("engine"), 80) or None,
                    thumbnail_url=item.get("thumbnail_src") or item.get("img_src"),
                )
            )
        except (KeyError, ValueError):
            continue
    return SearchResponse(query=payload.query, results=results)


@app.post("/v1/fetch", response_model=FetchResponse)
async def fetch(payload: FetchRequest, request: Request) -> FetchResponse:
    response, raw, truncated = await _external_get(
        _client(request), str(payload.url), max_bytes=payload.max_bytes, accept="text/html,text/plain"
    )
    media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
    if media_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
        raise HTTPException(status_code=415, detail=f"unsupported fetch media type: {media_type}")
    if media_type in {"text/html", "application/xhtml+xml"}:
        title, text = extract_readable_html(raw, response.encoding or "utf-8")
    else:
        title, text = "", raw.decode(response.encoding or "utf-8", errors="replace")
    return FetchResponse(
        final_url=str(response.url), media_type=media_type, title=title, text=text, truncated=truncated
    )


def _entity_score(query: str, label: str, description: str, kind: str) -> float:
    def _key(value: str) -> str:
        return " ".join(re.findall(r"[^\W_]+", value.casefold()))

    query_key = _key(query)
    label_key = _key(label)
    generic_tails = {"bridge", "landmark", "monument", "vehicle", "car", "brand", "company"}
    stripped_query = " ".join(token for token in query_key.split() if token not in generic_tails)
    lexical = max(
        SequenceMatcher(None, query_key, label_key).ratio(),
        SequenceMatcher(None, stripped_query, label_key).ratio() if stripped_query else 0,
    )
    if query_key == label_key:
        lexical = 1.0
    kind_terms = {
        "vehicle": ("car", "automobile", "vehicle", "\u062e\u0648\u062f\u0631\u0648", "\u0645\u0627\u0634\u06cc\u0646"),
        "brand": ("brand", "company", "manufacturer", "automaker", "\u0628\u0631\u0646\u062f", "\u0634\u0631\u06a9\u062a", "\u062e\u0648\u062f\u0631\u0648\u0633\u0627\u0632"),
        "organization": ("organization", "company", "manufacturer", "automaker", "\u0634\u0631\u06a9\u062a", "\u0633\u0627\u0632\u0645\u0627\u0646"),
        "place": (
            "bridge", "landmark", "monument", "building", "place", "heritage",
            "city", "capital", "province", "village", "iran",
            "\u067e\u0644", "\u0628\u0646\u0627", "\u0645\u06a9\u0627\u0646", "\u0634\u0647\u0631", "\u0645\u0631\u06a9\u0632", "\u0627\u0633\u062a\u0627\u0646", "\u0631\u0648\u0633\u062a\u0627", "\u0627\u06cc\u0631\u0627\u0646",
        ),
    }.get(kind, ())
    context = f"{label} {description}".casefold()
    kind_match = bool(kind_terms and any(term in context for term in kind_terms))
    kind_bonus = 0.08 if kind_match else (-0.08 if kind_terms else 0.0)
    return min(1.0, round(lexical * 0.92 + kind_bonus, 4))


@app.post("/v1/entities/resolve", response_model=EntityResolveResponse)
async def resolve_entity(payload: EntityResolveRequest, request: Request) -> EntityResolveResponse:
    language = "fa" if payload.language.lower().startswith("fa") else "en"
    try:
        response = await _client(request).get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": payload.name,
                "language": language,
                "uselang": language,
                "format": "json",
                "limit": payload.limit,
                "type": "item",
            },
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Wikidata is unavailable") from exc
    candidates = sorted(
        [
            EntityCandidate(
                entity_id=str(item["id"]),
                label=_plain(item.get("label"), 300),
                description=_plain(item.get("description"), 1_000),
                url=item.get("concepturi") or f"https://www.wikidata.org/wiki/{item['id']}",
                score=_entity_score(payload.name, str(item.get("label", "")), str(item.get("description", "")), payload.kind),
            )
            for item in body.get("search", [])
            if item.get("id") and item.get("label")
        ],
        key=lambda item: item.score,
        reverse=True,
    )
    top = candidates[0] if candidates else None
    margin = top.score - candidates[1].score if top and len(candidates) > 1 else (top.score if top else 0)
    accepted = top if top and top.score >= 0.86 and margin >= 0.06 else None
    confidence = "high" if accepted and accepted.score >= 0.94 else "medium" if accepted else "low" if top else "none"
    reason = "exact or unambiguous entity match" if accepted else "candidate match is absent or ambiguous"
    return EntityResolveResponse(
        query=payload.name, candidates=candidates, accepted=accepted, confidence=confidence, reason=reason
    )


@app.post("/v1/assets/import", response_model=ImportedAsset)
async def import_asset(payload: AssetImportRequest, request: Request) -> ImportedAsset:
    response, raw, truncated = await _external_get(
        _client(request), str(payload.url), max_bytes=payload.max_bytes, accept="image/*,application/pdf"
    )
    if truncated:
        raise HTTPException(status_code=413, detail="asset exceeds the configured byte limit")
    media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
    media_type = _verified_asset_media_type(raw, media_type)
    allowed = media_type.startswith("image/") if payload.expected_kind == "image" else media_type == "application/pdf"
    if not allowed:
        raise HTTPException(status_code=415, detail=f"unexpected asset media type: {media_type}")
    digest = hashlib.sha256(raw).hexdigest()
    extension = mimetypes.guess_extension(media_type) or ".bin"
    target_dir = ASSET_ROOT / digest[:2]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o755)
    target = target_dir / f"{digest}{extension}"
    if not target.exists():
        target.write_bytes(raw)
        target.chmod(0o644)
    retrieved_at = datetime.now(UTC).isoformat()
    metadata = target.with_suffix(target.suffix + ".json")
    metadata.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sha256": digest,
                "path": str(target),
                "source_url": str(response.url),
                "source_page_url": str(payload.source_page_url) if payload.source_page_url else "",
                "target": payload.target,
                "role": payload.role,
                "media_type": media_type,
                "bytes": len(raw),
                "retrieved_at": retrieved_at,
                "license_state": payload.license_state,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    metadata.chmod(0o644)
    return ImportedAsset(
        source_url=str(response.url),
        source_page_url=payload.source_page_url,
        sha256=digest,
        media_type=media_type,
        bytes=len(raw),
        path=str(target),
        retrieved_at=retrieved_at,
        license_state=payload.license_state,
        metadata_path=str(metadata),
    )
