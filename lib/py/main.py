import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from utils import error, info, warn, write_yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        error(
            f"{CONFIG_PATH} not found. Copy config.yaml.example to config.yaml and edit it."
        )
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        error(f"{CONFIG_PATH} did not parse to a mapping")
        sys.exit(1)
    return data


def validate_config(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    general = data.get("general")
    if not isinstance(general, dict):
        errors.append("missing top-level 'general' section")
        general = {}
    for key in ("hostname", "build_path", "install"):
        if key not in general:
            errors.append(f"general.{key} is required")

    components = data.get("components")
    if components is None:
        components = []
    elif not isinstance(components, list):
        errors.append("'components' must be a list")
        components = []
    for name in components:
        if name not in data:
            errors.append(
                f"component '{name}' is listed under components: but has no '{name}:' section"
            )

    return errors


def load_component_module(name: str) -> ModuleType:
    module_name = name.replace("-", "_")
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        error(
            f"components: lists '{name}' but lib/py/{module_name}.py does not exist ({exc})"
        )
        sys.exit(1)


def build_registry(
    enabled: list[str], data: dict[str, Any], general: dict[str, Any]
) -> tuple[dict[str, ModuleType], dict[str, Any]]:
    modules: dict[str, ModuleType] = {}
    registry: dict[str, Any] = {}
    for name in enabled:
        module = load_component_module(name)
        modules[name] = module
        declare = getattr(module, "declare", None)
        if declare is not None:
            try:
                capabilities = declare(data[name], general)
            except ValueError as exc:
                error(f"{name}: {exc}")
                sys.exit(1)
            if capabilities:
                registry[name] = capabilities
    return modules, registry


def ensure_bind_mounts(compose_path: Path, dest: Path) -> None:
    """Create empty host directories referenced by relative compose volumes.

    Rendered output only contains files a component generates (e.g. config/);
    persistent-but-empty dirs (e.g. storage/) are never rendered, so deploy
    must create them itself, generically, from the compose file alone.
    """
    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f) or {}

    for service in compose.get("services", {}).values():
        for volume in service.get("volumes", []) or []:
            if isinstance(volume, str):
                host_path = volume.split(":", 1)[0]
            else:
                continue
            if not host_path.startswith("./"):
                continue
            (dest / host_path[2:]).mkdir(parents=True, exist_ok=True)


def deploy_component(name: str, src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

    script = ROOT / "lib" / "sh" / f"{name}.sh"
    compose_path = dest / "compose.yaml"
    ran_something = False

    if script.exists():
        info(f"Running lib/sh/{name}.sh")
        subprocess.run(["bash", str(script), str(dest)], check=True, cwd=ROOT)
        ran_something = True

    if compose_path.exists():
        ensure_bind_mounts(compose_path, dest)
        info(f"docker compose up -d ({dest})")
        subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "up", "-d"],
            check=True,
            cwd=dest,
        )
        ran_something = True

    if not ran_something:
        warn(
            f"{name} has no lib/sh/{name}.sh and no rendered compose.yaml; nothing to run"
        )


def sync_common_config_folder(
    general: dict[str, Any], registry: dict[str, Any]
) -> None:
    """Symlink every declared config_file capability into one folder.

    Runs after deploy_component() so targets already exist on disk; targets
    are absolute host paths declared by each component, never build/ paths.
    """
    common = general.get("common_config_folder") or {}
    if not common.get("enable", False):
        return

    folder_path = common.get("path")
    if not folder_path:
        raise ValueError(
            "general.common_config_folder.path is required when enable is true"
        )

    folder = Path(folder_path)
    folder.mkdir(parents=True, exist_ok=True)

    for name in sorted(registry):
        config_file = registry[name].get("config_file")
        if not config_file:
            continue
        target = Path(config_file["path"])
        link = folder / name

        if link.is_symlink():
            if link.readlink() == target:
                continue
            link.unlink()
        elif link.exists():
            raise ValueError(
                f"{link} already exists and is not a symlink - refusing to overwrite"
            )

        link.symlink_to(target)
        info(f"Linked {link} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Config-driven server deploy orchestrator"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="validate config and exit")
    group.add_argument(
        "--dry-run", action="store_true", help="print planned actions without executing"
    )
    group.add_argument(
        "--generate", action="store_true", help="render component configs into build/"
    )
    group.add_argument(
        "--deploy",
        action="store_true",
        help="generate, install, and (re)start components",
    )
    args = parser.parse_args()

    data = load_config()
    errors = validate_config(data)
    if errors:
        for msg in errors:
            error(msg)
        sys.exit(1)

    general: dict[str, Any] = data["general"]
    enabled: list[str] = data.get("components") or []
    build_root = ROOT / general["build_path"]

    modules, registry = build_registry(enabled, data, general)
    info(f"Enabled components: {', '.join(enabled) if enabled else '(none)'}")

    if args.check:
        info("Config OK")
        return

    if args.dry_run:
        install_root = Path(general["install"])
        for name in enabled:
            out = build_root / name
            info(f"[dry-run] would render {name} -> {out}")
            if getattr(modules[name], "render", None) is None:
                continue
            script = ROOT / "lib" / "sh" / f"{name}.sh"
            compose_source = ROOT / "components" / name / "compose.yaml"
            if script.exists():
                info(
                    f"[dry-run] would run lib/sh/{name}.sh against {install_root / name}"
                )
            if compose_source.exists():
                info(f"[dry-run] would docker compose up -d in {install_root / name}")
            if not script.exists() and not compose_source.exists():
                info(f"[dry-run] {name} has no lib/sh/{name}.sh or compose.yaml source")
        info(f"[dry-run] would write {build_root / 'registry.yaml'}")

        common = general.get("common_config_folder") or {}
        if common.get("enable", False):
            folder_path = common.get("path")
            if not folder_path:
                info(
                    "[dry-run] general.common_config_folder.enable is true but "
                    "path is missing"
                )
            else:
                for name in sorted(registry):
                    config_file = registry[name].get("config_file")
                    if not config_file:
                        continue
                    info(
                        f"[dry-run] would link {Path(folder_path) / name} -> "
                        f"{config_file['path']}"
                    )
        return

    for name in enabled:
        render = getattr(modules[name], "render", None)
        if render is None:
            warn(f"{name} has no render(); nothing generated")
            continue
        out = build_root / name
        try:
            render(data[name], general, registry, out)
        except ValueError as exc:
            error(f"{name}: {exc}")
            sys.exit(1)
        info(f"Rendered {name} -> {out}")

    registry_text = write_yaml(build_root / "registry.yaml", registry, mode=0o644)
    info(f"Generated registry.yaml:\n{registry_text}")

    if args.generate:
        return

    install_root = Path(general["install"])
    for name in enabled:
        src = build_root / name
        if not src.exists():
            continue
        deploy_component(name, src, install_root / name)

    try:
        sync_common_config_folder(general, registry)
    except ValueError as exc:
        error(f"common_config_folder: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
