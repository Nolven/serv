---
description: Wire components/<NAME> into the deploy pipeline - research it, verify its config.yaml section, then write its declare/render module and deploy script
argument-hint: <component-name>
---

# link_component $1

Goal: take a component that already has files under `components/$1/` and wire it
into the pipeline described in the root `CLAUDE.md` - a config.yaml section, a
Python module (`lib/py/components/$1.py`) implementing the `declare`/`render`
contract, and whatever deployment step it needs - without ever writing another
component's name as a literal in source or config.

Follow these steps in order. Do not skip the question step - guessing at
unclear config wastes a deploy cycle on a real host.

## 0. Preconditions

Stop and ask before doing anything if any of these hold:

- `components/$1/` does not exist. Do not create a component from scratch under
  this command.
- `lib/py/$1.py` or `lib/sh/$1.sh` already exists. Use
  AskUserQuestion - do not overwrite or silently extend.
- `$1` contains characters invalid in a Python module name. The config key is
  authoritative; the module name is the config key with hyphens normalized to
  underscores. Confirm the mapping with the user rather than inventing it.

Re-read the root `CLAUDE.md` and `components/CLAUDE.md` before writing
anything. They are the source of truth for structure, the capability
vocabulary, and the read-only-defaults rule.

## 1. Research the component

Read every file under `components/$1/` - `compose.yaml`, any config file,
everything in `files/`. Note:
- what image/service it runs and what version is pinned
- every setting the file format supports, versus the subset already stubbed in
  the component's own defaults
- volumes, ports, and env vars the compose file expects
- anything that must be generated per-host (keys, salts, paths under `install:`)

If the component wraps known third-party software, use WebSearch/WebFetch to
confirm what its config format requires versus defaults, and whether the pinned
version matches current upstream docs. Cite findings in code comments only when
they explain a WHY (e.g. "must be >=X for Y reason"), per the project's
no-narration-comments rule.

## 2. Classify what it exchanges with the rest of the system

Decide, and state to the user, which of these `$1` is:

- **Provider** - declares capabilities others consume (an HTTP route, a DNS
  record, a mount). Populates its `declare()` return.
- **Consumer** - reads the registry at render time (a reverse proxy, a DNS
  updater). Its `render()` iterates the registry and treats every key as an
  opaque name.
- **Both**, or **neither** (self-contained).

A consumer must never branch on a specific registry key. If `$1` appears to
need behaviour specific to one other component, that is the registry problem
CLAUDE.md calls out - stop and ask.

Only capability keys listed in root `CLAUDE.md` may be used. If `$1` needs
something outside that vocabulary, propose the addition to the user as a
CLAUDE.md change first; do not invent a key inline.

## 3. Verify the config.yaml section

- Check whether `/config.yaml` has a top-level `$1:` section (it may exist as
  an uncommented stub).
- Compare its keys against what step 1 found the component actually supports.
  Flag to the user, do not silently fix:
  - required settings missing from the stub (credentials, host paths)
  - settings present that the component does not recognize
  - the same value defined in two places, here or in `general:`
  - any value that duplicates something derivable from another key
  - any hardcoded reference to another component's name, port, or path
- Confirm `$1` is listed under `components:`. Do not force-enable it.
- Update `config.yaml.example` with the same section, using placeholder values
  and a comment for every setting the user must supply. This is part of the
  definition of done, not optional - `config.yaml` is gitignored, so the
  example is the only committed documentation of the schema.

## 4. Ask questions if anything is unclear

Use AskUserQuestion, not assumptions, for anything steps 1-3 left open:

- ambiguous or missing defaults in `components/$1/`
- whether a setting belongs in `general:` or in `$1:` - anything two components
  could plausibly need belongs in `general:`
- how a cross-cutting concern (subdomain, port, auth, shared API token) is
  exposed without naming another component
- destination path under the install folder for anything non-obvious
- whether a secret should be rendered into `build/$1/` at all, or referenced
  from an env file created at deploy time

Do not proceed with open questions still unanswered.

## 5. Write `lib/py/components/$1.py`

Two functions, both required. main.py derives the component's registry key from
the module name; the module never names itself or any other component.

```py
def declare(config: dict, general: dict) -> dict:
    """Pure - no filesystem access, no network, no mutation of the arguments.

    config:  this component's config.yaml section, defaults already merged
    general: the general: section plus keys injected by main.py

    Returns capability declarations using only the vocabulary in root
    CLAUDE.md. Return {} if this component provides nothing.
    """


def render(config: dict, general: dict, registry: Registry, out: Path) -> None:
    """Writes this component's generated files into `out`.

    registry: {component_name: declared_capabilities} for every enabled
              component, including this one. Keys are opaque.
    out:      the directory to write into. Supplied by main.py - do not
              compute build/ paths here, and never write outside `out`.
    """
```

Requirements:

- merge the component's defaults from `components/$1/` with the user's
  config.yaml overrides; `components/$1/` is read-only
- rendering must be deterministic: sorted mapping keys, no timestamps, no
  UUIDs, no unseeded randomness, the project's shared YAML dumper settings, LF
  line endings, explicit file modes
- files containing secrets are written 0600
- type hints on every signature; `ruff check` and `ruff format` clean
- fail loudly with actionable messages - what failed, where, what to do next

## 6. Write the deployment step

Refer to root `CLAUDE.md`.

- If `components/$1/compose.yaml` exists and the component needs nothing beyond
  copying `build/$1/` into place and `docker compose up -d`, no script is
  needed. Confirm with the user before adding one anyway.
- If it needs bash-side work beyond compose - permissions, directory layout, a
  non-containerized install - add `lib/sh/$1.sh`:
  - `set -euo pipefail`, quote all expansions, `shellcheck` clean
  - idempotent; safe to re-run on a converged host, exits 0
  - `[INFO]`/`[WARN]` to stdout, `[ERROR]` to stderr
  - must not reference any other component by name

## 7. Verify

- `./deploy.sh --check` - passes, and the registry validates with `$1` enabled
- `./deploy.sh --check` with `$1` commented out of `components:` - still passes,
  and nothing in `build/` or the plan references it
- `./deploy.sh --dry-run`
- `./deploy.sh --generate`, then inspect `build/$1/` against what step 1 said
  the component expects
- run `./deploy.sh --generate` a second time and confirm `build/$1/` is
  byte-identical. If it is not, that is a determinism bug in `render()` - fix
  it, do not paper over it
- confirm no file under `build/$1/` contains a hardcoded path outside
  `general.install`, and that files holding credentials are 0600
- `ruff check lib/py/components/$1.py`
- `shellcheck lib/sh/$1.sh` if created
- Do NOT run `./deploy.sh --deploy` against the live host.

## 8. Report

State what was added or changed, which capabilities `$1` now declares and
consumes, and every open question the user must resolve before a real deploy -
real credentials, camera IPs, API tokens, host paths.