"""memoryctl code_units — structural code-unit parser (M3 pilot, CODE_MEMORY_DESIGN.md §4).

Stdlib-only extraction of the *units* that get embedded and indexed by the
vector pilot. Chunking is structural, never "every N tokens": one unit = one
module / class / function / method / route / model / template block / JS
handler / migration / config section.

Every unit carries:

- ``path``       repo-relative POSIX path;
- ``symbol``     qualified symbol (e.g. ``LockTimerService.open_slot``);
- ``span``       (start_line, end_line) 1-based, inclusive;
- ``unit_kind``  one of UNIT_KINDS;
- ``language``   ``python`` | ``jinja2`` | ``javascript`` | ``alembic`` | ``config``;
- ``scope``      bounded context (locktimer/core, social, llm, …);
- ``signature``  human-readable signature/route metadata line;
- ``retrieval_text`` normalized text that gets embedded (never the raw body alone);
- ``content_hash`` sha256 of (path + span + retrieval_text) — content-addressed.

This module is pure-Python and has zero third-party imports so it runs without
the optional vector dependencies and is unit-testable in isolation.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

PARSER_VERSION = "0.1.0"

UNIT_KINDS = (
    "module",
    "class",
    "function",
    "method",
    "route",
    "model",
    "revision",
    "template_block",
    "macro",
    "form",
    "js_handler",
    "config_section",
    "test",
    "fixture",
)

_SCAN_DIRS = ("app", "tests", "alembic")
_SCAN_SUFFIXES = (".py", ".html", ".js", ".yml", ".yaml", ".toml")

# Bounded-context derivation from repo path prefixes (ordered, first match wins).
_SCOPE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("app/locktimer/", "locktimer/core"),
    ("app/platform/social/", "social"),
    ("app/llm/", "llm"),
    ("app/api/", "tracker/core"),
    ("app/models/", "tracker/core"),
    ("app/templates/locktimer/", "locktimer/core"),
    ("app/static/js/pages/", "tracker/core"),
    ("app/", "tracker/core"),
    ("tests/test_locktimer", "locktimer/core"),
    ("tests/test_social", "social"),
    ("tests/", "tracker/core"),
    ("alembic/", "data/migrations"),
)


@dataclass
class CodeUnit:
    path: str
    symbol: str
    start_line: int
    end_line: int
    unit_kind: str
    language: str
    scope: str
    signature: str
    retrieval_text: str
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = content_hash(self.path, self.start_line, self.end_line, self.retrieval_text)

    def to_payload(self) -> dict:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "span": (self.start_line, self.end_line),
            "unit_kind": self.unit_kind,
            "language": self.language,
            "scope": self.scope,
            "signature": self.signature,
            "content_hash": self.content_hash,
        }


def content_hash(path: str, start: int, end: int, retrieval_text: str) -> str:
    digest = f"{path}\x00{start}\x00{end}\x00{retrieval_text}".encode()
    return "sha256:" + hashlib.sha256(digest).hexdigest()


def derive_scope(path: str) -> str:
    for prefix, scope in _SCOPE_PREFIXES:
        if path.startswith(prefix):
            return scope
    return "platform"


def _unit(
    path: str, symbol: str, start: int, end: int, kind: str, lang: str, signature: str, retrieval: str
) -> CodeUnit:
    return CodeUnit(
        path=path,
        symbol=symbol,
        start_line=start,
        end_line=end,
        unit_kind=kind,
        language=lang,
        scope=derive_scope(path),
        signature=signature,
        retrieval_text=retrieval,
    )


# ---------------------------------------------------------------------------
# Python (ast)
# ---------------------------------------------------------------------------


def _docstring(node: ast.AST) -> str:
    return ast.get_docstring(node, clean=True) or ""


def _route_meta(decorators: list[ast.expr]) -> tuple[str, str] | None:
    """Detect a FastAPI-style @router.get('/path') decorator → (method, path)."""
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    for dec in decorators:
        call = dec
        while isinstance(call, ast.Attribute):
            call = call.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute) or func.attr not in methods:
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "router":
            continue
        path = ""
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            path = call.args[0].value
        return func.attr.upper(), path
    return None


def _is_model(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Assign | ast.AnnAssign):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "__tablename__":
                    return True
    return False


def parse_python(path: str, text: str) -> list[CodeUnit]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    units: list[CodeUnit] = []
    lines = text.splitlines()

    def span_lines(start: int, end: int) -> str:
        if start < 1:
            start = 1
        return "\n".join(lines[start - 1 : end]) if lines else ""

    def make(symbol: str, node: ast.AST, kind: str, signature: str, doc: str, body_src: str) -> CodeUnit:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        retrieval = "\n".join(x for x in (signature, doc, body_src[:1500]) if x)
        return _unit(path, symbol, start, end, kind, "python", signature, retrieval)

    # module-level docstring
    if ast.get_docstring(tree):
        body_src = span_lines(1, min(40, len(lines)))
        units.append(
            _unit(
                path,
                path,
                1,
                min(40, len(lines)),
                "module",
                "python",
                "module",
                _docstring(tree) + "\n" + body_src[:800],
            )
        )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            doc = _docstring(node)
            cls_kind = "model" if _is_model(node.body) else "class"
            sig = f"class {node.name}"
            body_src = span_lines(node.lineno, node.end_lineno)
            units.append(make(f"{node.name}", node, cls_kind, sig, doc, body_src))
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    cdoc = _docstring(child)
                    route = _route_meta(child.decorator_list)
                    if route:
                        method, route_path = route
                        sig = f"{method} {route_path} ({node.name}.{child.name})"
                        kind = "route"
                    else:
                        sig = f"def {node.name}.{child.name}(...)"
                        kind = "method"
                    units.append(
                        make(
                            f"{node.name}.{child.name}",
                            child,
                            kind,
                            sig,
                            cdoc,
                            span_lines(child.lineno, child.end_lineno),
                        )
                    )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            doc = _docstring(node)
            route = _route_meta(node.decorator_list)
            is_fixture = any(
                (isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "fixture")
                or (isinstance(d, ast.Attribute) and d.attr == "fixture")
                for d in node.decorator_list
            )
            sig = f"def {node.name}(...)"
            if is_fixture:
                kind = "fixture"
            elif node.name.startswith("test_"):
                kind = "test"
            elif route:
                method, route_path = route
                kind = "route"
                sig = f"{method} {route_path}"
                doc = f"{method} {route_path}\n{doc}"
            else:
                kind = "function"
            units.append(make(node.name, node, kind, sig, doc, span_lines(node.lineno, node.end_lineno)))

    return units


# ---------------------------------------------------------------------------
# Alembic revisions
# ---------------------------------------------------------------------------

_REVISION_RE = re.compile(r'^(?:down_)?revision(?:\s*:\s*str\b[^=]*)?\s*=\s*["\']([^"\']+)["\']')


def parse_alembic(path: str, text: str) -> list[CodeUnit]:
    units: list[CodeUnit] = []
    revision = None
    down = None
    for line in text.splitlines():
        m = re.match(r'^revision(?:\s*:\s*str\b[^=]*)?\s*=\s*["\']([^"\']+)["\']', line)
        if m:
            revision = m.group(1)
        m = re.match(r'^down_revision(?:\s*:\s*str\b[^=]*)?\s*=\s*["\']([^"\']+)["\']', line)
        if m:
            down = m.group(1)
    if revision is not None:
        # upgrade/downgrade function spans
        up_span = _function_span(text, "def upgrade")
        down_span = _function_span(text, "def downgrade")
        retrieval = f"alembic revision {revision} down_revision {down or 'None'}\n" + (
            text[:1200] if not up_span else text
        )
        unit = _unit(
            path,
            f"revision:{revision}",
            up_span[0] if up_span else 1,
            (down_span[1] if down_span else up_span[1] if up_span else len(text.splitlines())),
            "revision",
            "alembic",
            f"revision={revision} down_revision={down}",
            retrieval[:2000],
        )
        units.append(unit)
    return units


def _function_span(text: str, defname: str) -> tuple[int, int] | None:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(defname):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        stripped = lines[i]
        if stripped and not stripped[0].isspace() and i > start:
            end = i
            break
    return start, end


# ---------------------------------------------------------------------------
# Jinja2 templates
# ---------------------------------------------------------------------------

_BLOCK_RE = re.compile(r"{%\s*block\s+(\w+)")
_MACRO_RE = re.compile(r"{%\s*macro\s+(\w+)")
_FORM_RE = re.compile(r"<form\b[^>]*>")


def parse_jinja(path: str, text: str) -> list[CodeUnit]:
    units: list[CodeUnit] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _BLOCK_RE.search(line)
        if m:
            name = m.group(1)
            unit = _unit(
                path,
                f"block:{name}",
                i + 1,
                i + 1,
                "template_block",
                "jinja2",
                f"block {name}",
                line.strip(),
            )
            units.append(unit)
        m = _MACRO_RE.search(line)
        if m:
            name = m.group(1)
            units.append(_unit(path, f"macro:{name}", i + 1, i + 1, "macro", "jinja2", f"macro {name}", line.strip()))
        if _FORM_RE.search(line):
            units.append(_unit(path, f"form:{i + 1}", i + 1, i + 1, "form", "jinja2", "form", line.strip()))
    return units


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)")
_JS_ARROW_RE = re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
_JS_HANDLER_RE = re.compile(r"addEventListener\s*\(\s*['\"]([^'\"]+)['\"]")
_JS_FETCH_RE = re.compile(r"\bfetch\s*\(")


def parse_javascript(path: str, text: str) -> list[CodeUnit]:
    units: list[CodeUnit] = []
    for i, line in enumerate(text.splitlines()):
        m = _JS_FUNC_RE.match(line)
        if m:
            units.append(_unit(path, m.group(1), i + 1, i + 1, "js_handler", "javascript", line.strip(), line.strip()))
            continue
        m = _JS_ARROW_RE.match(line)
        if m:
            units.append(_unit(path, m.group(1), i + 1, i + 1, "js_handler", "javascript", line.strip(), line.strip()))
            continue
        if _JS_HANDLER_RE.search(line) or _JS_FETCH_RE.search(line):
            units.append(
                _unit(path, f"handler:{i + 1}", i + 1, i + 1, "js_handler", "javascript", line.strip(), line.strip())
            )
    return units


# ---------------------------------------------------------------------------
# Config (YAML/TOML) — semantic sections
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")  # TOML
_YAML_KEY_RE = re.compile(r"^([A-Za-z_][\w.-]*):\s*$")  # YAML top-level key


def parse_config(path: str, text: str) -> list[CodeUnit]:
    units: list[CodeUnit] = []
    for i, line in enumerate(text.splitlines()):
        m = _SECTION_RE.match(line)
        if m:
            units.append(
                _unit(
                    path, f"section:{m.group(1)}", i + 1, i + 1, "config_section", "config", line.strip(), line.strip()
                )
            )
            continue
        m = _YAML_KEY_RE.match(line)
        if m:
            units.append(
                _unit(path, f"key:{m.group(1)}", i + 1, i + 1, "config_section", "config", line.strip(), line.strip())
            )
    return units


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _language(path: str) -> str:
    if path.startswith("alembic/"):
        return "alembic"
    if path.endswith(".html"):
        return "jinja2"
    if path.endswith(".js"):
        return "javascript"
    if path.endswith((".yml", ".yaml", ".toml")):
        return "config"
    return "python"


def extract_file(path: str, text: str) -> list[CodeUnit]:
    lang = _language(path)
    if lang == "alembic":
        return parse_alembic(path, text)
    if lang == "python":
        return parse_python(path, text)
    if lang == "jinja2":
        return parse_jinja(path, text)
    if lang == "javascript":
        return parse_javascript(path, text)
    return parse_config(path, text)


def iter_scan_files(root: Path):
    for d in _SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in _SCAN_SUFFIXES:
                continue
            yield p, p.relative_to(root).as_posix()


def extract_units(root: Path, *, denylist=None) -> list[CodeUnit]:
    """Extract all structural units across app/tests/alembic (deterministic order)."""
    denylist = denylist or (lambda _rel: False)
    units: list[CodeUnit] = []
    for p, rel in iter_scan_files(root):
        if denylist(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        units.extend(extract_file(rel, text))
    return sorted(units, key=lambda u: (u.path, u.start_line, u.symbol))
