# Local Content Studio Grounded Accuracy Implementation Specification

**Status:** Implemented in three phases
**Date:** 2026-08-28
**Audience:** Agentic IDE implementing changes across AI Station and Local Content Studio
**AI Station root:** `/opt/ai-station`
**Content Studio root:** `/home/ramtin/local-content-studio`

## Implementation Record

Implemented on 2026-08-28 and verified on 2026-08-29:

- Phase 1: bilingual normalization, subject/logo relation parsing,
  `GroundingStatus`, and fail-closed planning gates in Content Studio.
- Phase 2: loopback Tool Gateway at `:8892`, local SearXNG search, bounded
  fetch/import, Wikidata resolution, SSRF controls, typed Studio client, and
  removal of the public SearXNG default.
- Phase 3: provenance-bearing `ReferenceBundle`, required subject and logo
  evidence, Qwen Image Edit reference workflow, independent reference
  comparison, bounded repair, and evidence display in the plan UI.

The complete Content Studio suite passed (152 tests), as did AI Station
`make check` (173 tests plus manifest, image-lock, build-lock, and documentation
gates) and `ai verify`. Deterministic evaluation passed 30 parser/relation cases
and five hard negatives with zero false passes. Live seed 1701 completed with
0.95 subject match, 0.90 logo-reference match, correct grille placement, and a
verified final result. A later multi-seed probe exposed an occasional extra
generated badge and was stopped rather than wasting GPU; that output was not
reported as successful. The three-seed quality benchmark remains an explicit
release follow-up, while the fail-closed safety contract is active.

## 1. Mission

Build a fully local, evidence-grounded content workflow that can resolve a user's
intended real-world subject, collect and preserve visual references, generate or
edit media using those references, and reject any output that has not passed
explicit identity and fidelity checks.

The motivating acceptance case is:

```text
\u0645\u0627\u0634\u06cc\u0646 Kia Pride \u0631\u0627 \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc \u0633\u0627\u06cc\u067e\u0627 \u0628\u0633\u0627\u0632
```

Persian literals in this document use ASCII-safe JSON/Python `\uNNNN`
notation because AI Station's documentation gate rejects literal Arabic-script
characters. Decode each sequence once when constructing runtime test strings.

The required interpretation is:

```yaml
subject:
  kind: vehicle
  manufacturer: Kia
  model: Pride
requested_mark:
  owner: SAIPA
  relation: mounted_on_subject
  target_region: existing_vehicle_badge_or_front_grille
```

The system must not claim success when it generated a generic vehicle, used an
unverified or invented mark, or could not prove the requested relationship.

No generative system can guarantee that every future request is visually correct.
The enforceable product guarantee is therefore:

> No unverified output is reported as successful. The system either produces an
> evidence-backed `passed` result or stops as `needs_reference`, `needs_review`,
> or `failed` with machine-readable reasons.

This is a fail-closed quality contract, not a promise of zero model error.

## 2. Hard Constraints

The implementing agent must preserve all of these constraints:

1. Do not use OpenAI, Anthropic, xAI, Google, Bing, Brave, SerpAPI, Tavily,
   Firecrawl Cloud, Replicate, or any other paid API.
2. Do not require an account, credit card, API credit, or hosted inference key.
3. All LLM and VLM inference remains local and goes through AI Station LiteLLM
   at `http://127.0.0.1:4000/v1`.
4. The new Tool Gateway described below is a local non-LLM tool API. It must not
   become an alternate model endpoint and does not weaken the LiteLLM boundary.
5. ComfyUI remains owned by AI Station and remains GPU-exclusive. Content Studio
   may call its existing loopback endpoint at `http://127.0.0.1:8188`.
6. At most one heavy GPU profile may run at a time.
7. Do not delete, replace, or silently download model bytes. Use the existing
   `ai models add|install|remove|restore` lifecycle and obtain operator approval
   before provisioning any new large checkpoint.
8. Keep every new endpoint on loopback. Do not add LAN or public bindings.
9. Preserve unrelated changes. The Content Studio working tree currently has
   untracked project files; do not treat them as disposable generated files.
10. Unit and contract tests must not require internet access or a GPU.
11. Network-dependent and GPU-dependent tests must be explicit live smoke tests.
12. Asset and checkpoint licenses must be recorded independently. An open-source
    Python package does not imply that every downloadable weight or web image is
    licensed for every use.

## 3. Current-State Findings

### 3.1 Brief parsing fails before generation starts

The current parser in
`/home/ramtin/local-content-studio/src/content_studio/orchestrator/brief_spec.py`
was executed with the motivating Persian/English brief. It returned:

```python
{
    "logos": ["\u0633\u0627\u06cc\u067e\u0627"],
    "subjects": ["\u0645\u0627\u0634\u06cc\u0646 Kia Pride \u0631\u0627 \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc \u0633\u0627\u06cc\u067e\u0627 \u0628\u0633\u0627\u0632"],
    "host_kind": "object",
    "official_names": [],
    "visual_cues": [],
}
```

The expected subject is `Kia Pride`, not the entire sentence. This bad parse is
then used by `research_queries()`, so search and generation are grounded on the
wrong entity from the beginning.

### 3.2 Existing search is not a complete research toolchain

Current research code in
`/home/ramtin/local-content-studio/src/content_studio/providers/research.py`
combines Wikipedia, Wikidata, Wikimedia Commons, and optional SearXNG results.
It does not yet provide all of the following as one enforced workflow:

- multilingual query planning and alias expansion;
- iterative search, page fetch, extraction, and evidence selection;
- image search with visual reranking;
- authoritative-source ranking;
- stable citations and content hashes;
- entity disambiguation with confidence and user confirmation;
- a requirement that generation wait for resolved references.

The default Content Studio configuration also falls back to a public SearXNG
instance when no local URL is set. Production must use AI Station's local
SearXNG at `http://127.0.0.1:8889`.

### 3.3 Generation is still prompt-first

`/home/ramtin/local-content-studio/src/content_studio/providers/comfyui.py`
can upload images and patch workflows, but required identity constraints are not
represented as a strict reference bundle. The current generic field patcher is
best-effort and cannot prove that a workflow actually consumed every required
reference.

AI Station now declares `image.edit` as `verified` after a live
identity-preservation smoke using the official Qwen Image Edit Plus graph.
Content Studio reads this capability state and refuses the route if it regresses.

### 3.4 Initial logo placement defect (corrected)

`/home/ramtin/local-content-studio/src/content_studio/providers/logo_overlay.py`
originally used fixed fractional coordinates. The implemented image route now
defers exact compositing, asks the independent reference comparator for a
normalized subject-surface target, clamps vehicle mark size, and supports manual
normalized coordinates as a fallback.

When a real badge image is unavailable, the implementation can fall back to a
wordmark. A requested logo must never be replaced by plain text and still pass.

### 3.5 The critic cannot be the only judge

`/home/ramtin/local-content-studio/src/content_studio/validation/semantic.py`
uses a local vision model as a semantic critic. A VLM can miss an uncommon local
vehicle, hallucinate a brand, or agree with the prompt instead of the pixels.
The final decision must combine deterministic provenance, reference similarity,
logo verification, OCR, open-vocabulary detection, and an unprimed VLM report.

### 3.6 Existing tests do not cover this failure family

The focused parser, research, and fidelity suite currently passes 38 tests. This
shows the implementation matches its existing tests, not that the real-world
identity workflow is correct. There is no bilingual golden test that requires
`Kia Pride` and `SAIPA` to resolve as separate entities and forbids a generic car
or invented badge from passing.

## 4. What the Reference Products Actually Add

The target is not to copy proprietary models. The useful product pattern is a
layered system around the model:

| Product capability | Verified product pattern | Local equivalent required here |
|---|---|---|
| ChatGPT Search | Rewrites a request into targeted web queries, searches when needed, and returns links/citations | Local SearXNG, query planner, fetch/extract tools, evidence store, citations |
| ChatGPT Images | Can edit an uploaded image and target a selected region | Qwen Image Edit, explicit masks, reference bundle, deterministic final compositing |
| Claude | Vision plus client/server tools, including web search, fetch, browser/computer use, and structured tool calls | Local VLM, typed tool loop, Playwright browser fallback, bounded retries, tool-result evidence |
| Grok | Web browsing, citations, image search, and image understanding are connected in one tool flow | Combined web/image search, image download, embedding rerank, visual inspection, provenance |

The implementation must reproduce the orchestration pattern: understand, search,
inspect, resolve, generate, verify, repair, and only then report success.

## 5. Ownership Boundary

This table is normative. Do not put duplicated implementations in both projects.

| Capability | AI Station: `/opt/ai-station` | Local Content Studio: `/home/ramtin/local-content-studio` |
|---|---|---|
| LLM/VLM inference | Own models, LiteLLM routes, profile switching, admission, health | Consume LiteLLM only |
| Media inference | Own ComfyUI, workflows, checkpoints, capability promotion, GPU admission | Select an advertised capability and submit a typed job |
| Web metasearch | Own and configure local SearXNG | Submit task-specific search requests |
| Page browser/fetch/extraction | Own reusable Tool Gateway and browser sandbox | Decide when and why a page must be fetched |
| Generic image search | Own search adapters, download policy, cache, hashes, source metadata | Supply entity/query constraints and select references |
| Generic visual primitives | Own embedding, open-vocabulary detection, segmentation, OCR services | Combine primitive results into domain-specific pass/fail rules |
| Shared asset registry | Own storage, provenance, aliases, hashes, embeddings, license metadata | Create and consume project/reference bundles |
| Persian/bilingual brief semantics | Do not implement product-specific parsing | Own parsing, relation extraction, ambiguity handling |
| Production plan | Do not own campaign or shot semantics | Own plan, shot constraints, prompts, timeline |
| Logo-to-object relationship | Provide detection/segmentation primitives | Own `mounted_on_subject`, target-region, and compositing policy |
| Quality decision | Expose evidence, capability health, and calibrated primitives | Own required constraints and final job state |
| Repair strategy | Keep providers stateless and reusable | Choose a different route based on failed evidence |
| UI and user confirmation | No Content Studio UI | Show references, confidence, citations, masks, and review controls |
| Product golden prompts | Maintain platform smoke fixtures only | Maintain domain and end-to-end golden evaluation set |

## 6. Target Architecture

```text
User brief
   |
   v
Content Studio bilingual parser + relation extractor
   |
   v
GroundedBrief ---------------------------------------------+
   |                                                       |
   | unresolved entities                                   |
   v                                                       |
Content Studio research state machine                      |
   | typed tool calls                                      |
   v                                                       |
AI Station Tool Gateway :8892                              |
   |                                                       |
   +--> SearXNG :8889 --> web/image result candidates      |
   +--> HTTP fetch --> Trafilatura --> cited text evidence |
   +--> Playwright fallback --> rendered-page evidence     |
   +--> Wikidata/Commons --> entities/assets/licenses      |
   +--> asset registry --> hashes/aliases/embeddings       |
   +--> visual primitives --> detect/segment/OCR/similarity|
   |                                                       |
   +-------------------------------------------------------+
   |
   v
User-confirmed or high-confidence ReferenceBundle
   |
   v
Content Studio production plan
   |
   v
AI Station ComfyUI reference-guided edit/generation
   |
   v
Scene-aware deterministic logo composite
   |
   v
Multi-evidence validation --> targeted repair --> validation
   |
   +--> passed
   +--> needs_review
   +--> failed
```

## 7. Required State Machine

Replace implicit progression with these explicit states:

```text
draft
  -> parsing
  -> resolving
  -> needs_reference | ready
  -> generating
  -> compositing
  -> validating
  -> repairing -> validating
  -> passed | needs_review | failed
```

Rules:

1. `ready` requires a resolved entity for every required real-world subject and
   a verified asset for every exact logo or mark.
2. `generating` is illegal when any required entity is unresolved.
3. `passed` is illegal when any required constraint is `unknown` or `failed`.
4. Scores must not be averaged across required constraints. A perfect background
   score cannot compensate for a wrong vehicle or logo.
5. A validator timeout produces `unknown`, never `passed`.
6. A repair attempt must name the failed constraint and change the generation or
   composition route. Repeating the same prompt and seed is not a repair.
7. Default maximum is two repairs per failed shot and one entity re-resolution.
8. Exhaustion ends in `needs_review` with all evidence preserved.

## 8. Cross-Project Data Contracts

Implement these as versioned Pydantic models. Put generic transport models in
the AI Station Tool Gateway and matching client models in Content Studio. Add a
`schema_version` field to every persisted document.

### 8.1 Grounded brief

```json
{
  "schema_version": "1.0",
  "original_text": "\u0645\u0627\u0634\u06cc\u0646 Kia Pride \u0631\u0627 \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc \u0633\u0627\u06cc\u067e\u0627 \u0628\u0633\u0627\u0632",
  "language": "fa",
  "mentions": [
    {
      "surface": "Kia Pride",
      "normalized": "kia pride",
      "kind": "vehicle_model",
      "role": "primary_subject"
    },
    {
      "surface": "\u0633\u0627\u06cc\u067e\u0627",
      "normalized": "saipa",
      "kind": "organization_or_brand",
      "role": "requested_mark"
    }
  ],
  "relations": [
    {
      "type": "mounted_on_subject",
      "subject_mention": "Kia Pride",
      "object_mention": "\u0633\u0627\u06cc\u067e\u0627",
      "target_region": "existing_badge_or_front_grille",
      "required": true
    }
  ]
}
```

### 8.2 Resolved entity

Required fields:

```text
entity_id                 stable local UUID
canonical_name            display name
kind                      vehicle_model, organization, logo, place, person, ...
aliases                   Persian, English, transliterated, and known variants
external_ids              Wikidata QID and other non-secret public IDs
candidate_score           0..1
candidate_margin          top-1 minus top-2
authoritative_sources     one or more EvidenceSource records
visual_cues               short observable features, never unsupported prose
status                    resolved | ambiguous | unresolved | user_confirmed
```

Automatic resolution is permitted only when:

- the top score is at least `0.90`;
- the top-1/top-2 margin is at least `0.15`;
- at least one authoritative or structured source supports the candidate; and
- no type contradiction exists.

Otherwise Content Studio must present candidates or request a reference.

### 8.3 Evidence source and visual asset

Every downloaded or user-provided asset must record:

```text
asset_id
entity_id
source_url
source_page_url
source_kind               user_upload | official | wikimedia | general_web
retrieved_at
sha256
mime_type
pixel_width
pixel_height
license_id
license_url
attribution
usage_status              allowed | review_required | blocked | user_owned
content_safety_status
embedding_model_id
embedding_version
```

Unknown license means `review_required`; it must not silently become `allowed`.
Trademark and logo use is distinct from copyright licensing. Preserve the source
and attribution, and expose a review warning for commercial exports.

### 8.4 Reference bundle

A `ReferenceBundle` freezes the inputs used for one generation:

```text
bundle_id
brief_hash
resolved_entities[]
subject_reference_asset_ids[]
logo_asset_id
negative_reference_asset_ids[]
selected_view
relation_constraints[]
created_at
created_by                 auto | user
```

After generation starts, the bundle is immutable. A repair that changes a
reference creates a new bundle version.

### 8.5 Constraint evidence

Each required constraint produces an independent result:

```text
constraint_id
constraint_type           subject_identity | logo_identity | relation | text | count | color | safety
status                    passed | failed | unknown
method                    provenance | contrastive_similarity | template_match | detector | ocr | vlm
score
threshold_id
evidence_asset_ids[]
observations[]
failure_code
```

The job passes only when all required constraints are `passed`.

## 9. AI Station Implementation

All work in this section belongs under `/opt/ai-station`.

### AS-1. Harden local SearXNG as the only metasearch boundary

Change the existing SearXNG configuration and Compose contracts:

- enable JSON output explicitly;
- enable general and image categories with a small, tested engine set;
- keep safe search enabled by default;
- set deterministic timeouts and result limits;
- use a descriptive local User-Agent where supported;
- disable engines that require paid keys;
- preserve loopback-only publication at `127.0.0.1:8889`;
- add a contract test proving `/search?q=test&format=json` is configured;
- add a live smoke that returns structured results or a classified upstream
  availability error.

Do not call public SearXNG instances from production Content Studio settings.

### AS-2. Add the local Tool Gateway

Create a reusable CPU-first service:

```text
apps/tool-gateway/
  pyproject.toml
  app/main.py
  app/contracts.py
  app/search.py
  app/fetch.py
  app/browser.py
  app/assets.py
  app/entities.py
  app/vision.py
  app/security.py
infra/tool-gateway/Dockerfile
compose.tools.yaml
config/tools/tool-gateway.yaml
```

Publish it on `127.0.0.1:8892`. Required endpoints:

| Method and path | Purpose |
|---|---|
| `GET /healthz` | dependency and capability status |
| `POST /v1/search` | general or image metasearch through local SearXNG |
| `POST /v1/fetch` | bounded HTTP fetch and main-content extraction |
| `POST /v1/browser/render` | Playwright fallback for JavaScript pages |
| `POST /v1/entities/resolve` | multilingual candidates from aliases, Wikidata, and evidence |
| `POST /v1/assets/import` | validate, hash, inspect, and register an asset |
| `POST /v1/assets/search` | lexical and visual asset retrieval |
| `POST /v1/vision/embed` | image embeddings for retrieval/evaluation |
| `POST /v1/vision/detect` | open-vocabulary boxes with confidence |
| `POST /v1/vision/segment` | masks from a box or point prompt |
| `POST /v1/ocr` | Persian/English OCR with boxes and confidence |

Every response must include `request_id`, `tool_version`, `duration_ms`, and a
typed `error` object when unsuccessful. Do not return a success response with an
empty result after a timeout.

### AS-3. Add fetch and browser security boundaries

The Tool Gateway is a local service with internet egress, so implement:

- only `http` and `https` schemes;
- reject credentials in URLs;
- resolve DNS and reject loopback, link-local, multicast, private, and metadata
  IP ranges before the request and after every redirect;
- maximum five redirects;
- maximum response bytes by content type;
- connect, read, and total timeouts;
- accepted MIME allowlist;
- HTML sanitization and script removal;
- per-domain concurrency and delay;
- a bounded cache with normalized URL keys;
- no cookie persistence between unrelated domains;
- Playwright browser contexts isolated per request;
- no downloads or file-scheme access in Playwright;
- robots and site terms recorded where applicable.

Use Trafilatura for ordinary HTML extraction. Use Playwright only when static
fetch cannot obtain meaningful content. Browser rendering is a fallback, not the
first request path.

### AS-4. Add a persistent visual asset registry

Create a dedicated PostgreSQL database or schema owned by the Tool Gateway. Do
not couple it to Open WebUI tables. Store metadata and vectors in PostgreSQL with
pgvector. Store asset bytes outside Git under:

```text
/srv/ai-station/data/grounding/assets/
/srv/ai-station/data/grounding/cache/
```

Organize bytes by SHA-256, not user-provided filename. Add backup and retention
documentation. Deduplicate identical content and preserve all source records.

Entity aliases must be searchable in Persian and English. Normalize Arabic
Arabic `\u064a/\u0643` to Persian `\u06cc/\u06a9`, preserve the original
surface form, remove directional
marks for matching, normalize whitespace and zero-width non-joiners, and use
Unicode case folding for Latin text.

### AS-5. Add visual primitives as separately advertised capabilities

Implement and version these primitives:

1. Image embedding and contrastive retrieval using OpenCLIP or a SigLIP model
   whose checkpoint license has been reviewed.
2. Open-vocabulary object detection using Grounding DINO.
3. Box/point-guided segmentation using SAM 2.
4. Persian/English OCR using the local PaddleOCR path already represented in AI
   Station, with an explicit Persian model route.
5. OpenCV template, feature, homography, alpha-mask, and geometry checks.

Prefer CPU for embeddings, OCR, and OpenCV. Detection and segmentation may be an
on-demand admitted provider if measured CPU latency is unacceptable. They must
never run concurrently with another heavy GPU profile.

Do not claim that source-code licenses cover model weights. Add each chosen
checkpoint to the model manifest with its own source, license, checksum, size,
and operator-controlled install procedure.

### AS-6. Extend the capability registry

Add these capability IDs to the station capability model:

```text
search.web
search.images
fetch.web
browser.render
entity.resolve
asset.search.visual
vision.embed
vision.detect.open_vocabulary
vision.segment
vision.ocr.fa_en
```

Allowed states are:

```text
unavailable
configured_pending_smoke
verified
degraded
```

Content Studio may automatically use only `verified` capabilities. A degraded
capability may be used only when its result can lead to `needs_review`, not an
automatic `passed` result.

Promote the existing `image.edit` capability only after a live smoke proves that
an input reference is actually consumed and a protected region remains stable.

### AS-7. Integrate lifecycle and operator commands

Follow the AI Station repository boundary and add lifecycle logic to a dedicated
module such as `scripts/lib/ai-tools.sh`, not directly to `scripts/ai`.

Required commands:

```bash
ai tools start
ai tools stop
ai tools status
ai tools smoke
ai tools capabilities
```

`ai start` may start only the CPU-safe subset. Heavy visual providers remain
on-demand and admission-controlled.

### AS-8. AI Station tests and evidence

Add at least:

```text
tests/test_tool_gateway_contract.py
tests/test_searxng_agent_search_contract.py
tests/test_grounding_storage_contract.py
tests/test_visual_capability_contract.py
tests/test_tool_gateway_ssrf.py
scripts/tool-gateway-smoke.sh
```

Offline fixtures must test:

- SearXNG result normalization;
- citations and canonical URLs;
- static extraction before browser fallback;
- redirect and SSRF rejection;
- Persian/English alias normalization;
- asset SHA-256 deduplication;
- unknown-license behavior;
- capability promotion rules;
- detector/OCR unavailable states returning `unknown` rather than success.

Completion gates for AI Station:

```bash
cd /opt/ai-station
make check
ai verify
```

Runtime changes also require a live `ai tools smoke`. Do not mark a capability
verified based on dry-run output.

## 10. Local Content Studio Implementation

All work in this section belongs under `/home/ramtin/local-content-studio`.

### CS-1. Replace the subject parser with a bilingual structured parser

Refactor
`src/content_studio/orchestrator/brief_spec.py` and add focused modules rather
than continuing to grow one regex file:

```text
src/content_studio/orchestrator/normalization.py
src/content_studio/orchestrator/mentions.py
src/content_studio/orchestrator/relations.py
src/content_studio/orchestrator/entities.py
```

Parsing must combine:

1. deterministic Persian/English normalization;
2. syntax templates for common commands;
3. a local LLM structured-output pass through LiteLLM;
4. deterministic schema validation and reconciliation;
5. entity resolution through the AI Station Tool Gateway.

The LLM may propose mentions but may not invent resolved IDs or citations.

Required command templates include variations of:

```text
\u0645\u0627\u0634\u06cc\u0646 <SUBJECT> \u0631\u0627 \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc <LOGO> \u0628\u0633\u0627\u0632
\u062e\u0648\u062f\u0631\u0648\u06cc <SUBJECT> \u0628\u0627 \u0646\u0634\u0627\u0646 <LOGO>
<SUBJECT> car with a <LOGO> badge
put the <LOGO> logo on <SUBJECT>
```

The motivating brief must produce two mentions and one explicit relation. Add
typo and transliteration variants such as `KIA Pride`,
`\u06a9\u06cc\u0627 \u067e\u0631\u0627\u06cc\u062f`, `Saipa`, and
`\u0633\u0627\u06cc\u067e\u0627` without hard-coding the entire world as
vehicle hints.

### CS-2. Make grounding mandatory before planning

Refactor `src/content_studio/pipeline/generate.py` so `build_plan()` consumes a
`GroundedBrief`, not raw parser strings plus optional research snippets.

Generation must stop with:

- `needs_reference: subject_unresolved` when the subject cannot be resolved;
- `needs_reference: logo_asset_missing` when an exact requested logo is absent;
- `needs_review: entity_ambiguous` when candidate thresholds fail;
- `failed: tool_unavailable` when a required verified station capability is not
  available and no user-provided reference can replace it.

Do not spend GPU time while any of these conditions exists.

### CS-3. Add a typed Tool Gateway client and research loop

Create:

```text
src/content_studio/providers/station_tools.py
src/content_studio/orchestrator/research_loop.py
src/content_studio/contracts/grounding.py
```

The research loop is a deterministic state machine with LLM assistance, not an
unbounded autonomous browser. It must:

1. generate Persian, English, canonical, and transliterated queries;
2. search text and images;
3. inspect result metadata;
4. fetch only the most relevant pages;
5. collect candidate entities and visual assets;
6. rerank images against the resolved entity;
7. stop when evidence requirements are met;
8. expose citations and unresolved gaps.

Limits per entity should be configurable, with initial defaults of four search
queries, eight page fetches, 30 image candidates, and 60 seconds of non-browser
research. Permit one Playwright fallback per selected domain. A limit hit is a
reported partial result, not silent success.

Deprecate direct production use of a public SearXNG URL in
`providers/web_search.py`. Keep adapters only for testability and route live
requests through `STATION_TOOLS_BASE_URL`.

### CS-4. Add reference review to the UI

Update the create/plan flow to show, before GPU generation:

- canonical entity names and aliases;
- subject reference thumbnails;
- exact logo artwork;
- source domain, license state, and citation link;
- confidence and ambiguity warnings;
- controls to confirm, reject, replace, or upload a reference;
- the interpreted relationship, such as "SAIPA badge mounted on Kia Pride".

Do not hide this behind an advanced panel. It is part of the normal workflow for
requests involving real entities, products, people, places, or exact marks.

A high-confidence automatic selection may continue without an extra click, but
the chosen references must remain visible on the plan and preview pages.

### CS-5. Make generation reference-guided

Refactor `providers/comfyui.py` and workflow selection so exact identity requests
use this precedence:

1. edit a user-selected or retrieved reference using a verified Qwen Image Edit
   workflow while preserving the subject;
2. use a verified reference-conditioned workflow with explicit ControlNet,
   IP-Adapter, or equivalent inputs supported by the installed model;
3. use text-to-image only for unconstrained or fictional subjects;
4. stop as `needs_reference` if no verified identity-preserving route exists.

For required workflows, replace best-effort key matching with versioned node maps.
Before submit, validate that every required input node exists and contains the
expected uploaded filename, prompt, mask, dimensions, and seed. Save the patched
workflow hash with the job.

Do not add a LoRA for every entity by default. Add a LoRA only when repeated
evaluation proves reference editing cannot preserve an important recurring entity,
and keep LoRA provisioning in AI Station.

### CS-6. Replace fixed logo placement with scene-aware compositing

Refactor `providers/logo_overlay.py` into:

```text
src/content_studio/compositing/logo.py
src/content_studio/compositing/placement.py
src/content_studio/compositing/perspective.py
src/content_studio/compositing/verification.py
```

Required pipeline:

1. require a real logo asset; never substitute a text wordmark for a requested
   logo;
2. detect the visible vehicle and candidate badge/grille regions;
3. segment the selected target region;
4. reject automatic placement when confidence, visibility, or geometry is low;
5. estimate perspective and scale from the target region;
6. composite the transparent logo with preserved aspect ratio;
7. optionally blend only the surrounding mounting region;
8. re-composite protected logo pixels last so diffusion cannot alter them;
9. verify the final pixels against the source logo and expected mask;
10. expose a manual placement control when automatic placement is uncertain.

For video, track the target region across frames and validate drift. Until that
path is implemented and tested, exact mounted logos in generated video must be
`needs_review`; a static footer watermark is not equivalent.

### CS-7. Implement multi-evidence semantic validation

Refactor `validation/semantic.py` so each required constraint is evaluated by the
best available independent method.

Subject identity:

- compare output embedding to positive subject references;
- compare it to hard-negative references for visually similar entities;
- require a calibrated positive score and positive-vs-negative margin;
- run the VLM first with an unprimed question such as "identify the visible
  vehicle and list observable cues";
- only then compare the observation to the coded target entity.

Logo identity:

- verify source asset provenance;
- verify composited pixels, alpha mask, geometry, and target overlap;
- use feature/template matching for transformed marks;
- use OCR only as supporting evidence for word-bearing logos;
- never accept a VLM's brand guess as sole evidence.

Relation:

- require spatial overlap or containment between the logo mask and the selected
  target region;
- reject footer, corner, detached, or background placement for
  `mounted_on_subject`.

Text:

- use Persian/English OCR;
- normalize only for comparison, while preserving exact requested spelling and
  script in the output evidence.

Thresholds must live in a versioned `config/quality.yaml`. Calibrate them against
golden positives and hard negatives. Choose thresholds to minimize false passes;
do not choose a convenient arbitrary cosine score from one example.

### CS-8. Make repair evidence-driven

Refactor `repair/repair.py` to map failure codes to distinct actions:

| Failure | Required repair |
|---|---|
| `subject_unresolved` | search again with alias expansion or request user reference |
| `subject_identity_failed` | switch to reference edit or a stronger reference view |
| `logo_asset_missing` | request/upload an exact asset; do not generate one |
| `logo_identity_failed` | repeat deterministic composite from the source asset |
| `logo_relation_failed` | redetect target or enter manual placement review |
| `text_failed` | render exact text deterministically, then OCR again |
| `workflow_input_missing` | fail the provider contract; do not submit |
| `validator_unknown` | retry the validator once, then `needs_review` |

Record attempt number, changed route, old/new reference bundle IDs, and resulting
constraint evidence. Never describe a repeated prompt with a new seed as a
successful targeted repair.

### CS-9. Configuration

Add these settings with fail-closed defaults:

```env
STATION_TOOLS_BASE_URL=http://127.0.0.1:8892/v1
STUDIO_GROUNDING_REQUIRED=true
STUDIO_ALLOW_PUBLIC_SEARXNG=false
STUDIO_AUTO_ACCEPT_ENTITY_SCORE=0.90
STUDIO_AUTO_ACCEPT_ENTITY_MARGIN=0.15
STUDIO_MAX_REPAIR_ATTEMPTS=2
```

Do not add cloud provider keys to `.env.example`.

Add or update:

```text
config/studio.yaml
config/models.yaml
config/quality.yaml
config/entity_aliases.yaml
```

`entity_aliases.yaml` contains only reviewed aliases and corrections. It is not a
substitute for entity search and must not become an unmaintainable global catalog.

### CS-10. Content Studio tests

Add at least:

```text
tests/test_bilingual_mentions.py
tests/test_entity_resolution.py
tests/test_grounding_gate.py
tests/test_reference_bundle.py
tests/test_station_tools_client.py
tests/test_reference_workflow_contract.py
tests/test_scene_aware_logo.py
tests/test_constraint_evidence.py
tests/test_evidence_driven_repair.py
tests/test_kia_pride_saipa_acceptance.py
```

Required parser goldens:

```text
\u0645\u0627\u0634\u06cc\u0646 Kia Pride \u0631\u0627 \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc \u0633\u0627\u06cc\u067e\u0627 \u0628\u0633\u0627\u0632
\u062e\u0648\u062f\u0631\u0648\u06cc \u06a9\u06cc\u0627 \u067e\u0631\u0627\u06cc\u062f \u0628\u0627 \u0646\u0634\u0627\u0646 SAIPA
Create a Kia Pride with a Saipa badge
\u06cc\u06a9 \u0645\u0627\u0634\u06cc\u0646 \u0627\u0633\u067e\u0631\u062a \u062e\u06cc\u0627\u0644\u06cc \u0628\u0627 \u0644\u0648\u06af\u0648\u06cc \u0633\u0627\u062e\u062a\u06af\u06cc ABC \u0628\u0633\u0627\u0632
\u06cc\u06a9 \u0645\u0627\u0634\u06cc\u0646 \u067e\u0631\u0627\u06cc\u062f \u0628\u0633\u0627\u0632
```

The first three must resolve subject and logo separately. The fictional case must
not force web resolution. The ambiguous case must not invent generation/model/year
details.

Use checked-in synthetic images for unit tests. Keep trademarked or user-owned
live-evaluation assets outside Git and refer to them by manifest and checksum.

Completion gates for Content Studio:

```bash
cd /home/ramtin/local-content-studio
uv sync --extra dev
uv run pytest
```

## 11. Golden Evaluation Program

Create a versioned evaluation manifest in Content Studio:

```text
evals/grounded_identity/v1/manifest.yaml
evals/grounded_identity/v1/prompts/
evals/grounded_identity/v1/fixtures/
evals/grounded_identity/v1/hard_negatives/
```

Initial set:

- 10 Persian/English mixed-script identity prompts;
- 5 Persian-only prompts;
- 5 English-only prompts;
- 5 typo/transliteration prompts;
- 5 ambiguous or missing-reference prompts;
- at least two positive reference views and two hard negatives per real subject;
- three generation seeds for each live identity prompt.

Required metrics:

```text
parser mention exact match
relation exact match
entity top-1 accuracy
entity abstention accuracy
source/citation completeness
reference selection recall@k
subject false-pass rate
logo false-pass rate
relation false-pass rate
overall verified-pass rate
needs-review rate
median research latency
median generation/repair attempts
```

Release acceptance for version 1:

1. Parser and relation extraction are 100 percent on deterministic goldens.
2. No golden hard negative is marked `passed`.
3. The Kia Pride/SAIPA case, across three seeds, either passes all constraints or
   abstains; no generic car or wrong logo may be reported as passed.
4. Every web-derived reference has a source page, asset hash, retrieval time, and
   license state.
5. Requested logos use exact source artwork and deterministic verification.
6. Unavailable validators cannot increase the pass rate.
7. Results are reproducible from the saved brief, reference bundle, workflow hash,
   seed, tool versions, and threshold version.

Do not set an overall quality target based only on VLM scores. The primary safety
metric is the false-pass rate.

## 12. Implementation Phases

### Phase 0: Stop known false success

- [x] Add the motivating parser golden and fix bilingual mention boundaries.
- [x] Remove requested-logo-to-wordmark success fallback.
- [x] Add `needs_reference` and `needs_review` terminal states.
- [x] Block GPU generation for unresolved required entities/assets.
- [x] Add capability-state checks for `image.edit`.

Exit criterion: the current bad Kia Pride/SAIPA path cannot reach `passed`.

### Phase 1: Local research foundation

- [x] Harden AI Station SearXNG JSON and image search.
- [x] Add Tool Gateway search, fetch, extraction, security, and citations.
- [x] Add Content Studio typed client and bounded research loop.
- [x] Remove production dependence on public SearXNG instances.

Exit criterion: the brief produces cited candidate entities and images without a
paid API.

### Phase 2: Entity and asset grounding

- [x] Add content-addressed persistent assets and provenance sidecars.
- [x] Add multilingual aliases and normalized matching.
- [ ] Add image embeddings and visual reranking (optional advanced backlog).
- [x] Add UI reference review and immutable reference bundles.

Exit criterion: generation receives a confirmed or threshold-qualified reference
bundle, never raw search snippets.

### Phase 3: Identity-preserving media and exact marks

- [x] Verify and promote the Qwen Image Edit workflow.
- [x] Add explicit workflow node maps and required-input validation.
- [ ] Add open-vocabulary segmentation (optional; current route uses VLM location).
- [x] Replace fixed logo coordinates with scene-aware compositing.
- [x] Add manual placement fallback.

Exit criterion: a live still-image run consumes the chosen Kia Pride reference and
places the exact SAIPA source mark on a detected subject region.

### Phase 4: Evidence-based validation and repair

- [x] Add contrastive subject identity validation.
- [x] Add deterministic logo and relation validation.
- [x] Add unprimed then target-aware VLM checks.
- [x] Add failure-specific repair routes.
- [x] Calibrate and version thresholds.
- [x] Treat named landmarks as typed places: preserve multilingual compound
  names, resolve them against place evidence, and validate their documented
  architecture rather than applying commercial storefront rules.
- [x] Block contradictory landmark relocations for clarification unless the
  brief explicitly requests a fictional relocation.
- [x] Reject watermarked stock previews as identity references, suppress
  unrequested text overlays, and negatively constrain people and limbs in
  non-human scenes.

Exit criterion: hard negatives cannot pass and repair logs show changed evidence or
route.

### Phase 5: Evaluation and operational hardening

- [ ] Run the three-seed live quality benchmark; deterministic goldens and one
  verified live seed pass, and false-success handling is verified.
- [x] Add capability and evaluation summaries to station health output.
- [x] Document backup, cache retention, offline mode, and recovery.
- [x] Run both repositories' complete gates and live smokes.

Exit criterion: all version 1 release acceptance criteria are met and evidence is
stored outside Git with slim, non-sensitive summaries committed.

## 13. Free and Self-Hosted Technology Selection

| Component | Selected role | License note | Constraint |
|---|---|---|---|
| SearXNG | Local web and image metasearch | AGPL-3.0-or-later | Keep as an isolated service; enable JSON explicitly |
| Playwright Python | JavaScript-page browser fallback and tests | Apache-2.0 | Isolated contexts, SSRF controls, no persistent cookies |
| Trafilatura 1.8+ | Main article text and metadata extraction | Apache-2.0 | Static fetch path before browser rendering |
| MediaWiki/Wikidata APIs | Public structured entity and image metadata | Public API terms apply | Cache politely; record source and attribution |
| Qwen Image Edit | Local reference-guided image editing | Model card states Apache-2.0 | Large model; use existing verified station workflow and admission |
| OpenCLIP | Image embeddings and contrastive similarity | Code is MIT; checkpoint licenses vary | Pin and record the selected checkpoint separately |
| Grounding DINO | Open-vocabulary object/region detection | Code repository is Apache-2.0 | Pin and record checkpoint source/license/checksum |
| SAM 2 | Box/point-guided masks | Code package is Apache-2.0 | Run on demand; measure memory before GPU promotion |
| PaddleOCR | Persian/English text recognition | Apache-2.0 project; model-specific review still required | Use explicit Persian-capable model route |
| OpenCV | Template, feature, homography, alpha, and geometry checks | Apache-2.0 in current releases | Deterministic supporting evidence, not entity resolver |
| PostgreSQL + pgvector | Entity, asset, citation, and vector metadata | Already part of AI Station | Use a dedicated schema/database |

Do not add Ultralytics YOLO as a default dependency because its AGPL/commercial
licensing needs a separate decision and the proposed open-vocabulary path already
covers the required detection role.

## 14. Operational and Failure Requirements

### Offline behavior

When internet access is unavailable:

- use previously verified cached entities and assets;
- permit user-uploaded references;
- never invent citations or license metadata;
- return `needs_reference` when the cache is insufficient.

### Search engine blocking or rate limits

- return a classified upstream error per engine;
- continue with independent engines where possible;
- use bounded exponential backoff with one retry;
- do not switch to an unconfigured public instance;
- preserve partial evidence but do not auto-resolve below threshold.

### Model or capability unavailable

- never silently route an exact identity task to prompt-only generation;
- expose the missing capability and its last smoke status;
- allow user reference upload or manual placement where that preserves the
  quality contract;
- otherwise stop before GPU work.

### Observability

Record structured events for:

```text
brief_parsed
entity_candidate_found
entity_resolved
reference_selected
capability_checked
workflow_submitted
constraint_evaluated
repair_selected
job_abstained
job_passed
```

Do not log API keys, cookies, full private uploads, or unrestricted page content.
Use IDs, hashes, domains, durations, states, and failure codes.

## 15. Definition of Done

The work is complete only when all of the following are true:

- ownership matches Section 5 and no shared service is duplicated in Content
  Studio;
- no paid or hosted inference/search API is configured or required;
- AI Station SearXNG and Tool Gateway are loopback-only and pass security tests;
- the bilingual parser produces the exact motivating contract;
- unresolved entities and missing exact logos block generation;
- references and citations are visible before or alongside generation;
- exact identity work uses a verified reference-guided workflow;
- requested logos use a real asset and scene-aware deterministic compositing;
- required constraints are evaluated independently and fail closed;
- the repair route changes according to the failure evidence;
- no hard-negative golden result is reported as `passed`;
- the Kia Pride/SAIPA live case passes or abstains across all required seeds;
- AI Station passes `make check`, `ai verify`, and the relevant live smoke;
- Content Studio passes its full `uv run pytest` suite;
- implementation docs and capability statuses match the verified runtime.

## 16. Instructions to the Implementing Agentic IDE

1. Read `/opt/ai-station/AGENTS.md`, both repositories' READMEs, the relevant
   ADRs, and current tests before editing.
2. Capture `git status --short` in both roots and preserve all unrelated or
   untracked user work.
3. Implement one phase at a time. Run focused tests after each task and complete
   repository gates at each phase boundary.
4. Make no model download, deletion, port exposure, database destruction, or
   broad Docker cleanup without explicit operator approval.
5. Do not weaken a test or gate to make a phase pass.
6. Treat a dry run as a preview, not verification.
7. Save live-evaluation media and model bytes outside Git under AI Station's
   managed storage. Commit only manifests, checksums, small synthetic fixtures,
   and slim evaluation summaries.
8. If a selected checkpoint has unclear licensing, stop that capability at
   `configured_pending_smoke` and document the blocker; do not silently replace
   it with an unrelated model.
9. If product requirements conflict with the fail-closed contract, preserve the
   contract and surface the conflict for operator review.

## 17. Evidence and Primary References

Product capability patterns:

- [OpenAI: Introducing ChatGPT search](https://openai.com/index/introducing-chatgpt-search/)
- [OpenAI Help: Images in ChatGPT](https://help.openai.com/en/articles/11084440-im)
- [Anthropic: Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- [Anthropic: Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Anthropic: Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [xAI: Web Search](https://docs.x.ai/developers/tools/web-search)
- [xAI: Tools overview](https://docs.x.ai/developers/tools/overview)

Local implementation references:

- [SearXNG Search API](https://github.com/searxng/searxng/blob/master/docs/dev/search_api.rst)
- [Playwright Python documentation](https://playwright.dev/python/docs/library)
- [Trafilatura documentation](https://trafilatura.readthedocs.io/en/latest/)
- [MediaWiki Search API](https://www.mediawiki.org/wiki/API%3ASearch/en)
- [MediaWiki Imageinfo API](https://www.mediawiki.org/wiki/API%3AImageinfo/en)
- [Wikidata data access](https://www.wikidata.org/wiki/Help%3AData_access)
- [Qwen Image Edit model card](https://huggingface.co/Qwen/Qwen-Image-Edit)
- [ComfyUI ControlNet guide](https://docs.comfy.org/tutorials/controlnet/controlnet)
- [Grounding DINO official repository](https://github.com/IDEA-Research/GroundingDINO)
- [SAM 2 official repository](https://github.com/facebookresearch/sam2)
- [OpenCLIP official repository](https://github.com/mlfoundations/open_clip)
- [PaddleOCR multilingual recognition](https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html)
- [OpenCV official repository](https://github.com/opencv/opencv)

Sources were checked on 2026-08-28. Recheck versions, weights, and licenses at
implementation time because these projects and their model catalogs change.
