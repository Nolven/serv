from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from utils import info, write_yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "frigate"

RTSP_PORT = 554
REQUIRED_CAM_FIELDS = ("login", "password", "ip")


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    capabilities: dict[str, Any] = {
        "config_file": {
            "path": str(
                PurePosixPath(general["install"]) / "frigate" / "config" / "config.yaml"
            )
        }
    }

    subdomain = config.get("subdomain")
    if not subdomain:
        return capabilities
    missing = [k for k in ("name", "port") if k not in subdomain]
    if missing:
        raise ValueError(
            f"frigate.subdomain missing required key(s): {', '.join(missing)}"
        )
    capabilities["http_route"] = {
        "subdomain": subdomain["name"],
        "port": subdomain["port"],
    }
    return capabilities


def _stream_url(name: str, cam: dict[str, Any]) -> str:
    missing = [k for k in REQUIRED_CAM_FIELDS if not cam.get(k)]
    if missing:
        raise ValueError(
            f"frigate.cams.{name} missing required key(s): {', '.join(missing)}"
        )
    stream = cam.get("stream", "stream1")
    return f"rtsp://{cam['login']}:{cam['password']}@{cam['ip']}:{RTSP_PORT}/{stream}"


def _build_frigate_config(config: dict[str, Any]) -> dict[str, Any]:
    with open(DEFAULTS_DIR / "config.yaml", "r") as f:
        frigate_config: dict[str, Any] = yaml.safe_load(f) or {}

    cams: dict[str, Any] = config.get("cams", {})
    go2rtc_streams: dict[str, Any] = {}
    cameras: dict[str, Any] = {}

    for name in sorted(cams):
        cam = cams[name]
        url = _stream_url(name, cam)
        go2rtc_streams[name] = [url]

        camera_entry: dict[str, Any] = {
            "detect": {"enabled": cam.get("detect", False)},
            "ffmpeg": {"inputs": [{"path": url, "roles": ["audio", "record"]}]},
        }
        onvif_port = cam.get("onvif_port")
        if onvif_port is not None:
            camera_entry["onvif"] = {
                "host": cam["ip"],
                "port": onvif_port,
                "user": cam["login"],
                "password": cam["password"],
            }
        cameras[name] = camera_entry

    if go2rtc_streams:
        frigate_config["go2rtc"] = {"streams": go2rtc_streams}
    if cameras:
        frigate_config["cameras"] = cameras

    return frigate_config


def _build_compose(docker: dict[str, Any]) -> dict[str, Any]:
    with open(DEFAULTS_DIR / "compose.yaml", "r") as f:
        compose: dict[str, Any] = yaml.safe_load(f) or {}

    service = compose["services"]["frigate"]
    if "shm_size" in docker:
        service["shm_size"] = docker["shm_size"]
    if "volumes" in docker:
        service["volumes"] = [*service.get("volumes", []), *docker["volumes"]]
    if "ports" in docker:
        service["ports"] = docker["ports"]

    return compose


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    frigate_config = _build_frigate_config(config)
    config_text = write_yaml(out / "config" / "config.yaml", frigate_config, mode=0o600)
    info(f"Generated frigate config:\n{config_text}")

    compose = _build_compose(config.get("docker", {}))
    compose_text = write_yaml(out / "compose.yaml", compose, mode=0o644)
    info(f"Generated frigate compose:\n{compose_text}")
