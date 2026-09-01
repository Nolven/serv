# Component contract

A component owns exactly one folder under `components/`. It must provide:

- `install.sh` — idempotent, `set -euo pipefail`, takes a rendered config JSON
  path as `$1`, exits non-zero on failure
- `defaults.yaml` — every tunable the component supports, at a working default

Optional: 
- `compose.yaml` # if containerized
- `configure.py` # only when shell cannot do the job cleanly
- `files/`   # if required by component
- `NOTES.md` # researcher output

`install.sh` is the only thing `main.py` calls. `configure.py` is invoked by
`install.sh`, never the reverse. Never hardcode a component name in `deploy.sh`
or add a per-component branch to `main.py`; if the generic path cannot handle
something, that is a signal the generic path needs extending.

Adding a component means: the folder with the files above and a block in `config.example.yaml`.

# Config layers

Merged in this order:

1. `components/<name>/defaults.yaml` — everything tunable, working defaults,
   commented like the upstream docs. Not user-facing.
2. `config.yaml` — only what the user must decide: identity, secrets, hardware,
   per-site facts. Never repeats a default.
3. Derived values — computed by `main.py` from layers 1 and 2 (go2rtc stream
   URLs built from `cams[]`, for instance). Never hand-written anywhere.

Maps merge deeply. Lists replace wholesale — a user list replaces the default
list entirely and is never appended to or element-merged.

Per-item defaults follow the same rule: a per-camera key overrides
`default_settings` by deep merge, and anything the user omits comes from
`default_settings`.

# Required-value sentinel

A value the user must supply is written `<REQUIRED>` in component's configs:

example: apex_domain: <REQUIRED>

`main.py` fails validation if any `<REQUIRED>` survives the merge, naming the
full key path. Never render a file containing the sentinel. Optional values are
omitted from `config.yaml` entirely — not set to null or an empty string.

# Single source of truth

A fact the user states once is never restated. `general.fileserver_root` exists
in exactly one place; components reference it as `${general.fileserver_root}`,
resolved by `main.py` before rendering. Writing the same literal value twice in
`config.example.yaml` is a bug.
