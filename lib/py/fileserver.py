import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from utils import info, write_text, write_yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "fileserver"

# where general.fileserver_root appears inside the sftpgo container
CONTAINER_ROOT = PurePosixPath("/srv/data")

# the only sftpgo paths reachable from outside the tunnel: the public share
# pages and the css/js/fonts they load. Login, admin UI and REST API all stay
# wg0-only
PUBLIC_PATHS = ["/web/client/pubshares/*", "/static/*"]

# everything on the outbox except overwrite: an upload link must never be able
# to replace a file that's already there
OUTBOX_PERMISSIONS = ["list", "download", "upload", "create_dirs", "delete", "rename"]

# sftpgo's own SFTP/WebDAV/FTP servers are off; denying them per account too
# keeps a later config slip from opening them
DENIED_PROTOCOLS = ["SSH", "FTP", "DAV"]

_LINUX_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_SHARE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_SIZE = re.compile(r"^(\d+)([KMGT]?)$", re.IGNORECASE)
_SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def _part(config: dict[str, Any], key: str) -> dict[str, Any] | None:
    part = config.get(key) or {}
    if not isinstance(part, dict):
        # ValueError, not TypeError: main.py reports ValueError as a config
        # mistake with this message, anything else as a crash
        raise ValueError(f"fileserver.{key} must be a mapping")  # noqa: TRY004
    return part if part.get("enable", False) else None


def _require(label: str, section: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if not section.get(k)]
    if missing:
        raise ValueError(f"{label} missing required key(s): {', '.join(missing)}")


def _linux_name(label: str, value: Any) -> str:
    if not isinstance(value, str) or not _LINUX_NAME.match(value):
        raise ValueError(
            f"{label} must be a Linux user name (lowercase letters, digits, _ "
            f"or -, starting with a letter or _), got {value!r}"
        )
    return value


def _password(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{label} must not contain line breaks")
    return value


def _size(label: str, value: Any) -> int:
    match = _SIZE.match(str(value).strip())
    if not match:
        raise ValueError(
            f"{label} must be a size like 500M, 20G or 0 (unlimited), got {value!r}"
        )
    return int(match.group(1)) * _SIZE_UNITS[match.group(2).upper()]


def _outbox_path(outbox: dict[str, Any]) -> PurePosixPath:
    folder = PurePosixPath(str(outbox.get("folder") or ""))
    if not folder.parts or folder.is_absolute() or ".." in folder.parts:
        raise ValueError(
            "fileserver.sftpgo.outbox.folder must be a relative path inside "
            f"general.fileserver_root (e.g. outbox), got {str(folder)!r}"
        )
    return folder


def _sftpgo_route(sftpgo: dict[str, Any]) -> dict[str, Any]:
    subdomain = sftpgo.get("subdomain") or {}
    _require("fileserver.sftpgo.subdomain", subdomain, ("name", "port"))
    share_link = sftpgo.get("share_link") or {}
    _require("fileserver.sftpgo.share_link", share_link, ("subdomain",))
    return {
        "subdomain": subdomain["name"],
        "port": subdomain["port"],
        "public": {"subdomain": share_link["subdomain"], "paths": PUBLIC_PATHS},
    }


def _general(general: dict[str, Any]) -> tuple[str, str]:
    for key in ("install", "fileserver_root"):
        if not general.get(key):
            raise ValueError(f"general.{key} is required by fileserver")
    root = PurePosixPath(str(general["fileserver_root"]))
    if not root.is_absolute():
        raise ValueError(
            f"general.fileserver_root must be an absolute path, got {str(root)!r}"
        )
    return str(general["install"]), str(root)


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    install, _ = _general(general)
    _linux_name("fileserver.user", config.get("user"))
    samba = _part(config, "samba")
    sftpgo = _part(config, "sftpgo")

    capabilities: dict[str, Any] = {}
    # everything render() would reject is rejected here too, so --check
    # catches it without rendering anything
    if samba:
        _samba_settings(samba)
    if sftpgo:
        _provision(sftpgo)

    if samba:
        capabilities["config_file"] = {"path": "/etc/samba/smb.conf"}
    elif sftpgo:
        capabilities["config_file"] = {
            "path": str(PurePosixPath(install) / "fileserver" / "compose.yaml")
        }
    if sftpgo:
        capabilities["http_route"] = _sftpgo_route(sftpgo)
    return capabilities


def _samba_settings(samba: dict[str, Any]) -> tuple[str, str, str]:
    _require("fileserver.samba", samba, ("share_name", "login"))
    share_name = str(samba["share_name"])
    if not _SHARE_NAME.match(share_name):
        raise ValueError(
            "fileserver.samba.share_name must be letters, digits, _ . or - "
            f"(it's typed into the mount path), got {share_name!r}"
        )
    login = _linux_name("fileserver.samba.login", samba["login"])
    password = _password("fileserver.samba.password", samba.get("password"))
    return share_name, login, password


def _smb_conf(samba: dict[str, Any], owner: str, root: str) -> str:
    share_name, login, _ = _samba_settings(samba)
    defaults = (DEFAULTS_DIR / "smb.conf").read_text()
    share = "\n".join(
        (
            f"[{share_name}]",
            f"   path = {root}",
            f"   valid users = {login}",
            # whoever logs in, files land owned by the one account sftpgo
            # also runs as, so both sides can keep editing each other's files
            f"   force user = {owner}",
            f"   force group = {owner}",
            "   read only = no",
            "   browseable = yes",
            "   create mask = 0664",
            "   directory mask = 0775",
        )
    )
    return defaults.rstrip("\n") + "\n\n" + share + "\n"


def _provision(sftpgo: dict[str, Any]) -> dict[str, Any]:
    _require("fileserver.sftpgo", sftpgo, ("admin_user",))
    user = sftpgo.get("user") or {}
    outbox = sftpgo.get("outbox") or {}
    _require("fileserver.sftpgo.user", user, ("name",))
    _require("fileserver.sftpgo.outbox", outbox, ("name",))
    if user["name"] == outbox["name"]:
        raise ValueError(
            "fileserver.sftpgo.user.name and outbox.name must differ - the "
            "outbox is a separate account so links can't reach the rest"
        )
    outbox_folder = _outbox_path(outbox)
    quota = _size("fileserver.sftpgo.outbox.quota", outbox.get("quota", 0))
    max_file = _size(
        "fileserver.sftpgo.outbox.max_file_size", outbox.get("max_file_size", 0)
    )
    return {
        "admins": [
            {
                "username": str(sftpgo["admin_user"]),
                "password": _password(
                    "fileserver.sftpgo.admin_pass", sftpgo.get("admin_pass")
                ),
                "status": 1,
                "permissions": ["*"],
            }
        ],
        "users": [
            {
                "username": str(user["name"]),
                "password": _password(
                    "fileserver.sftpgo.user.password", user.get("password")
                ),
                "status": 1,
                "home_dir": str(CONTAINER_ROOT),
                "permissions": {"/": ["*"]},
                "filters": {
                    # sharing only ever happens from the outbox account
                    "web_client": ["shares-disabled"],
                    "denied_protocols": DENIED_PROTOCOLS,
                },
            },
            {
                "username": str(outbox["name"]),
                "password": _password(
                    "fileserver.sftpgo.outbox.password", outbox.get("password")
                ),
                "status": 1,
                "home_dir": str(CONTAINER_ROOT / outbox_folder),
                "permissions": {"/": OUTBOX_PERMISSIONS},
                "quota_size": quota,
                "filters": {
                    "max_upload_file_size": max_file,
                    "denied_protocols": DENIED_PROTOCOLS,
                },
            },
        ],
    }


def _compose(sftpgo: dict[str, Any], root: str) -> dict[str, Any]:
    with open(DEFAULTS_DIR / "compose.yaml", "r") as f:
        compose: dict[str, Any] = yaml.safe_load(f)
    service = compose["services"]["sftpgo"]
    # resolved by compose from the .env lib/sh/fileserver.sh writes - the
    # owner's uid/gid only exist once that script has created the account
    service["user"] = "${FILESERVER_UID}:${FILESERVER_GID}"
    service["environment"]["SFTPGO_HTTPD__BINDINGS__0__PORT"] = str(
        _sftpgo_route(sftpgo)["port"]
    )
    service["volumes"].append(f"{root}:{CONTAINER_ROOT}")
    return compose


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    _, root = _general(general)
    owner = _linux_name("fileserver.user", config.get("user"))
    samba = _part(config, "samba")
    sftpgo = _part(config, "sftpgo")

    # a part switched off must not leave its previous render behind - the
    # deploy script tears it down based on what is (not) staged here
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    outbox_dir = ""
    if sftpgo:
        folder = _outbox_path(sftpgo.get("outbox") or {})
        outbox_dir = str(PurePosixPath(root) / folder)

        compose_text = write_yaml(
            out / "compose.yaml", _compose(sftpgo, root), mode=0o644
        )
        info(f"Generated fileserver compose:\n{compose_text}")
        provision = _provision(sftpgo)
        write_text(
            out / "provision" / "provision.json",
            json.dumps(provision, indent=2, sort_keys=True) + "\n",
            mode=0o600,
        )
        info("Generated provision/provision.json (contains passwords - not printed)")

    if samba:
        smb_text = write_text(out / "smb.conf", _smb_conf(samba, owner, root))
        info(f"Generated smb.conf:\n{smb_text}")
        _, login, password = _samba_settings(samba)
        write_text(out / "samba_credentials", f"{login}\n{password}\n", mode=0o600)
        info("Generated samba_credentials (contains password - not printed)")

    settings = {
        "FILESERVER_USER": owner,
        "FILESERVER_ROOT": root,
        "OUTBOX_DIR": outbox_dir,
        "SAMBA_ENABLE": "true" if samba else "false",
        "SFTPGO_ENABLE": "true" if sftpgo else "false",
    }
    for key, value in settings.items():
        if "\n" in value:
            raise ValueError(f"{key} must not contain line breaks, got {value!r}")
    # plain KEY=value lines, read (not sourced) by lib/sh/fileserver.sh
    write_text(
        out / "settings.env",
        "".join(f"{k}={v}\n" for k, v in settings.items()),
        mode=0o644,
    )
