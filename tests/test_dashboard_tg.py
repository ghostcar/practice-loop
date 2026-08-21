import re
from app.prefs import UserPrefs

def test_prefs_new_block_visible_by_default():
    p = UserPrefs()
    assert "tg" in p.dash_visible
    # stored order WITHOUT tg → tg appended, still hideable
    p2 = UserPrefs(dash_blocks={"order": ["header", "stats"], "hidden": []})
    assert "tg" in p2.dash_visible
    p3 = UserPrefs(dash_blocks={"order": ["header", "stats"], "hidden": ["tg"]})
    assert "tg" not in p3.dash_visible

async def test_dashboard_renders_tg_card(auth_client):
    r = await auth_client.get("/dashboard")
    assert r.status_code == 200
    for id_ in ("tg-status-text", "tg-link-btn", "tg-code-display", "tg-code"):
        assert f'id="{id_}"' in r.text, f"missing {id_}"
    assert "dashboard.js" in r.text
