# serv

Config-driven deployment for a home server: Frigate, Pi-hole, Caddy, DuckDNS,
WireGuard, SSH, and an nftables firewall, all driven by one `config.yaml`.
Target is a fresh Debian 13 (trixie) box. **WireGuard is the ingress for
everything except SSH** — every other service is reachable only over the
tunnel; the firewall trusts the `wg0` interface completely and opens nothing
else on the WAN except what a component explicitly declares (currently just
WireGuard's own port and SSH's).

Must be run as root (installs packages, writes to `/etc`, manages systemd
and docker).

## Quick start

```bash
cp config.yaml.example config.yaml
# edit config.yaml
./deploy.sh --check            # validate before doing anything
./deploy.sh --deploy
```

`deploy.sh` bootstraps its own venv and installs `requirements.txt` — no
manual Python setup needed.

## CLI flags

| Flag | What it does |
|---|---|
| `--check` | Validates `config.yaml` and exits. No files touched. |
| `--dry-run` | Prints exactly what `--deploy` would do, without doing it. |
| `--generate` | Renders every enabled component's config into `build/` only. Nothing is installed or started. |
| `--deploy` | Generate + install + start/restart, **conservatively**: each component only restarts/recreates if it detects an actual change (file diff, docker compose's own diff, etc). Safe to run repeatedly — a converged host is a no-op. |
| `--force [COMPONENT]` | Same pipeline as `--deploy`, but skips the "did anything change" checks for the targeted component and unconditionally restarts its service / recreates its container. Needed because some components can't reliably detect a change on their own (see **Frigate config changes** below). With no `COMPONENT`, every enabled component is forced — the whole stack. With `COMPONENT` (a name from `config.yaml`'s `components:`, e.g. `--force wireguard`), *only* that component is forced; every other enabled component still runs the full generate/install pipeline as a normal `--deploy` would (so anything that reads the registry — e.g. Caddy's routes — stays correct), it just isn't forced to restart. |

**Be aware:**
- `--force` is not "wipe and redeploy." It never touches persistent runtime
  state (docker volumes, WireGuard's key/peers) — only the config that state
  runs under.
- `--force` scoped to one component doesn't skip the other pipeline stages —
  the capability registry is still built from every enabled component
  first, and every enabled component is still rendered and installed, so a
  scoped force never leaves a stale registry or config behind. Only the
  named component's own idempotency check is bypassed.
- **WireGuard is the one exception in both modes.** `--deploy` never touches
  an existing `/etc/wireguard/wg0.conf` at all — WireGuard peers live outside
  `config.yaml` (see below), and overwriting the file would wipe them.
  `--force` *will* update it, but surgically: it regenerates `Address` /
  `ListenPort` / NAT rules from your current config while preserving the
  existing private key and every peer byte-for-byte. Nothing about your
  identity or connected peers is ever regenerated.
- `--deploy`/`--force` write a full transcript of everything they print
  (including subprocess output — `apt-get`, `docker compose`, `systemctl`,
  etc.) to `build/deploy.log`, in addition to your terminal. Check it after a
  deploy if something needs investigating after the fact.
- Nothing has been run against a real production box by anyone but you —
  test on a disposable VM first if you can, especially the first time.

## Components (`config.yaml` sections)

Enable a component by adding its name to the top-level `components:` list
*and* giving it a section — both are required, `--check` will catch a
mismatch either way. Details and full field list live in
`config.yaml.example`; the important gotchas per component:

- **`general`** — shared settings (`apex_domain`, `hostname`, `install`,
  `build_path`, `host_ip`, `fileserver_root`). `common_config_folder`
  (optional) symlinks every component's "main" config file into one folder
  for convenience — only populated during `--deploy`/`--force`, not
  `--generate`.
- **`caddy`** — reverse proxy, installed via Caddy's official apt repo (not
  docker). TLS is **off** — this only makes sense because nothing but
  WireGuard/SSH reaches the host from the WAN. Reverse-proxy blocks are
  generated automatically for every component that exposes an HTTP service;
  you don't configure routing here beyond the optional static fileserver.
  With `wan_enable`, 443 is opened on the WAN, but only routes that opt in
  (`wan: true`, or a component's public address such as `fileserver`'s
  share links) answer there.
- **`frigate`** — docker-based. Camera credentials go straight into RTSP
  URLs in the rendered config — treat `build/frigate` and the deployed
  install directory as sensitive. **Frigate's web UI password cannot be set
  in `config.yaml`** — Frigate generates a random admin password on first
  boot and only ever prints it once, to its own container logs. Find it in
  `build/deploy.log` after a deploy (`grep -i password build/deploy.log`),
  or via `docker logs frigate`.
- **`ddns`** — runs `duckdns_keepup` as a systemd service. Config changes
  (domain/token) are detected and applied correctly by a plain `--deploy` —
  no `--force` needed here.
- **`pihole`** — docker-based, DNS/ad-blocking only, no DHCP. Frees host port
  53 by disabling `systemd-resolved`'s stub listener (only the stub listener
  — your own DNS resolution is left alone); safely skipped if
  `systemd-resolved` isn't present at all. `admin_pass` changes are picked
  up by a plain `--deploy` (Docker Compose diffs `environment:`/`env_file`
  correctly) — again, no `--force` needed.
- **`wireguard`** — installed via apt, not docker. **Peers are not managed
  in `config.yaml` at all** — see below. Changing `listen_port`/`server_mask`
  after the first deploy requires `--force` (or `--force wireguard` to force
  just it) since plain `--deploy` won't touch an existing setup.
- **`ssh`** — writes a drop-in at `/etc/ssh/sshd_config.d/99-serv.conf`
  rather than editing `sshd_config` directly. Always validated with
  `sshd -t` *before* ever restarting the service — an invalid config is
  rejected and the previous one restored, so a typo here can't lock you out.
  Kept reachable on the WAN like WireGuard (not tunnel-only) — this assumes
  a home network behind a router with only default ports forwarded; if
  that's not your threat model, reconsider `password_authentication` and
  `permit_root_login`.
- **`fileserver`** — everything that serves `general.fileserver_root` beyond
  caddy's read-only view, as two parts with their own `enable`:
  - **`samba`** (apt) — one SMB3 share, reachable over WireGuard only:
    `\\<host_ip>\<share_name>` on Windows, `smb://<host_ip>/<share_name>` on
    Linux/Android (Android needs an SMB-capable file manager app).
  - **`sftpgo`** (docker) — web UI plus expiring share and upload links, all
    under one public name, `<share_link.subdomain>.<general.wan_host>`: over
    the tunnel (pihole resolves it to `host_ip`) it's the full UI, from the
    WAN only the share pages are served and everything else is a 404. Needs
    `caddy.https`, `caddy.wan_enable` and 443 forwarded on the router. Links
    can only be created by the separate outbox account, which sees nothing
    outside its folder; your own account can't create any. **Accounts are
    created on the container's first start only** — after that, change
    passwords in the web UI (`/web/admin`), not `config.yaml`.

  Both write files as `fileserver.user`; on the first deploy it takes over
  ownership of `fileserver_root` recursively. Disabling a part stops it
  (samba) or removes its container (sftpgo) but keeps its state.
- **`firewall`** — nftables, installed via apt. Default-drop on the public
  interface; `wg0` is fully trusted, and traffic to `host_ip` is only
  accepted from `wg0`; the *only* other things opened are
  whatever ports components declare (currently WireGuard's, SSH's, and
  443 when `caddy.wan_enable` is on). If
  you're testing this for the first time, do it with console/physical
  access to the box, not only over the connection you're about to firewall.

## Managing WireGuard peers

Peers are deliberately kept out of `config.yaml` so that redeploying never
risks wiping a live connection. Add one manually, after `wireguard` has been
deployed at least once:

```bash
bash lib/sh/wireguard_add_peer.sh <peer_name> <peer_ip>
```

Prints the peer's private key and the server's public key so you can build
that peer's client config by hand — there's no automated delivery step yet.

## Things worth knowing before your first deploy

- `config.yaml` is never touched automatically by anything in this repo
  beyond what you explicitly run. It holds real credentials, so mind
  where it ends up.
- `build/` is fully regenerated on every `--generate`/`--deploy`/`--force`
  and is gitignored — don't hand-edit anything under it, it won't survive
  the next run.
- Every rendered secret-bearing file (ddns's script, pihole's env file) is
  written `chmod 600` and its contents are deliberately never printed to
  stdout/logs; everything else is dumped in full so you can eyeball what's
  about to be installed.
- A failing component halts the entire `--deploy`/`--force` run at that
  point — components later in the `components:` list simply won't run yet.
  Check the tail of `build/deploy.log` (or the terminal) to see exactly
  where it stopped.
