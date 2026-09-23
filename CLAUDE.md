# Project overview
Automated server deployment driven by a single `config.yaml` that the user edits
before running. Target is a machine on the local network. WireGuard is the
default ingress for every proxied/internal service - the firewall trusts the
wg0 interface entirely, so nothing behind it needs its own opening. SSH (the
`ssh` component) is kept reachable directly from the WAN too, like WireGuard
itself - both declare a `firewall_rule` like any other component, nothing
hardcoded in `firewall.py`. This targets a home server behind a router with
only default ports forwarded, so the exposure is considered acceptable.

`caddy` is the one exception to "wg0-only by default": when `caddy.wan_enable`
is true it declares a `firewall_rule` for 443/tcp, and any individual
`http_route` consumer can opt itself into that WAN-facing listener with
`wan: true` on its own subdomain config (e.g. `pihole.subdomain.wan: true`).
Everything else stays wg0-only - caddy `bind`s each site block that isn't
opted in to `general.host_ip` so it's unreachable even if 443 is open. Opting
a route in without `caddy.wan_enable` set is a validation error.

Every subdomain this host serves is published by declaring a capability that
carries one - `http_route` (proxied to a port) or `static_site` (served off
disk). Declaring one is the *only* wiring a component needs: both the reverse
proxy's site blocks and the index page at the apex domain are generated from
those declarations, so a new subdomain appears on the index automatically and
disappearing from `components:` removes it from both. Never maintain a list of
services anywhere - if a subdomain has to be named a second time to show up
somewhere, that is the registry problem below, not a missing entry.

# General guidelines
- Target platform: Debian 13 (trixie), systemd, x86_64
- Languages: Python 3.11+ and Bash. Pick by task: multi-step shell work - Bash
  script; YAML parsing, validation, templating - Python
- Every operation must be idempotent. Re-running a --deploy on a converged host
  is a no-op and must exit 0
- Validate the entire config after generation

# Components are independent
No component may reference another component by name - not in code, not in
config, not in a dependency list.
If a task seems to require component A to know about component B, that is a
registry problem. Do not hardcode the name - ask.

## Capability registry
Components exchange capabilities only through a registry built by `main.py`,
never by naming each other directly.

- A component module may define `declare(config: dict, general: dict) -> dict`
  (pure, no I/O). It returns capability declarations keyed by capability type,
  using only the vocabulary below. Return `{}` if it provides nothing.
- `main.py` calls `declare()` for every enabled component before rendering
  any of them, and assembles `registry: dict[str, dict]` keyed by the
  component's config.yaml section name -> that component's `declare()` return.
- A component module may define
  `render(config: dict, general: dict, registry: dict, out: Path) -> None`,
  writing generated files into `out`. A consumer reads `registry` and must
  treat every component-name key as opaque - never branch on a literal
  component name.
- Capability vocabulary (extend this list before a component needs a new
  shape - do not invent a key inline):
  - `http_route: {subdomain: str, port: int, redir?: str, wan?: bool}` - an
    HTTP service a reverse proxy may expose. `redir`, if present, is a path
    (e.g. `/admin`) that bare `/` should redirect to. `wan`, if true, opts
    this specific route into being reachable from outside the WireGuard
    tunnel (via caddy's WAN-facing listener) - omit/false keeps it wg0-only,
    which is the default for everything. Consumed only by `caddy`; setting it
    true requires `caddy.wan_enable: true` or rendering fails. Every declared
    `subdomain` is also listed on the apex index page - nothing extra to
    declare for that, and nothing that opts out of it.
  - `static_site: {root: str, subdomain?: str, browsable?: bool, wan?: bool,
    cache?: bool}` -
    a directory of files a reverse proxy may serve directly off disk, with no
    process behind it. `root` is the absolute on-host path. `subdomain`, if
    present, is served at `<subdomain>.<apex_domain>`; omit it to be served at
    the apex domain itself (at most one component may do so). `browsable`
    turns on a directory index. `cache` defaults true; set it false for
    content regenerated on every deploy, so the proxy tells browsers to
    revalidate instead of serving a stale copy (`file_server` sends no
    `Cache-Control` of its own, so heuristic caching applies otherwise).
    `wan` behaves exactly as in `http_route`.
    Consumed by `caddy`, which treats it interchangeably with `http_route`,
    and - like `http_route` - listed on the apex index page whenever it
    carries a `subdomain`. Any consumer wanting the full list of published
    addresses must therefore read both capability types, never just one:
    reading only `http_route` silently omits every static site. A consumer
    building that list skips entries with no `subdomain` (those are the apex
    itself).
  - `firewall_rule: {proto: "tcp" | "udp", port: int}` - a port that must be
    reachable from outside the host, on the public interface, independent of
    the WireGuard tunnel. The firewall trusts the wg0 interface entirely, so
    only declare this for something that must work before/outside the
    tunnel exists (e.g. WireGuard's own listen port) - not for services only
    reachable over the tunnel.
  - `config_file: {path: str}` - the absolute, on-host path to a config file
    worth exposing for convenient inspection/editing. `path` is the file's
    real final location (e.g. under `general.install/<name>/...`, or a fixed
    system path like `/etc/wireguard/wg0.conf`) - never a `build/` path.
    Consumed only by `main.py`'s `general.common_config_folder` step, which
    symlinks it in; not every component needs to declare one (skip it for
    anything with no single config worth surfacing).
  - `dns_resolver: {address: str}` - a DNS resolver running on this host,
    reachable by WireGuard peers at `address` (an IP, typically
    `general.host_ip`). Consumed by `wg-easy` as the default DNS pushed to
    new clients when `wg-easy.dns` isn't set explicitly; every declared
    address is used, in registry-key order.
  - `post_deploy_note: {message: str}` - a static, human-readable reminder
    about something manual the user still needs to do that isn't otherwise
    derivable from the registry (e.g. a one-time generated password to go
    retrieve). `message` must be self-contained (no other capability data
    needed to make sense of it). Consumed only by `main.py`, which prints
    every declared note once at the end of a `--deploy`/`--force` run -
    never during `--generate`/`--check`/`--dry-run`, since nothing has
    actually run yet. Don't declare this for anything derivable from other
    capabilities already in the registry (e.g. WAN port-forwarding reminders
    come from `firewall_rule` generically, not from a note).

# Project structure
- /
  - deploy.sh           # entry point: bootstrap venv, exec main.py "$@"
  - config.yaml         # user-edited, gitignored, 0600
- lib/
  - py/                  # python scripts
    - component_name.py  # entry point for 1st component configuration; should be 1-to-1 name as in /config.yaml
    - component_name2.py # entry point for 2nd component configuration; should be 1-to-1 name as in /config.yaml
    - main.py            # parse, validate, render, invoke each component_
    - util python scripts
  - sh/
    - util bash scripts
    - component_name.sh # necessary for component bash script
- build/                # generated configs
- components/
  - <name>/
    - files/            # any non-config files requied by component
    - compose.yaml      # if containerized
    - any additional configurational files required by the component

`deploy.sh` stays dumb: create/activate the venv, install requirements,
`exec python lib/py/main.py "$@"`. If it grows a component loop, the boundary has
slipped - that logic belongs in `main.py`.

# Code quality
- Python: type hints on all signatures; `ruff check` and `ruff format` clean
- Bash: `set -euo pipefail` at the top, quote all expansions, `shellcheck` clean
- Fail loudly with actionable messages: what failed, where, what to do next
- Output is `[INFO]` / `[WARN]` to stdout, `[ERROR]` to stderr, so that
  redirecting a dry-run plan does not swallow errors

# Testing
There is no unit test suite. Verify only by:
- `./deploy.sh --check` - validates config and exits
- `./deploy.sh --dry-run` - prints planned actions without executing
- `./deploy.sh --generate` - generates configs into /build folder
- `shellcheck` on all `*.sh`, `ruff check` on all Python

Never run a real deploy against a live host to test a change.

# Deploying
For the actual deploing `./deploy.sh --deploy` shall be used.
Deploy consists of 3 stages:
- Generate configs into /build/component_name/
- Create file structure in the `/config.yaml:general.install` folder
- Move necessary configs there (for example for docker compose)
- Execute docker compose where needed; execute installatation scripts otherwise
- Replace configs generated upon installation where necessary (for example frigate/config/config.yaml will be replaced by the one generated by deployment)
- Restart app/container if necessary

`--deploy` is intentionally conservative: each component's own idempotency
check (a `cmp` against the installed file, docker compose's own diff, etc.)
decides whether anything needs restarting. `--force` is the same pipeline but
skips those checks - every component's service is restarted / its container
is recreated unconditionally, even if nothing detectably changed. This exists
because not every component has (or can have) a reliable "did this change"
signal - e.g. a docker-compose component whose config lives in a bind-mounted
file (not `environment:`) has no way for `docker compose up -d` to notice the
file's content changed, so a plain `--deploy` silently no-ops there.

`--force` optionally takes a component name (1-to-1 with its `config.yaml`
section, e.g. `--force wg-easy`), scoping the unconditional restart/recreate
to that component alone. Every *other* stage of the run is unaffected by the
scoping: the registry is still built from every enabled component's
`declare()`, every enabled component is still rendered into `build/` and run
through `deploy_component()`, and `common_config_folder`/post-deploy-note
handling still sees the full registry - only the named component's own
idempotency check is bypassed, so anything a bystander component needs from
the registry (e.g. a `caddy` route referencing the forced component's port)
stays correct. `--force` with no name forces every enabled component, same as
before.

`--force` is not "wipe and redeploy from scratch" - it must not be destructive
to a component's own persistent runtime state (docker volumes, generated
keys/peers, etc.), only to the *rendered config* that state is running under.
A docker-compose component's bind-mounted state directories (e.g. wg-easy's
`./etc_wireguard`) survive `docker compose up -d --force-recreate` untouched
by default, so most components need no special handling here. Before adding
`--force` handling to a new component, check whether it has persistent state
a blind recreate/restart *would* lose (e.g. a component that renders its
runtime state file directly into `build/`, rather than leaving it in an
untouched bind mount) - if so, that component's own script needs to update
that state in place instead of overwriting it, the way a stateful component
must.