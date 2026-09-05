import sys
from pathlib import Path
from typing import Any

import yaml


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def write_yaml(path: Path, data: dict[str, Any], mode: int = 0o644) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    with open(path, "w", newline="\n") as f:
        f.write(text)
    path.chmod(mode)
    return text


def write_text(path: Path, text: str, mode: int = 0o644) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)
    path.chmod(mode)
    return text
