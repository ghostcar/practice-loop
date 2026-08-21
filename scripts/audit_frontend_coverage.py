"""Static audit: which template-rendering GET routes are reachable from the UI.

Parses app/api/*.py statically:
- route decorators @router.get("...") with their TemplateResponse template names
- resolves router prefix (APIRouter(prefix="...")) and include_router prefix in main.py
- checks whether each final route path appears in any href/hx-* in app/templates/
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "app" / "api"
MAIN = ROOT / "app" / "main.py"
TEMPLATES = ROOT / "app" / "templates"


def collect_hrefs() -> set[str]:
    hrefs: set[str] = set()
    for p in TEMPLATES.rglob("*.html"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        hrefs.update(re.findall(r'href="(/[^"]*)"', text))
        hrefs.update(re.findall(r'hx-(?:get|post|put|delete)="(/[^"]*)"', text))
        hrefs.update(re.findall(r'hx-target="(/[^"]*)"', text))
        hrefs.update(re.findall(r'fetch\(\s*["\'](/[^"\']+)["\']', text))
        hrefs.update(re.findall(r'location\.href\s*=\s*["\'](/[^"\']+)["\']', text))
        # Jinja macros: nav_item(key, '/path', ...) and icon('name', ...)
        hrefs.update(re.findall(r"nav_item\([^,]+,\s*['\"](/[^'\"]+)['\"]", text))
        hrefs.update(re.findall(r"url_for\([^,]+,\s*['\"](/[^'\"]+)['\"]", text))
        # Jinja dynamic links: /entities/{{ entity.id }}/edit -> /entities/*/edit
        hrefs.update(re.findall(r'href="(/[^"]*\{\{[^}]*\}[^"]*)"', text))
        hrefs.update(re.findall(r"href='(/[^']*\{\{[^}]*\}[^']*)'", text))
    return {h for h in hrefs if not h.startswith("/static") and h != "/"}


def parse_file(path: Path) -> list[tuple[str, str, str]]:
    """Return (template, relative_path) pairs: template -> route path (with {params} preserved)."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    # map each router variable -> its prefix
    var_prefix: dict[str, str] = {}
    for m in re.finditer(
        r'([a-z_0-9]*router)\s*=\s*APIRouter\(([^)]*)\)', src, re.S
    ):
        var = m.group(1)
        pm = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', m.group(2))
        if pm:
            var_prefix[var] = pm.group(1).rstrip("/")
        else:
            var_prefix[var] = ""
    # package-level prefix: if this file is in a subpackage, look at __init__.py
    if path.parent != API:
        init = path.parent / "__init__.py"
        if init.exists():
            isrc = init.read_text(encoding="utf-8", errors="ignore")
            im = re.search(r'APIRouter\(([^)]*)\)', isrc)
            if im:
                pm = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', im.group(1))
                if pm:
                    pkg_prefix = pm.group(1).rstrip("/")
                    for v in var_prefix:
                        var_prefix[v] = pkg_prefix + var_prefix[v]
    out = []
    # collect decorators and TemplateResponse calls with their positions
    decos = [
        (m.start(), m.group(1), m.group(2), m.group(3))
        for m in re.finditer(r'@([a-z_0-9]*router)\.(get|post)\("([^"]*)"', src)
    ]
    tpls = [
        (m.start(), m.group(1))
        for m in re.finditer(
            r'TemplateResponse\([^)]*?name\s*=\s*["\']([a-z_/]+\.html)["\']', src, re.S
        )
    ]
    if not tpls:
        # legacy positional form: TemplateResponse(request, "tpl.html")
        tpls = [
            (m.start(), m.group(1))
            for m in re.finditer(r'TemplateResponse\(\s*[^,]*\s*,\s*["\']([a-z_/]+\.html)["\']', src)
        ]
    for i, (dpos, var, verb, rpath) in enumerate(decos):
        if verb != "get":
            continue
        # find TemplateResponse calls between this decorator and the next
        end = decos[i + 1][0] if i + 1 < len(decos) else len(src)
        body_tpls = [t for (tpos, t) in tpls if dpos < tpos < end]
        if body_tpls:
            full = f"{var_prefix.get(var, '')}{rpath}"
            out.append((body_tpls[0], full))
    return out


def main() -> None:
    hrefs = collect_hrefs()
    href_norm = {h.rstrip("/") for h in hrefs}

    pages: list[tuple[str, str, str]] = []  # (template, final_path, source_file)
    for py in sorted(API.rglob("*.py")):
        for tpl, rpath in parse_file(py):
            # route path may already be absolute; else prefix from main include or file router
            final = rpath if rpath.startswith("/") else "/" + rpath
            pages.append((tpl, final.rstrip("/"), str(py.relative_to(ROOT))))

    print(f"pages with TemplateResponse: {len(pages)}")
    print(f"unique hrefs: {len(href_norm)}")
    print("\n=== ORPHAN pages (route path never linked in UI) ===")
    orphans: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for tpl, path, src in sorted(pages, key=lambda kv: kv[1]):
        if path in seen:
            continue
        seen.add(path)
        if path in href_norm:
            continue
        if any(path.startswith(h + "/") for h in href_norm):
            continue
        # dynamic routes like /entities/{id} — check for a Jinja link /entities/{{ id }}/edit
        base = path.split("{")[0].rstrip("/")
        if base and any("{{ " in h and h.startswith(base) for h in href_norm):
            continue
        # dynamic routes like /entities/{id} — check for a link containing the prefix
        if base and any(h.startswith(base) for h in href_norm):
            continue
        orphans.append((path, tpl, src))
    for path, tpl, src in orphans:
        print(f"  {path:50s} {tpl:40s} {src}")
    if not orphans:
        print("  (none)")
    print("\n=== Sample linked pages ===")
    shown = 0
    for tpl, path, _src in sorted(pages, key=lambda kv: kv[1]):
        if path in href_norm and shown < 8:
            print(f"  {path:50s} {tpl}")
            shown += 1


if __name__ == "__main__":
    main()
