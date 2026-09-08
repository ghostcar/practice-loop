"""Online Pharmaceutical Directory Parser (Vidal & RxNorm).

Fetches verified drug master data and real generics/analogues from open
pharmaceutical references (Vidal.ru for RU/CIS, RxNorm for international names).
Includes memory caching and graceful fallback on network errors.
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 86400  # 24 hours
_MEMORY_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}

_SENTINEL = object()
_CLEAN_TAGS = re.compile(r"<[^>]+>")
_CLEAN_REG = re.compile(r"&(?:reg|copy|trade);?|[®©™]", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    text = html.unescape(s)
    text = _CLEAN_REG.sub("", text)
    text = _CLEAN_TAGS.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _get_cached(key: str) -> Any:
    entry = _MEMORY_CACHE.get(key)
    if entry is None:
        return _SENTINEL
    ts, val = entry
    if time.time() - ts > _CACHE_TTL_SEC:
        _MEMORY_CACHE.pop(key, None)
        return _SENTINEL
    return val


def _set_cached(key: str, val: dict[str, Any] | None) -> None:
    if len(_MEMORY_CACHE) > 500:
        _MEMORY_CACHE.clear()
    _MEMORY_CACHE[key] = (time.time(), val)


async def lookup_vidal(query: str, max_analogs: int = 10) -> dict[str, Any] | None:
    """Search Vidal.ru for a drug name, extract active substance and analogues."""
    clean_q = query.strip()
    if not clean_q or len(clean_q) < 2:
        return None

    cache_key = f"vidal:{clean_q.lower()}"
    cached = _get_cached(cache_key)
    if cached is not _SENTINEL:
        return cached

    timeout = httpx.Timeout(5.0, connect=3.0)
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = await client.get("https://www.vidal.ru/search", params={"q": clean_q})
            if resp.status_code != 200:
                _set_cached(cache_key, None)
                return None

            matches = re.findall(
                r'<td class="products-table-name">.*?<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>',
                resp.text,
                re.DOTALL,
            )
            if not matches:
                _set_cached(cache_key, None)
                return None

            first_drug_path = matches[0][0]
            first_drug_name = _clean_text(matches[0][1])

            drug_resp = await client.get(f"https://www.vidal.ru{first_drug_path}")
            if drug_resp.status_code != 200:
                _set_cached(cache_key, None)
                return None

            drug_html = drug_resp.text

            mol_match = re.search(
                r'<a[^>]+href="(/drugs/molecule/(\d+))"[^>]*>(.*?)</a>',
                drug_html,
            )

            molecule_id: str | None = None
            substance_name: str | None = None
            if mol_match:
                molecule_id = mol_match.group(2)
                substance_name = _clean_text(mol_match.group(3))

            firm_match = re.search(r'<a[^>]+href="/drugs/firm/[^"]*"[^>]*>(.*?)</a>', drug_html)
            manufacturer = _clean_text(firm_match.group(1)) if firm_match else None

            form_match = re.search(r'<div class="hyphenate">.*?<p>(.*?)</p>', drug_html, re.DOTALL)
            form_desc = _clean_text(form_match.group(1)) if form_match else None

            analogs: list[dict[str, Any]] = []
            if molecule_id:
                mol_in_resp = await client.get(f"https://www.vidal.ru/drugs/molecule-in/{molecule_id}")
                if mol_in_resp.status_code == 200:
                    raw_analogs = re.findall(
                        r'<td class="products-table-name">.*?<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>',
                        mol_in_resp.text,
                        re.DOTALL,
                    )
                    seen_names: set[str] = set()
                    src_norm = clean_q.lower()
                    for _, a_raw in raw_analogs:
                        a_name = _clean_text(a_raw)
                        norm_a = a_name.lower()
                        if not a_name or norm_a == src_norm or norm_a in seen_names:
                            continue
                        seen_names.add(norm_a)
                        analogs.append({
                            "name": a_name,
                            "manufacturer": None,
                            "form": None,
                            "strength": None,
                            "same_composition": True,
                            "notes": f"Дженерик с веществом: {substance_name}" if substance_name else None,
                        })
                        if len(analogs) >= max_analogs:
                            break

            components: list[dict[str, Any]] = []
            if substance_name:
                components.append({
                    "name": substance_name.capitalize(),
                    "inn": substance_name.capitalize(),
                    "amount": None,
                    "unit": None,
                })

            result: dict[str, Any] = {
                "name": first_drug_name or clean_q,
                "kind": "medication",
                "active_ingredient": substance_name.capitalize() if substance_name else None,
                "components": components,
                "manufacturer": manufacturer,
                "form": form_desc,
                "analogs": analogs,
                "source": "vidal.ru",
            }
            _set_cached(cache_key, result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("Vidal lookup failed for %r: %s", clean_q, exc)
        _set_cached(cache_key, None)
        return None


async def lookup_rxnorm(query: str) -> dict[str, Any] | None:
    """Query NIH RxNorm REST API for international/English drug names."""
    clean_q = query.strip()
    if not clean_q or not re.search(r"^[a-zA-Z0-9\s\-]+$", clean_q):
        return None

    cache_key = f"rxnorm:{clean_q.lower()}"
    cached = _get_cached(cache_key)
    if cached is not _SENTINEL:
        return cached

    timeout = httpx.Timeout(4.0, connect=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                "https://rxnav.nlm.nih.gov/REST/drugs.json",
                params={"name": clean_q},
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                _set_cached(cache_key, None)
                return None
            data = resp.json()
            concept_group = data.get("drugGroup", {}).get("conceptGroup", [])
            names: list[str] = []
            for group in concept_group:
                for concept in group.get("conceptProperties", []):
                    name = concept.get("name")
                    if name and name not in names:
                        names.append(name)

            if not names:
                _set_cached(cache_key, None)
                return None

            first_name = names[0]
            analogs = [
                {
                    "name": n,
                    "manufacturer": None,
                    "form": None,
                    "strength": None,
                    "same_composition": True,
                    "notes": "RxNorm generic",
                }
                for n in names[1:9]
            ]
            result = {
                "name": first_name,
                "kind": "medication",
                "active_ingredient": clean_q.capitalize(),
                "components": [{"name": clean_q.capitalize(), "inn": clean_q.capitalize()}],
                "manufacturer": None,
                "form": None,
                "analogs": analogs,
                "source": "rxnorm",
            }
            _set_cached(cache_key, result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("RxNorm lookup failed for %r: %s", clean_q, exc)
        _set_cached(cache_key, None)
        return None


async def online_drug_lookup(name: str, max_analogs: int = 10) -> dict[str, Any] | None:
    """Combined online lookup: try Vidal first, then RxNorm."""
    clean = name.strip()
    if not clean:
        return None

    vidal_res = await lookup_vidal(clean, max_analogs=max_analogs)
    if vidal_res:
        return vidal_res

    rxnorm_res = await lookup_rxnorm(clean)
    if rxnorm_res:
        return rxnorm_res

    return None
