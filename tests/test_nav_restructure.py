"""Temporary smoke: nav restructure renders 5 sections (Flash #7)."""
import re
import warnings

warnings.filterwarnings("ignore")  # passlib/bcrypt env artifact


async def test_nav_renders_five_sections(auth_client):
    r = await auth_client.get("/dashboard")
    assert r.status_code == 200
    titles = re.findall(r'pl-nav-group-title">([^<]+)<', r.text)
    assert len(titles) >= 5, titles
    # EN locale labels for the 5 product sections
    assert any(t in titles for t in ("Now", "Plan", "Body & Routine", "Connections", "System")), titles
    assert re.findall(r"pl-nav-item", r.text)
