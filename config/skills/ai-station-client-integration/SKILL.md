---
name: ai-station-client-integration
description: Connect OpenCode or any OpenAI-compatible application to AI Station, create/revoke project keys, select public models, set rate limits, and diagnose client authentication or routing. Use whenever a user asks for an SDK example, base URL, API key, project integration, OpenCode setup, or multi-project isolation. Always routes clients through LiteLLM :4000/v1 and never through llama.cpp or the host gateway directly.
compatibility: Requires a running AI Station LiteLLM gateway and the `ai` CLI; client examples use OpenAI-compatible SDK semantics.
---

# AI Station Client Integration

## Fixed contract

All clients use:

~~~text
Base URL: http://127.0.0.1:4000/v1
Auth:     Bearer project virtual key
Model:    canonical public model id
~~~

Never configure a client with `:8888`, `:8082`–`:8088`, GGUF paths, or
`local-*` backend aliases. Those are internal implementation details.

## Create least-privilege project access

Inspect public models, then create one key per application/use-case:

~~~bash
ai models list
ai projects create <project-id> --models <public-id-1,public-id-2> --rpm 60 --tpm 120000
ai projects show <project-id>
~~~

Store the resulting env file locally and never paste or commit its key.
Revoke a compromised or retired project with `ai projects revoke` rather than
rotating unrelated applications.

## Generic OpenAI-compatible client

~~~python
import os

from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4000/v1",
    api_key=os.environ["LLM_API_KEY"],
)
response = client.chat.completions.create(
    model="Qwen3-Coder-30B-A3B-Instruct-Q4",
    messages=[{"role": "user", "content": "Explain this function."}],
)
~~~

Import `os`; do not embed a real key in source. Use only models present in the
project allowlist.

## OpenCode

Use the repository renderer instead of hand-editing secret-bearing JSON:

~~~bash
ai opencode configure --dry-run
ai opencode configure
ai opencode doctor
ai opencode run /opt/ai-station
ai opencode acceptance
ai opencode use coder
ai opencode test --model coder
~~~

OpenCode runs inside WSL as the dedicated non-root `aidev` user; Windows
Manager launches that same runtime. One provider (`ai-station`) keeps all
picker models visible. Coder is default. Use `doctor` for read-only checks and
`acceptance` when a real edit-and-test proof is authorized. General and Ornith
are also tool-capable. DeepSeek is selectable for non-tool reasoning and
should not back build/debug agents.

## Diagnose client failures

1. `ai health` confirms LiteLLM and the current model without changing state.
2. Confirm the base URL is exactly `:4000/v1`.
3. Confirm the project key is not revoked and its allowlist contains the
   canonical public id.
4. Confirm the requested profile is installed/admissible; allow the gateway
   time to switch a cold heavy model.
5. Use bounded logs only after the contract checks above.

Report secrets as present/missing or redacted; never echo them.
