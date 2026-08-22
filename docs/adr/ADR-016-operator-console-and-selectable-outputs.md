# ADR-016: Operator Console, Selectable Outputs, Graphify Map

- Status: Accepted
- Date: 2026-08-22

## Context

Operators asked for two product gaps on top of the existing station:

1. Generated artifacts (ComfyUI media and Graphify graphs) always landed
   in fixed `/srv/ai-station/runtime/...` paths. The destination was not
   operator-selectable.
2. A "centralised manager platform" that could see the whole system,
   including a graphical Graphify view so humans and coding assistants
   can evaluate module relationships.

The station already has a control plane: `ai` (`scripts/ai`) and the
Windows Manager (`AI Station/AI Station Manager.ps1`), which only
invokes that CLI. Open WebUI, LiteLLM Admin, and experimental ComfyUI
are workload UIs, not operator consoles. A second privileged web admin
would overlap that control plane and add a new loopback API that can
start GPU providers.

Graphify 0.9.47 already emits a self-contained force graph
(`graphify export html` → `graph.html`) and a collapsible tree
(`graphify tree` → `GRAPH_TREE.html`). Those artifacts were not wired
through `ai` or the Manager.

## Options considered

1. Build a new web administration product (start/stop, models, keys,
   media, Graphify) on its own port.
2. Keep `ai` + Windows Manager as the only privileged console; add
   operator-selectable output roots and a loopback Graphify map that
   wraps the upstream HTML (read-only links to existing UIs).
3. Teach operators to open raw `graph.json` and hard-coded `/srv` paths.

## Evidence

- Windows Manager already covers lifecycle, models, API keys, OpenCode,
  Graphify extract/status, tests, backup, and ComfyUI start/stop
  (see `tests/test_windows_manager_contract.py`).
- ADR-012 classified Graphify as an optional code graph, not a second
  retrieval store. Upstream HTML export needs no GPU and no new engine.
- Compose already bind-mounts ComfyUI output; substituting
  `AI_STATION_COMFYUI_OUTPUT` changes the host directory without a new
  container. Restart of the experimental overlay is required for the
  mount to move.
- A privileged HTTP start/stop API would duplicate the admission
  controller (ADR-004) and expand the threat model.

## Decision

Adopt option 2.

- Classification: **production default** for `ai` / Windows Manager;
  Graphify map remains the **optional profile** from ADR-012.
- Output roots live in `/srv/ai-station/runtime/operator-prefs.json`
  (runtime state, not git). Commands: `ai output show|set|open`.
  Kinds: `media` (ComfyUI bind), `graphify` (extract parent), `export`
  (Windows-visible copy target under `/mnt/c/Users/...` or runtime).
- `media` and `graphify` paths must stay under
  `/srv/ai-station/runtime`. Compose reads
  `runtime/compose-operator.env` when present.
- `ai graphify view` writes upstream `graph.html` / `GRAPH_TREE.html`
  plus a station map `index.html`, then serves that directory on
  `127.0.0.1:4174` (stop with `ai graphify view --stop`).
- Windows Manager gains map + folder actions; it still calls `ai` with
  typed arguments. No new engine, no LAN bind, no GPU at view time.
- Coding assistants keep using `ai graphify query|path|explain` against
  `graph.json` (ADR-012). The HTML map is for human evaluation.

## Consequences

Operators pick where media and graphs land. Humans open one loopback
page to see Graphify and jump to Open WebUI / LiteLLM / ComfyUI.
Start, stop, and model load stay on `ai` and the Manager so admission
policy is not reimplemented in a browser.

## Risks

- Moving the ComfyUI bind while the overlay is running has no effect
  until restart. Mitigation: `ai output set media` prints that warning.
- `GRAPH_TREE.html` loads D3 from a CDN; `graph.html` is self-contained.
  Mitigation: document that the tree tab needs outbound HTTPS; the
  force graph does not.
- Stale graphs after refactors. Mitigation: extract remains explicit;
  view regenerates HTML from the current `graph.json`.

## Rollback

~~~bash
ai graphify view --stop
ai output set media /srv/ai-station/runtime/comfyui/output
ai output set graphify /srv/ai-station/runtime/graphify/ai-station
rm -f /srv/ai-station/runtime/operator-prefs.json
rm -f /srv/ai-station/runtime/compose-operator.env
~~~

Restart ComfyUI if it was running so the default bind returns. Remove
this ADR from `docs/adr/README.md` only if the feature is deleted.

## Acceptance criteria

1. `ai output set media` rejects paths outside `/srv/ai-station/runtime`
   and writes `compose-operator.env` without printing secrets.
2. `ai graphify extract --out DIR` writes `DIR/graphify-out/graph.json`.
3. `ai graphify view --no-serve` writes `index.html` and `graph.html`
   next to the current graph; `--stop` leaves no listener on `:4174`.
4. Windows Manager menu numbers stay unique and sequential; new actions
   call `ai graphify view` / `ai output` with typed arguments.
5. No second privileged HTTP API for start/stop or model load.
