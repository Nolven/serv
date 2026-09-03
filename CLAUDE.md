# Project overview
Automated server deployment driven by a single `config.yaml` that the user edits
before running. Target is a machine on the local network. The only ingress is
WireGuard - nothing else is exposed.

# General guidelines
- Target platform: Debian 13 (trixie), systemd, x86_64
- Languages: Python 3.11+ and Bash. Pick by task: multi-step shell work - Bash
  script; YAML parsing, validation, templating - Python
- Every operation must be idempotent. Re-running a deploy on a converged host
  is a no-op and must exit 0
- Validate the entire config after generation

# Components are independent
No component may reference another component by name - not in code, not in
config, not in a dependency list.
If a task seems to require component A to know about component B, that is a
registry problem. Do not hardcode the name - ask.

# Project structure
- /
  - deploy.sh           # entry point: bootstrap venv, exec main.py "$@"
  - config.yaml         # user-edited, gitignored, 0600
- lib/
  - py/                 # python scripts
    - component_name.py # entry point for component configuration
    - main.py           # parse, validate, render, invoke each install.sh
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
`exec python main.py "$@"`. If it grows a component loop, the boundary has
slipped - that logic belongs in `main.py`.

# Code quality
- Python: type hints on all signatures; `ruff check` and `ruff format` clean
- Bash: `set -euo pipefail` at the top, quote all expansions, `shellcheck` clean
- Fail loudly with actionable messages: what failed, where, what to do next
- Output is `[INFO]` / `[WARN]` to stdout, `[ERROR]` to stderr, so that
  redirecting a dry-run plan does not swallow errors

# Running and testing
There is no unit test suite. Verify only by:
- `./deploy.sh --check` - validates config and exits
- `./deploy.sh --dry-run` - prints planned actions without executing
- `./deploy.sh --generate` - generates configs into /build folder
- `./deploy.sh --deploy` - generates configs into /build folder, installs components, and replaces default configs with generated after installation
- `shellcheck` on all `*.sh`, `ruff check` on all Python

Never run a real deploy against a live host to test a change.