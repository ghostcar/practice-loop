"""Analogs / equivalents (ADR-109, ADR-190 phase F, multicomponent support)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import get_translations
from app.models.medication import MedStock
from app.services.med.graph import get_med, load_meds_graph
from app.services.med.serializers import composition_label
from app.services.med.substances import extract_med_substances, normalize_substance, sync_med_components
from app.services.med.units import equivalent_candidates
from app.timeutils import local_now

logger = logging.getLogger(__name__)

_ANALOGS_MAX = 10


def _build_analogs_prompt(
    med_name: str,
    composition: str,
    target_substance: str | None,
    locale: str,
    target_strength: str | None = None,
) -> str:
    """Генерирует целевой системный промпт с учетом многокомпонентности, выбранного вещества и дозировки."""
    strength_clause = (
        f"ЦЕЛЕВАЯ ДОЗИРОВКА ИСХОДНОГО ПРЕПАРАТА: {target_strength}. "
        f"ОБЯЗАТЕЛЬНО укажи доступные дозировки для каждого аналога в поле strength. "
        f"Если у аналога есть форма с совпадающей дозировкой ({target_strength}), укажи это в notes. "
        if target_strength
        else ""
    )

    if target_substance:
        return (
            f"Ты — фармацевтический справочник. Исходный препарат: {med_name}. "
            f"Полный состав препарата: {composition}. {strength_clause}"
            f"ЦЕЛЕВОЕ ДЕЙСТВУЮЩЕЕ ВЕЩЕСТВО ДЛЯ ПОИСКА АНАЛОГОВ: {target_substance}. "
            f"Найди известные тебе РЕАЛЬНЫЕ препараты-аналоги (дженерики, монопрепараты и комбинированные замены), "
            f"содержащие ИМЕННО действующее вещество '{target_substance}'. "
            "Верни только JSON: "
            '{"summary": "краткая справка", "analogs": [{"name": str, "manufacturer": str|null, '
            '"form": str|null, "strength": str|null, "same_composition": bool, "same_strength": bool, '
            '"notes": str|null}]}. '
            f"Правила: 1) Включай препараты, содержащие {target_substance}. "
            f"2) same_composition=true — только если препарат совпадает со ВСЕМИ веществами исходного {med_name}. "
            f"3) В notes на языке {locale} обязательно поясни форму, тип аналога и доступные дозировки. "
            "4) Не более 8-10 аналогов. 5) Ответ — строго валидный JSON-объект."
        )

    return (
        f"Ты — фармацевтический справочник. Исходный препарат: {med_name}. "
        f"Состав (действующие вещества): {composition}. {strength_clause}"
        "Найди известные тебе РЕАЛЬНЫЕ торговые наименования препаратов "
        "с теми же действующими веществами (дженерики и аналоги). "
        "ВНИМАНИЕ: Если препарат многокомпонентный (содержит 2 и более веществ), обязательно предложи: "
        "1) Полные комбинированные аналоги (где совпадают ВСЕ действующие вещества, same_composition=true); "
        "2) Качественные аналоги по ключевым отдельным действующим веществам (same_composition=false), "
        "равномерно распределив варианты между компонентами (чтобы не было перекоса только в одно вещество) "
        "и ОБЯЗАТЕЛЬНО явно указав в notes, по какому именно действующему веществу предложен аналог. "
        "Верни только JSON: "
        '{"summary": "краткая справка", "analogs": [{"name": str, "manufacturer": str|null, '
        '"form": str|null, "strength": str|null, "same_composition": bool, "same_strength": bool, '
        '"notes": str|null}]}. '
        f"Правила: 1) Включай только реально существующие препараты. 2) notes — на языке {locale} без назначения доз. "
        "3) Не более 8-10 аналогов. 4) Ответ — строго валидный JSON-объект."
    )


def _san_str(v: object) -> str | None:
    s = str(v or "").strip()[:200]
    return s or None


def _sanitize_analogs_payload(
    parsed: object,
    source_name: str,
    target_strength: str | None = None,
) -> tuple[list[dict], str | None]:
    """Строгая санитизация ответа LLM с сопоставлением дозировок."""
    from app.services.pharma_online import strengths_match

    if isinstance(parsed, list):
        parsed = {"analogs": parsed}
    if not isinstance(parsed, dict):
        return [], None
    raw = parsed.get("analogs")
    if not isinstance(raw, list):
        raw = []
    out: list[dict] = []
    seen: set[str] = set()
    src_norm = normalize_substance(source_name)
    for item in raw:
        if not isinstance(item, dict) or len(out) >= _ANALOGS_MAX:
            break
        name = str(item.get("name") or "").strip()[:200]
        if not name:
            continue
        nk = normalize_substance(name)
        if not nk or nk == src_norm or nk in seen:
            continue
        seen.add(nk)
        strength = _san_str(item.get("strength"))
        same_str = bool(item.get("same_strength"))
        if not same_str and target_strength and strength:
            same_str = strengths_match(target_strength, strength)

        out.append(
            {
                "name": name,
                "manufacturer": _san_str(item.get("manufacturer")),
                "form": _san_str(item.get("form")),
                "strength": strength,
                "same_composition": bool(item.get("same_composition")),
                "same_strength": same_str,
                "notes": _san_str(item.get("notes")),
            }
        )
    summary = _san_str(parsed.get("summary"))
    return out, summary


async def find_analogs(
    db: AsyncSession,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    locale: str = "ru",
    allow_directory_fallback: bool = True,
    target_substance: str | None = None,
    source_type: str = "llm",
    target_strength: str | None = None,
) -> dict:
    """ADR-109 & Multicomponent: поиск аналогов/дженериков по составу препарата через BYOK-LLM и онлайн-справочники.

    Параметры:
    - target_substance: конкретное действующее вещество (для многокомпонентных) или None/'all' для всех;
    - source_type: 'combined' (онлайн-каталог + ИИ), 'online' (только онлайн-реестры), 'llm' (только ИИ);
    - target_strength: целевая дозировка для точного сопоставления (например '25 мг', '100 мг', '200 мг').
    """
    from app.services.pharma_online import extract_dosage_strength, strengths_match

    m = await get_med(db, user_id, medication_id)
    clean_strength = (
        target_strength.strip()
        if target_strength and target_strength.strip()
        else extract_dosage_strength(m.name, m.strength)
    )
    composition = composition_label(m) or (m.active_ingredient or "").strip()
    if not composition:
        auto = await autofill_info(db, user_id, m.name, locale=locale)
        if auto:
            if auto.get("components"):
                await sync_med_components(db, m, auto["components"])
            if auto.get("active_ingredient") and not m.active_ingredient:
                m.active_ingredient = auto["active_ingredient"]
                db.add(m)
                await db.flush()
            m = await get_med(db, user_id, medication_id)
            composition = composition_label(m) or (m.active_ingredient or "").strip()

    if not composition:
        raise ValueError("no_composition")

    available_substances = extract_med_substances(m)
    clean_target = (
        target_substance.strip()
        if target_substance and target_substance.strip() not in ("all", "")
        else None
    )

    directory_analogs: list[dict] = []
    sources_used: list[str] = []

    # 1. Поиск по онлайн-каталогам (Vidal.ru / RxNorm)
    if source_type in ("combined", "online"):
        try:
            from app.services.pharma_online import online_drug_lookup

            # Target lookup
            online_res = await online_drug_lookup(
                m.name,
                max_analogs=_ANALOGS_MAX,
                target_substance=clean_target,
                target_strength=clean_strength,
            )
            if online_res and online_res.get("analogs"):
                sources_used.append("vidal.ru")
                for item in online_res["analogs"]:
                    item_name = str(item.get("name") or "").strip()
                    if item_name and normalize_substance(item_name) != normalize_substance(m.name):
                        directory_analogs.append({
                            "name": item_name,
                            "manufacturer": _san_str(item.get("manufacturer")),
                            "form": _san_str(item.get("form")),
                            "strength": _san_str(item.get("strength")),
                            "same_composition": bool(item.get("same_composition", True)),
                            "same_strength": bool(item.get("same_strength", False)),
                            "notes": _san_str(item.get("notes")),
                        })

            # If multicomponent and no target substance specified, also query online directory for each substance
            if not clean_target and len(available_substances) > 1 and len(directory_analogs) < _ANALOGS_MAX:
                seen_sub_names = {normalize_substance(x["name"]) for x in directory_analogs}
                for sub in available_substances[:2]:
                    sub_res = await online_drug_lookup(
                        m.name,
                        max_analogs=4,
                        target_substance=sub,
                        target_strength=clean_strength,
                    )
                    if sub_res and sub_res.get("analogs"):
                        if "vidal.ru" not in sources_used:
                            sources_used.append("vidal.ru")
                        for item in sub_res["analogs"]:
                            item_name = str(item.get("name") or "").strip()
                            nk = normalize_substance(item_name)
                            if item_name and nk != normalize_substance(m.name) and nk not in seen_sub_names:
                                seen_sub_names.add(nk)
                                directory_analogs.append({
                                    "name": item_name,
                                    "manufacturer": _san_str(item.get("manufacturer")),
                                    "form": _san_str(item.get("form")),
                                    "strength": _san_str(item.get("strength")),
                                    "same_composition": False,
                                    "same_strength": bool(item.get("same_strength", False)),
                                    "notes": _san_str(item.get("notes")) or f"Аналог по веществу: {sub}",
                                })
        except Exception as exc:  # noqa: BLE001
            logger.debug("Online directory lookup failed for %s (target=%s): %s", m.name, clean_target, exc)

    analogs: list[dict] = []
    summary: str | None = None

    # 2. Только онлайн-режим
    if source_type == "online":
        if directory_analogs:
            analogs = directory_analogs[:_ANALOGS_MAX]
            if clean_target:
                summary = f"Аналоги по действующему веществу '{clean_target}' найдены по онлайн-каталогу Vidal.ru"
            else:
                summary = "Аналоги по составу найдены по онлайн-каталогу Vidal.ru"
            source = "vidal.ru"
        elif allow_directory_fallback:
            # Fallback to LLM if online gave no results
            source_type = "llm"
        else:
            analogs = []
            summary = "Онлайн-каталог не содержит зарегистрированных аналогов по данному запросу."
            source = "vidal.ru"

    # 3. ИИ-поиск (LLM) или комбинированный режим
    if source_type in ("combined", "llm"):
        from app.llm.client import call_llm, set_call_meta
        from app.llm.pipeline import get_active_llm_config
        from app.llm.repair import parse_llm_json

        config = await get_active_llm_config(db, user_id, capability="text")
        if config is None:
            if allow_directory_fallback and directory_analogs:
                analogs = directory_analogs[:_ANALOGS_MAX]
                summary = "Аналоги и дженерики найдены по онлайн-реестру Vidal.ru (LLM-провайдер не настроен)"
                source = "vidal.ru"
            else:
                raise ValueError("no_llm")
        else:
            prompt = _build_analogs_prompt(
                m.name,
                composition,
                clean_target,
                locale,
                target_strength=clean_strength,
            )
            user_msg = (
                f"Препарат: {m.name}\n"
                f"Состав: {composition}\n"
                f"Форма: {m.form or '—'}\n"
                f"Дозировка: {clean_strength or m.strength or '—'}\n"
                f"Целевое вещество: {clean_target or 'Все вещества (полная комбинация)'}"
            )
            set_call_meta(section="medication", purpose="analogs_search")
            try:
                result = await call_llm(
                    config,
                    system_prompt=prompt,
                    user_message=user_msg,
                    json_mode=True,
                    db=db,
                    user_id=user_id,
                )
                content = (result.get("content") or "").strip()
                parsed = None
                try:
                    parsed = parse_llm_json(content, is_last_attempt=True) if content else None
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM analogs parse failed for med %s: %s", medication_id, exc)

                llm_analogs, llm_summary = _sanitize_analogs_payload(
                    parsed,
                    m.name,
                    target_strength=clean_strength,
                )
                sources_used.append("llm")

                # Combine LLM and online directory results
                seen_nk = {normalize_substance(x["name"]) for x in llm_analogs}
                for da in directory_analogs:
                    nk = normalize_substance(da["name"])
                    if nk and nk not in seen_nk and len(llm_analogs) < _ANALOGS_MAX:
                        seen_nk.add(nk)
                        llm_analogs.append(da)

                analogs = llm_analogs[:_ANALOGS_MAX]
                source = " + ".join(sources_used) or "llm"
                if clean_target:
                    summary = (
                        llm_summary
                        or f"Аналоги сфокусированы на действующем веществе '{clean_target}' (источники: {source})"
                    )
                else:
                    summary = llm_summary or f"Аналоги и дженерики по составу препарата (источники: {source})"
            except Exception as exc:  # noqa: BLE001
                if allow_directory_fallback and directory_analogs:
                    analogs = directory_analogs[:_ANALOGS_MAX]
                    summary = "Аналоги и дженерики найдены по онлайн-реестру Vidal.ru (ошибка вызова LLM)"
                    source = "vidal.ru"
                else:
                    logger.warning("LLM analogs call failed for med %s: %s", medication_id, exc)
                    raise ValueError("llm_error") from None

    for row in analogs:
        if clean_strength and row.get("strength"):
            if not row.get("same_strength"):
                row["same_strength"] = strengths_match(clean_strength, row["strength"])
        else:
            row.setdefault("same_strength", False)

    # Sort: full composition first, then matching dosage, then by name
    analogs.sort(
        key=lambda x: (
            not x.get("same_composition", False),
            not x.get("same_strength", False),
            x.get("name", ""),
        )
    )

    meds = await load_meds_graph(db, user_id)
    owned_by_norm = {normalize_substance(x.name): x for x in meds if x.name}
    for row in analogs:
        owned = owned_by_norm.get(normalize_substance(row["name"]))
        row["owned"] = owned is not None
        row["owned_medication_id"] = str(owned.id) if owned else None

    t = get_translations(locale)
    data = {
        "active_ingredient": composition,
        "composition": composition_label(m),
        "target_substance": clean_target,
        "target_strength": clean_strength,
        "available_substances": available_substances,
        "source": source,
        "source_type": source_type,
        "generated_at": local_now().isoformat(),
        "summary": summary,
        "analogs": analogs,
        "disclaimer": t.get("med_analogs_disclaimer", "Перед заменой препарата проконсультируйтесь с врачом."),
    }
    m.analogues = data
    db.add(m)
    await db.flush()
    return data


async def autofill_info(db: AsyncSession, user_id: uuid.UUID, name: str, locale: str = "ru") -> dict | None:
    from app.services.pharma_enricher import enrich_medication_info

    return await enrich_medication_info(db, user_id, name, locale=locale)


async def get_equivalents(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> dict:
    """ADR-190 (фаза F): заменители препарата по составу + остатки по аптечкам."""
    m = await get_med(db, user_id, medication_id)
    meds = await load_meds_graph(db, user_id)
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
    stocks_by_med: dict[str, list[MedStock]] = {}
    for st in stocks:
        stocks_by_med.setdefault(str(st.medication_id), []).append(st)
    candidates = equivalent_candidates(m, meds, stocks_by_med)
    return {
        "source": {
            "medication_id": str(m.id),
            "name": m.name,
            "form": m.form,
            "strength": m.strength,
            "composition_label": composition_label(m),
        },
        "candidates": candidates[:8],
        "total": len(candidates),
    }
