---
description: Validate config and dry-run the full deploy
argument-hint: "[component name, or blank for all]"
allowed-tools: Read, Glob, Grep, Bash
---

Validate the deployment without touching a host.

1. `./deploy.sh --check` — config validates, no `<REQUIRED>` survives.
2. `./deploy.sh --dry-run` — read the planned actions and flag anything that
   is not obviously idempotent.
3. `shellcheck` on all `*.sh`, `ruff check` and `ruff format --check` on all
   Python.
4. For each enabled component, confirm nothing references another component
   by name.

If $ARGUMENTS names a component, scope 3 and 4 to it. Report failures with
file and line. Do not fix anything unless I ask.