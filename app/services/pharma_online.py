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


def clean_drug_name(s: str) -> str:
    """Очищает торговое наименование от дозировок, форм выпуска и знаков препинания для каталогов."""
    # 1. Дозировки вида 25 мг, 0.06%, 200 mg, 1.5 мл
    t = re.sub(r"\b\d+(?:[\.,]\d+)?\s*(?:мг|г|мкг|мл|mg|g|mcg|ml|ед|iu|%)\b", " ", s, flags=re.IGNORECASE)
    # 2. Дроби типа 2/10
    t = re.sub(r"\b\d+/\d+\b", " ", t)
    # 3. Отдельные числа
    t = re.sub(r"\b\d+\b", " ", t)
    # 4. Формы выпуска
    t = re.sub(
        r"\b(?:таблетки|капсулы|раствор|гель|таб|капс|драже|крем|мазь|суспензия|спрей|суппозитории)\b\.?",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"[\.,%\+\-\/\(\)]", " ", t)
    res = re.sub(r"\s+", " ", t).strip()
    return res or s.strip()


def extract_dosage_strength(name: str, strength: str | None = None) -> str | None:
    """Извлекает или нормализует строку дозировки."""
    if strength and strength.strip():
        return strength.strip()
    m = re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:мг|г|мкг|мл|mg|g|mcg|ml|ед|iu|%)\b", name, flags=re.IGNORECASE)
    if m:
        return m.group(0).strip()
    m_num = re.search(r"\b\d+/\d+\b", name)
    if m_num:
        return m_num.group(0).strip()
    m_single = re.search(r"\b\d+\b", name)
    if m_single:
        return m_single.group(0).strip()
    return None


def normalize_strength_val_unit(s: str) -> tuple[float | None, str]:
    if not s:
        return None, ""
    clean = s.strip().lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([a-zа-я%]+)?", clean)
    if not m:
        return None, ""
    val = float(m.group(1))
    unit = m.group(2) or "мг"
    if unit in ("mg", "мг"):
        unit = "мг"
    elif unit in ("g", "г"):
        unit = "г"
    elif unit in ("mcg", "мкг"):
        unit = "мкг"
    elif unit in ("ml", "мл"):
        unit = "мл"
    return val, unit


def strengths_match(target: str, candidates: list[str] | str) -> bool:
    t_val, t_unit = normalize_strength_val_unit(target)
    if t_val is None:
        return False
    if isinstance(candidates, str):
        c_list = re.findall(
            r"\b\d+(?:[\.,]\d+)?\s*(?:мг|г|мкг|мл|mg|g|mcg|ml|ед|iu|%)\b", candidates, flags=re.IGNORECASE
        )
        if not c_list:
            c_list = [candidates]
    else:
        c_list = candidates
    for c in c_list:
        c_val, c_unit = normalize_strength_val_unit(c)
        if c_val is not None and c_val == t_val and (not t_unit or not c_unit or t_unit == c_unit):
            return True
    return False


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


async def lookup_vidal(
    query: str,
    max_analogs: int = 10,
    target_substance: str | None = None,
    target_strength: str | None = None,
) -> dict[str, Any] | None:
    """Search Vidal.ru for a drug name, extract active substances, dosages and analogues.

    Supports multicomponent drugs, dosage equivalence, and targeted search by active substance.
    """
    clean_q = query.strip()
    clean_sub = target_substance.strip() if target_substance else None
    clean_str = extract_dosage_strength(clean_q, target_strength)
    if not clean_q and not clean_sub:
        return None

    base_q = clean_drug_name(clean_q)
    sub_part = clean_sub.lower() if clean_sub else "all"
    str_part = clean_str.lower() if clean_str else "none"
    cache_key = f"vidal:{clean_q.lower()}:{sub_part}:{str_part}"
    cached = _get_cached(cache_key)
    if cached is not _SENTINEL:
        return cached

    timeout = httpx.Timeout(6.0, connect=3.0)
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            search_query = clean_sub or base_q or clean_q
            resp = await client.get("https://www.vidal.ru/search", params={"q": search_query})
            if resp.status_code != 200:
                _set_cached(cache_key, None)
                return None

            matches = re.findall(
                r'<td class="products-table-name">.*?<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>',
                resp.text,
                re.DOTALL,
            )
            # If base name gave no matches, fallback to original query
            if not matches and base_q != clean_q and not clean_sub:
                search_query = clean_q
                resp = await client.get("https://www.vidal.ru/search", params={"q": search_query})
                if resp.status_code == 200:
                    matches = re.findall(
                        r'<td class="products-table-name">.*?<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>',
                        resp.text,
                        re.DOTALL,
                    )

            first_drug_name = clean_q
            drug_html = ""
            if matches:
                first_drug_path = matches[0][0]
                first_drug_name = _clean_text(matches[0][1])
                drug_resp = await client.get(f"https://www.vidal.ru{first_drug_path}")
                if drug_resp.status_code == 200:
                    drug_html = drug_resp.text

            # If searching by target_substance or no drug page, also check direct molecule search
            direct_mol_matches = re.findall(
                r'<a[^>]+href="(/drugs/molecule/(\d+))"[^>]*>(.*?)</a>',
                resp.text,
            )

            # Find all molecule references on the drug page or search page
            mols_found = re.findall(
                r'<a[^>]+href="(/drugs/molecule/(\d+))"[^>]*>(.*?)</a>',
                drug_html,
            ) or direct_mol_matches

            molecules: list[tuple[str, str]] = []  # (mol_id, substance_name)
            seen_mols = set()
            for _, m_id, m_name in mols_found:
                c_name = _clean_text(m_name)
                if m_id not in seen_mols and c_name:
                    seen_mols.add(m_id)
                    molecules.append((m_id, c_name))

            firm_match = re.search(r'<a[^>]+href="/drugs/firm/[^"]*"[^>]*>(.*?)</a>', drug_html)
            manufacturer = _clean_text(firm_match.group(1)) if firm_match else None

            form_match = re.search(r'<div class="hyphenate">.*?<p>(.*?)</p>', drug_html, re.DOTALL)
            form_desc = _clean_text(form_match.group(1)) if form_match else None

            # Filter molecules if target_substance specified
            if clean_sub and molecules:
                sub_norm = clean_sub.lower()
                matching_mols = [m for m in molecules if sub_norm in m[1].lower() or m[1].lower() in sub_norm]
                if matching_mols:
                    molecules = matching_mols
                else:
                    # If drug page didn't have this molecule, search Vidal directly for this substance
                    mol_resp = await client.get("https://www.vidal.ru/search", params={"q": clean_sub})
                    if mol_resp.status_code == 200:
                        direct_mols = re.findall(
                            r'<a[^>]+href="(/drugs/molecule/(\d+))"[^>]*>(.*?)</a>',
                            mol_resp.text,
                        )
                        if direct_mols:
                            molecules = [(direct_mols[0][1], _clean_text(direct_mols[0][2]))]

            analogs: list[dict[str, Any]] = []
            seen_names: set[str] = set()
            src_norm = clean_q.lower()
            base_src_norm = base_q.lower()

            target_strengths: set[str] = set()
            target_forms: set[str] = set()
            target_mfr: str | None = None
            target_rx: bool = False

            for mol_id, sub_name in molecules[:3]:
                mol_in_resp = await client.get(f"https://www.vidal.ru/drugs/molecule-in/{mol_id}")
                if mol_in_resp.status_code != 200:
                    continue

                rows = re.findall(r"<tr[^>]*>(.*?)</tr>", mol_in_resp.text, re.DOTALL)
                analogs_map: dict[str, dict[str, Any]] = {}

                for r in rows:
                    if "products-table-name" not in r:
                        continue
                    tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL)
                    if len(tds) < 2:
                        continue
                    name_m = re.search(r'<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>', tds[1], re.DOTALL)
                    if not name_m:
                        continue
                    a_name = _clean_text(name_m.group(2)).replace("&reg;", "").replace("®", "").strip()
                    norm_a = a_name.lower()
                    if not a_name:
                        continue

                    form_text = _clean_text(tds[3]) if len(tds) > 3 else ""
                    mfr_text = _clean_text(tds[4]) if len(tds) > 4 else ""
                    rx_status = _clean_text(tds[0]) if len(tds) > 0 else ""

                    found_strengths = list(
                        dict.fromkeys(
                            re.findall(r"\b\d+(?:[\.,]\d+)?\s*(?:мг|мкг|%|ед|ме)\b", form_text, flags=re.IGNORECASE)
                        )
                    )
                    if not found_strengths:
                        found_strengths = list(
                            dict.fromkeys(
                                re.findall(
                                    r"\b\d+(?:[\.,]\d+)?\s*(?:мг|г|мкг|мл|%|ед|ме)\b",
                                    form_text,
                                    flags=re.IGNORECASE,
                                )
                            )
                        )
                    found_forms = []
                    for kw in ("капсулы", "таблетки", "гель", "раствор", "крем", "мазь", "суспензия", "спрей", "драже"):
                        if kw in form_text.lower():
                            found_forms.append(kw)

                    is_target = (
                        norm_a in (src_norm, base_src_norm)
                        or (base_src_norm and base_src_norm in norm_a)
                        or (base_src_norm and clean_drug_name(norm_a) == base_src_norm)
                    )
                    if is_target:
                        target_strengths.update(found_strengths)
                        target_forms.update(found_forms)
                        if not target_mfr and mfr_text:
                            target_mfr = mfr_text
                        if "рецепт" in rx_status.lower():
                            target_rx = True
                        continue

                    if norm_a in (src_norm, base_src_norm):
                        continue

                    if norm_a not in analogs_map:
                        analogs_map[norm_a] = {
                            "name": a_name,
                            "manufacturer": mfr_text or None,
                            "forms": set(found_forms),
                            "strengths": set(found_strengths),
                        }
                    else:
                        analogs_map[norm_a]["forms"].update(found_forms)
                        analogs_map[norm_a]["strengths"].update(found_strengths)
                        if not analogs_map[norm_a]["manufacturer"] and mfr_text:
                            analogs_map[norm_a]["manufacturer"] = mfr_text

                # Fallback to simple regex if table rows were not parsed
                if not analogs_map:
                    raw_analogs = re.findall(
                        r'<td class="products-table-name">.*?<a[^>]+href="(/drugs/[^"]+)"[^>]*>(.*?)</a>',
                        mol_in_resp.text,
                        re.DOTALL,
                    )
                    for _, a_raw in raw_analogs:
                        a_name = _clean_text(a_raw).replace("&reg;", "").replace("®", "").strip()
                        norm_a = a_name.lower()
                        if not a_name or norm_a in (src_norm, base_src_norm) or norm_a in seen_names:
                            continue
                        seen_names.add(norm_a)
                        analogs.append({
                            "name": a_name,
                            "manufacturer": None,
                            "form": None,
                            "strength": None,
                            "same_composition": len(molecules) == 1 or (not clean_sub and len(mols_found) <= 1),
                            "same_strength": False,
                            "notes": f"Действующее вещество: {sub_name}",
                        })
                        if len(analogs) >= max_analogs:
                            break
                else:
                    for norm_a, item in analogs_map.items():
                        if norm_a in seen_names:
                            continue
                        seen_names.add(norm_a)

                        sorted_strengths = sorted(
                            item["strengths"],
                            key=lambda x: normalize_strength_val_unit(x)[0] or 0,
                        )
                        strength_label = ", ".join(sorted_strengths) if sorted_strengths else None
                        form_label = ", ".join(sorted(item["forms"])) if item["forms"] else None

                        same_str = (
                            strengths_match(clean_str, sorted_strengths)
                            if clean_str and sorted_strengths
                            else False
                        )
                        if same_str:
                            notes = f"Совпадает дозировка ({clean_str}). Доступно: {strength_label}"
                        elif strength_label:
                            notes = f"Доступные дозировки: {strength_label}"
                        else:
                            notes = f"Действующее вещество: {sub_name}"

                        analogs.append({
                            "name": item["name"],
                            "manufacturer": item["manufacturer"],
                            "form": form_label,
                            "strength": strength_label,
                            "same_composition": len(molecules) == 1 or (not clean_sub and len(mols_found) <= 1),
                            "same_strength": same_str,
                            "notes": notes,
                        })
                        if len(analogs) >= max_analogs * 2:
                            break

                if len(analogs) >= max_analogs * 2:
                    break

            # Sort analogs: same_strength first, then by name
            analogs.sort(key=lambda x: (not x.get("same_strength", False), x.get("name", "")))
            analogs = analogs[:max_analogs]

            sorted_target_strengths = sorted(
                target_strengths,
                key=lambda x: normalize_strength_val_unit(x)[0] or 0,
            )
            all_known_strengths = list(sorted_target_strengths)
            if not all_known_strengths:
                temp_s: set[str] = set()
                for a in analogs:
                    if a.get("strength"):
                        for part in a["strength"].split(","):
                            p = part.strip()
                            if p:
                                temp_s.add(p)
                all_known_strengths = sorted(
                    temp_s,
                    key=lambda x: normalize_strength_val_unit(x)[0] or 0,
                )

            final_strength = clean_str or (", ".join(sorted_target_strengths) if sorted_target_strengths else None)
            final_form = form_desc or (", ".join(sorted(target_forms)) if target_forms else None)
            final_mfr = manufacturer or target_mfr

            first_strength_to_fill = (
                clean_str or (sorted_target_strengths[0] if len(sorted_target_strengths) == 1 else None)
            )
            amt_val, unit_val = (
                normalize_strength_val_unit(first_strength_to_fill) if first_strength_to_fill else (None, None)
            )

            components: list[dict[str, Any]] = [
                {
                    "name": m_name.capitalize(),
                    "inn": m_name.capitalize(),
                    "amount": amt_val,
                    "unit": unit_val,
                }
                for _, m_name in molecules
            ]

            active_ing = " + ".join([m_name.capitalize() for _, m_name in molecules]) if molecules else None

            result: dict[str, Any] = {
                "name": first_drug_name or clean_q,
                "kind": "medication",
                "active_ingredient": active_ing,
                "components": components,
                "manufacturer": final_mfr,
                "form": final_form,
                "strength": final_strength,
                "available_strengths": all_known_strengths,
                "prescription_required": target_rx,
                "analogs": analogs,
                "source": "vidal.ru",
                "target_substance": clean_sub,
                "target_strength": clean_str,
            }
            _set_cached(cache_key, result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("Vidal lookup failed for query=%r, sub=%r, str=%r: %s", clean_q, clean_sub, clean_str, exc)
        _set_cached(cache_key, None)
        return None
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


async def online_drug_lookup(
    name: str,
    max_analogs: int = 10,
    target_substance: str | None = None,
    target_strength: str | None = None,
) -> dict[str, Any] | None:
    """Combined online lookup: try Vidal first, then RxNorm."""
    clean = name.strip()
    clean_sub = target_substance.strip() if target_substance else None
    if not clean and not clean_sub:
        return None

    vidal_res = await lookup_vidal(
        clean,
        max_analogs=max_analogs,
        target_substance=clean_sub,
        target_strength=target_strength,
    )
    if vidal_res:
        return vidal_res

    rxnorm_query = clean_sub or clean
    rxnorm_res = await lookup_rxnorm(rxnorm_query)
    if rxnorm_res:
        return rxnorm_res

    return None
