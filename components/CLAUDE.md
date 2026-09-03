# The one rule
 
`components/<name>/` is a **read-only source of defaults**. Nothing in it is
ever edited, templated in place, or written to during a run. All output goes to
`build/<name>/`.
 
    components/<name>/   defaults, committed, never written
    config.yaml          user deltas, gitignored, 0600
    build/<name>/        generated, disposable, safe to `rm -rf`
 
`build/` is reproducible from the other two. If it is not, something wrote state
where it should not have.

# Per-component layout
- configure.py required. entry point, see below
- compose.yaml if containerized. base service definition
- install.sh optional. host-side work that is not config generation
- files/ optional. non-config assets copied verbatim to build
- *.yaml|*.conf|… optional. base config files in the component's own format

Formats differ per component. `main.py` must never learn a component's format - it hands over a dict and a destination, `configure.py` does the rest.

# configure.py

Should contain interfaces for both validation of input config and generation of the resulting config and validation of it. Configure might return values that will be reused by other components, without knowing about each other
Example: frigate provides web-ui for the user, so it returns back port on which UI is running and name, so a reverse-proxy could map it
If not sure what to return and in which format - ask.
 

# Merge semantics
 
Two classes of user key, and they are handled differently:
 
**Passthrough** - the user value maps onto a base file with no reshaping.
Handled by shared helpers in `lib/`, not reimplemented per component. Rules:
 
- maps: deep merge, user wins on conflict
- scalars: user wins
- lists: **replace wholesale**, never append. A user who lists two ports gets
  exactly two ports. If a component genuinely needs append semantics, it says so
  in a comment at the merge site
- a key absent from user config leaves the base value untouched
- a key set to `null` deletes the base key
`docker:` is a reserved passthrough key: it merges into the component's own
service block in `compose.yaml`. Every containerized component gets this for
free - do not hand-roll it.
 
**Derived** - one user key expands into several places, or into a different
shape. This is the whole reason `configure.py` exists. Keep the derivation in
one function per user key so it stays greppable.
 
The set of user-facing keys is closed. Adding one is a deliberate decision, not
a side effect of a feature - it is public API and someone has to live with it.
Anything a sane default covers stays in the base file.

# Determinism
 
Re-running `--generate` on unchanged inputs must produce **byte-identical**
output. That is what makes idempotency checkable by hash rather than by
guesswork.
 
- no timestamps, no hostnames-of-the-moment, no random ordering
- iterate dicts in a fixed order; preserve source order where order is semantic
  (compose `depends_on`, ffmpeg inputs) and sort where it is not
- generated secrets are read back from disk if already present, never
  regenerated on a converged host

# Worked example: frigate
 
Base files: `compose.yaml` (service skeleton, image pin, tmpfs cache) and
`config.yml` (snapshots, record, detect, motion defaults, mqtt off, tls off -
Caddy terminates).
 
| user key | destination |
|---|---|
| `docker.*` | `compose.yaml` → `services.frigate` (generic passthrough) |
| `cams.<n>.{login,password,ip,stream}` | derived → `go2rtc.streams.<n>`, `cameras.<n>.ffmpeg.inputs[0].path` with roles `audio, record`, `cameras.<n>.onvif.{host,user,password}` |
| `cams.<n>.detect` | derived → `cameras.<n>.detect.enabled` and `cameras.<n>.motion.enabled` |
 
Everything else - retention, quality, thresholds, contour area - stays in
`config.yml` and is not user-facing. A user who needs to change contour area is
a user who should be editing the component.
 
`declare` returns one `HttpService(slug="frigate", upstream="frigate:8971",
tls_upstream=True)`. Frigate does not know whether anything will read it, and
its output is identical either way.
 
`validate` checks: at least one camera; each camera has a non-placeholder `ip`;
`login`/`password` non-empty when the stream URL needs them; camera names are
valid Frigate identifiers and unique.
 
Storage lands under `facts.stack_root/frigate`, not a path the user repeats in
the frigate block.

# Worked example: frigate
 
Base files: `compose.yaml` (service skeleton, image pin, tmpfs cache) and
`config.yml` (snapshots, record, detect, motion defaults, mqtt off, tls off -
Caddy terminates).
 
| user key | destination |
|---|---|
| `docker.*` | `compose.yaml` → `services.frigate` (generic passthrough) |
| `cams.<n>.{login,password,ip,stream}` | derived → `go2rtc.streams.<n>`, `cameras.<n>.ffmpeg.inputs[0].path` with roles `audio, record`, `cameras.<n>.onvif.{host,user,password}` |
| `cams.<n>.detect` | derived → `cameras.<n>.detect.enabled` and `cameras.<n>.motion.enabled` |
 
Everything else - retention, quality, thresholds, contour area - stays in
`config.yml` and is not user-facing. A user who needs to change contour area is
a user who should be editing the component.