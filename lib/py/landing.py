import html
from pathlib import Path, PurePosixPath
from typing import Any

from utils import info, write_text

# capability types that produce a browsable address, in the order a consumer
# should treat them as equivalent - both are just "a site caddy serves"
_ADDRESSABLE = ("http_route", "static_site")


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    if "install" not in general:
        raise ValueError("general.install is required")
    root = str(PurePosixPath(general["install"]) / "landing" / "site")
    # no subdomain -> served at the apex domain itself. cache: False because
    # this page is regenerated on every deploy - without it browsers may serve
    # a stale copy for a while, since file_server sends no Cache-Control and
    # heuristic freshness kicks in
    return {
        "static_site": {
            "root": root,
            "wan": config.get("wan", False),
            "cache": False,
        }
    }


def _links(registry: dict[str, Any]) -> list[str]:
    """Every subdomain some component asked a reverse proxy to serve.

    Purely registry-derived: an entry with no subdomain is the apex site (i.e.
    this page), so it is skipped rather than linking to itself.
    """
    subdomains: list[str] = []
    for name in sorted(registry):
        for kind in _ADDRESSABLE:
            route = registry[name].get(kind)
            if not route:
                continue
            subdomain = route.get("subdomain")
            if subdomain:
                subdomains.append(str(subdomain))
    return sorted(set(subdomains))


def _page(title: str, apex_domain: str, subdomains: list[str]) -> str:
    if subdomains:
        # scheme-relative hrefs: the page is served by the same server as every
        # link, so the browser reuses its scheme - no need to know caddy's https
        items = "\n".join(
            f'      <li><a href="//{html.escape(s)}.{html.escape(apex_domain)}">'
            f"<span>{html.escape(s)}</span>"
            f'<span class="host">{html.escape(s)}.{html.escape(apex_domain)}</span>'
            "</a></li>"
            for s in subdomains
        )
        body = f"    <ul>\n{items}\n    </ul>"
    else:
        body = '    <p class="empty">No services are published yet.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f4;
  --fg: #1b1b1a;
  --muted: #6c6c68;
  --card: #ffffff;
  --line: #e3e3df;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #17171a;
    --fg: #ececea;
    --muted: #8f8f8a;
    --card: #202024;
    --line: #2f2f34;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 3rem 1rem;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}}
main {{ max-width: 34rem; margin: 0 auto; }}
h1 {{ font-size: 1.35rem; margin: 0 0 1.5rem; letter-spacing: -0.01em; }}
ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }}
a {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  padding: 0.85rem 1rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
  font-weight: 500;
}}
a:hover {{ border-color: var(--muted); }}
.host {{ color: var(--muted); font-weight: 400; font-size: 0.85rem; }}
.empty {{ color: var(--muted); }}
</style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
{body}
  </main>
</body>
</html>
"""


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    if "apex_domain" not in general:
        raise ValueError("general.apex_domain is required")
    title = str(config.get("title") or general["apex_domain"])
    subdomains = _links(registry)
    write_text(
        out / "site" / "index.html",
        _page(title, general["apex_domain"], subdomains),
        mode=0o644,
    )
    listed = ", ".join(subdomains) if subdomains else "(none)"
    info(f"Generated landing page for {general['apex_domain']} linking: {listed}")
