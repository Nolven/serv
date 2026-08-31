---
description: Scaffold and wire up a new component end to end
argument-hint: <component-name>
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

Component: $ARGUMENTS

Follow these in order. Do not skip step 1 even if you already know the service.

1. If `components/$ARGUMENTS/NOTES.md` does not exist, delegate to the
   `researcher` subagent to produce it. Wait for it.
2. Read NOTES.md and the config contract in CLAUDE.md. If NOTES.md has
   entries under "Open questions" that affect required config keys, ask me
   before continuing.
3. Create `components/$ARGUMENTS/`:
   - `install.sh` — idempotent, `set -euo pipefail`, exits non-zero on failure
   - `defaults.yaml` — every tunable, working defaults, `<REQUIRED>` for what
     the user must supply
   - the schema
   - `compose.yaml` if containerized
   - `files/` for templates and static files
   - `configure.py` only if shell cannot do the job cleanly
4. Register the schema. Do not add the component name to `deploy.sh` or to
   any branch in `main.py`.
5. Add the component to the user-facing example config, disabled, with only
   the keys the user must decide. No defaults duplicated.
6. Delegate to the `reviewer` subagent. Fix every BLOCKER it reports, then
   re-run it once.
7. Run `./deploy.sh --check` and `./deploy.sh --dry-run` with the component
   enabled. Both must pass.

Report: files created, `<REQUIRED>` values I now need to fill in, and any
reviewer findings you chose not to fix and why.