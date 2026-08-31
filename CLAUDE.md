# Project overview
Automated server deployment driven by a single `config.yaml` that the user edits
before running. Target is a machine on the local network. The only ingress is
WireGuard — nothing else is exposed.

# General guidelines
- Target platform: Debian 13 (trixie), systemd, x86_64
- Languages: Python 3.11+ and Bash. Pick by task: multi-step shell work → Bash
  script; YAML parsing, validation, templating → Python
- Every operation must be idempotent. Re-running a deploy on a converged host
  is a no-op and must exit 0
- Validate the whole config before mutating anything. No partial application

# Project structure
- A single folder per component
- All component's folders should be under the single Component folder; which itself is located in root folder 
- Root folder should contain the main config, entry point for the configuration start and necessary folders
- If component is containerized compose.yaml should be present

# Code quality
- For python add type hints wherever possible
- 