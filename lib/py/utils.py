import sys
from pathlib import Path
from typing import IO, Any

import yaml

_log_file: IO[str] | None = None


def set_log_file(f: IO[str] | None) -> None:
    """Mirror everything from info/warn/error/passthrough into f as well.

    Used by main.py to capture --deploy/--force output into build/deploy.log
    without changing what gets printed or where subprocess output streams to.
    """
    global _log_file
    _log_file = f


def _tee(stream: IO[str], text: str) -> None:
    stream.write(text)
    stream.flush()
    if _log_file is not None:
        _log_file.write(text)
        _log_file.flush()


def info(msg: str) -> None:
    _tee(sys.stdout, f"[INFO] {msg}\n")


def warn(msg: str) -> None:
    _tee(sys.stdout, f"[WARN] {msg}\n")


def error(msg: str) -> None:
    _tee(sys.stderr, f"[ERROR] {msg}\n")


def passthrough(text: str) -> None:
    """Forward one already-newline-terminated line of raw subprocess output."""
    _tee(sys.stdout, text)


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
