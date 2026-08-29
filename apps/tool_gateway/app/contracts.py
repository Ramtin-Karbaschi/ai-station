from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    category: Literal["general", "images", "news"] = "general"
    language: str = Field(default="auto", min_length=2, max_length=20)
    limit: int = Field(default=8, ge=1, le=20)


class SearchResult(BaseModel):
    title: str
    url: HttpUrl
    snippet: str = ""
    engine: str | None = None
    thumbnail_url: HttpUrl | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    source: Literal["searxng"] = "searxng"


class FetchRequest(BaseModel):
    url: HttpUrl
    max_bytes: int = Field(default=1_500_000, ge=1_024, le=5_000_000)


class FetchResponse(BaseModel):
    final_url: HttpUrl
    media_type: str
    title: str = ""
    text: str
    truncated: bool = False


class EntityResolveRequest(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    kind: Literal["vehicle", "brand", "organization", "person", "place", "other"] = "other"
    language: str = Field(default="auto", min_length=2, max_length=20)
    limit: int = Field(default=5, ge=1, le=10)


class EntityCandidate(BaseModel):
    entity_id: str
    label: str
    description: str = ""
    url: HttpUrl
    score: float = Field(ge=0, le=1)
    source: Literal["wikidata"] = "wikidata"


class EntityResolveResponse(BaseModel):
    query: str
    candidates: list[EntityCandidate]
    accepted: EntityCandidate | None = None
    confidence: Literal["high", "medium", "low", "none"]
    reason: str


class AssetImportRequest(BaseModel):
    url: HttpUrl
    source_page_url: HttpUrl | None = None
    target: str = Field(default="", max_length=300)
    role: Literal["subject_identity", "logo", "document", "other"] = "other"
    license_state: str = Field(default="unknown", max_length=100)
    expected_kind: Literal["image", "document"] = "image"
    max_bytes: int = Field(default=12_000_000, ge=1_024, le=25_000_000)


class ImportedAsset(BaseModel):
    source_url: HttpUrl
    source_page_url: HttpUrl | None = None
    sha256: str
    media_type: str
    bytes: int
    path: str
    retrieved_at: str
    license_state: str = "unknown"
    metadata_path: str


class CapabilitiesResponse(BaseModel):
    service: str = "ai-station-tool-gateway"
    version: str
    tools: list[str]
    constraints: dict[str, str | int | bool]
    capabilities: dict[str, dict[str, str | bool]] = Field(default_factory=dict)
