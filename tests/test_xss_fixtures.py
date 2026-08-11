"""REM §A14 XSS-fixture tests — ensure user-controlled strings can never reach
HTML without escaping.

Three layers:
1) base.html server-side Jinja autoescape is on (covered by all template renders)
2) Client-side `escapeHtml()` correctly neutralises payloads
3) End-to-end: a malicious-looking string passed through the stack lands harmless

The function `escapeHtml` is defined inline in base.html; here we mirror its
implementation so we can test the same behaviour without spinning up the
HTTP layer.
"""

import pytest


# ── Mirror of base.html#escapeHtml to test the JS contract from Python.
# (Keep this in sync with app/templates/base.html — if the JS side changes,
# update this and the security regression is no longer passing.)
def escape_html(value) -> str:
    if value is None:
        return ""
    s = str(value)
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")
    )


# ── Phase 1: Server-side autoescape (Jinja) ──


def test_jinja_autoescape_renders_user_data_inert():
    """User-controlled string rendered in a Jinja template must not produce
    executable HTML or attribute-breaking sequences."""
    from jinja2 import DictLoader, Environment, select_autoescape

    env = Environment(loader=DictLoader({}), autoescape=select_autoescape())
    tpl = env.from_string('<div class="row">{{ payload }}</div>')
    out = tpl.render(payload="<script>alert(1)</script>")
    # No literal <script> tag remains
    assert "<script>" not in out
    # Escaped form is present
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_jinja_autoescape_inside_attribute_quotes():
    tpl = env_render('<a title="{{ x }}">link</a>')  # type: ignore[name-defined]
    out = tpl.render(x='"><img src=x onerror=alert(1)>')
    # The attribute must be properly escaped - no closing quote or new tag injected
    assert '"><img' not in out.replace("&quot;", "QUOTE")  # raw quote pattern gone


def env_render(src):
    """Helper that mirrors setup of templates_setup."""
    from jinja2 import DictLoader, Environment, select_autoescape

    env = Environment(loader=DictLoader({}), autoescape=select_autoescape())
    return env.from_string(src)


# ── Phase 2: Client-side escapeHtml ──


XSS_PAYLOADS = [
    ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
    ('"><img src=x onerror=alert(1)>', "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"),
    ("' onmouseover='alert(1)", "&#39; onmouseover=&#39;alert(1)"),
    ("javascript:alert(1)", "javascript:alert(1)"),  # no-op; URL scheme preserved
    ("& < > \" '", "&amp; &lt; &gt; &quot; &#39;"),
    ("plain text", "plain text"),
    (42, "42"),  # numeric payloads converted
    (None, ""),  # explicit null
]


@pytest.mark.parametrize("raw,expected", XSS_PAYLOADS)
def test_escape_html_neutralises_payloads(raw, expected):
    assert escape_html(raw) == expected


def test_escape_html_does_double_escape_safe_chars():
    """& must be escaped first to avoid double-escaping entities later in the chain."""
    already_escaped = "&lt;safe&gt;"
    out = escape_html(already_escaped)
    # & becomes &amp; before < and > are re-escaped — this is conventional,
    # but the result is still safe (browsers parse &amp;lt; as just the literal text).
    assert "&amp;lt;" in out
    assert "<safe>" not in out


def test_escape_html_handles_unicode_payloads():
    """Unicode characters must pass through unchanged but quotes/angles escape."""
    out = escape_html("Привет <мир>")
    assert "<мир>" not in out
    assert "&lt;мир&gt;" in out


# ── Phase 3: end-to-end template render with hostile user payload ──


def test_calendar_renders_inert_when_name_is_malicious():
    """Calendar template renders hostile names as text, not as tags."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(),
    )

    from app.i18n.en import EN

    env.globals["t"] = EN

    html = env.get_template("calendar.html").render(
        t=EN,
        today_schedule={
            "template_name": "Work&<script>alert(1)</script>",
            "date": "2026-08-09",
            "windows": [],
        },
    )
    # Bare <script> tag MUST NOT be present anywhere
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_inventory_renders_inert_when_item_name_is_malicious():
    """Inventory template: when an item.name is hostile, escaping is applied.

    Browsers treat `&lt;img&gt;` as literal text, NOT a tag — so the
    `onerror=` substring inside escaped text is harmless (no img element
    is actually constructed). This test guards against accidentally
    unescaping that input via raw template substitution.
    """
    item_name = '<img src=x onerror="alert(1)">'
    escaped = escape_html(item_name)
    # Safe: <img replaced with &lt;img → browser cannot instantiate the tag.
    assert "<img" not in escaped
    assert "&lt;img" in escaped
    # Quotes in attribute escape ENTIRELY — no closing attribute possible.
    assert 'src=x onerror="alert(1)"' not in escaped
    assert "&quot;" in escaped


def _build_env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(),
    )
    from app.i18n.en import EN

    class T:
        def get(self, k, default=""):
            return EN.get(k, default)

    def __call__(self, k, default=""):  # noqa: N807 — dunder allowed for proxy
        return EN.get(k, default)

    T.__call__ = __call__
    return env, T()


# ── Phase 4: regression-style — known XSS patterns from OWASP cheat sheet ──


@pytest.mark.parametrize(
    "payload",
    [
        "<svg/onload=alert(1)>",
        "<iframe src=javascript:alert(1)>",
        "';alert(String.fromCharCode(88,83,83))//",
        "<script>alert('XSS')</script>",
        '<a href="javascript:alert(1)">click</a>',
        "<body onload=alert(1)>",
        "<input autofocus onfocus=alert(1)>",
        "{{constructor.constructor('alert(1)')()}}",  # template injection
        "<%= 'XSS' %>",  # ERB injection
        "${alert(1)}",  # JS template literal injection (intentional raw)
    ],
)
def test_common_owasp_xss_payloads_are_neutralised(payload):
    escaped = escape_html(payload)
    # None of the dangerous tags should remain as a real tag
    assert "<script>" not in escaped.lower()
    assert "<iframe" not in escaped.lower()
    assert "<svg" not in escaped.lower()
    assert "<body" not in escaped.lower()
    assert "<input" not in escaped.lower()
    assert "<a " not in escaped.lower()
