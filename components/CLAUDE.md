# Component contract

A component owns exactly one folder under `components/`. It must provide:

- `install.sh` — idempotent, `set -euo pipefail`, takes a rendered config JSON
  path as `$1`, exits non-zero on failure
- `defaults.yaml` — every tunable the component supports, at a working default
- `schema.py` — this component's config section, registered in `lib/schema.py`

Optional: `compose.yaml` (if containerized), `configure.py` (only when shell
cannot do the job cleanly), `files/`, `NOTES.md`.

`install.sh` is the only thing `main.py` calls. `configure.py` is invoked by
`install.sh`, never the reverse. Never hardcode a component name in `deploy.sh`
or add a per-component branch to `main.py`; if the generic path cannot handle
something, that is a signal the generic path needs extending.

Adding a component means: the folder with the files above, the
schema registered in `lib/schema.py`, and a disabled block in
`config.example.yaml`.

# Independence

No component references another by name. Anything a component offers to others
goes into the service registry via `lib/registry.py`; anything it consumes is
discovered from `/run/deploy/services.d/`, never assumed. A component must
behave correctly when the registry is empty.

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

A value the user must supply is written `<REQUIRED>` in `defaults.yaml`:

    apex_domain: <REQUIRED>

`main.py` fails validation if any `<REQUIRED>` survives the merge, naming the
full key path. Never render a file containing the sentinel. Optional values are
omitted from `config.yaml` entirely — not set to null or an empty string.

# Single source of truth

A fact the user states once is never restated. `general.fileserver_root` exists
in exactly one place; components reference it as `${general.fileserver_root}`,
resolved by `main.py` before rendering. Writing the same literal value twice in
`config.example.yaml` is a bug.

# What does not belong in config.yaml

Container volumes, port mappings, image tags, tmpfs sizes, internal service
ports, retention tuning, detector thresholds. These live in `defaults.yaml` or
`compose.yaml`. The exception is a port the user genuinely chooses — SSH,
WireGuard listen port.

# Idempotency

Every `install.sh` must be a no-op on a converged host. Specifically:

- Guard key and certificate generation on the file already existing
- Never `>>` into a config file; render the whole file and compare
- `mkdir -p`, and check before `useradd`
- Do not overwrite files the service itself rewrites at runtime — `NOTES.md`
  lists these per component
- `systemctl enable --now` is safe to repeat; a bare `systemctl start` in a
  loop is not what you want

# Secrets

Credentials never appear in `config.example.yaml`, not even as realistic-looking
placeholders. Generated keys go to `secrets/`, mode 0600. `config.yaml` is 0600
and gitignored.

Never echo a credential to stdout, pass one as a command-line argument where it
lands in `ps` output, or write one into a file outside `secrets/`. Use a file or
stdin to hand secrets to a program.

# Code quality

- Bash: `set -euo pipefail`, quote every expansion, `shellcheck` clean, source
  `lib/common.sh` for logging rather than raw `echo`
- Python: type hints on all signatures, `ruff check` and `ruff format` clean
- `[INFO]` and `[WARN]` to stdout, `[ERROR]` to stderr
- Error messages name the component, the file, and the fix