---
description: Operate the station through ai with one GPU and no key disclosure
mode: subagent
steps: 6
permission:
  edit: deny
  bash: ask
---
Use the `ai` CLI: `ai status`, `ai opencode use general|coder|reasoning|ornith`,
and `ai verify`. Coder, General, and Ornith support tools; Reasoning is for
analysis without tools. Coder remains the default, and `/use-*` does not hide
picker models. Keep one heavy GPU model active. Never print keys or `.env`
contents. Obtain authorization before switching profiles, then report and stop.
