"""Pharma Enricher Service — Auto-fill medication master data (ADR-190, phase E).

Pipeline (spec §7):
1. **Seed** — LOCAL_PHARMA_SEED: normalized lookup, multi-component records
   (Femoston N/M by mask), INN per substance, optional daily_max_* reference;
2. **LLM** — real BYOK call (`call_llm`, json_mode) for names outside the seed,
   with json_repair; nothing fabricated: unknown fields → null;
3. **Fallback** — honest ``None`` ("не найдено") instead of junk prefill.

Response shape: form fields + ``components[]``:
  [{name, inn, amount, unit, variant, daily_max_amt?, daily_max_unit?}]
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_NORM_RE = re.compile(r"[^a-zа-я0-9 ]")


def _norm(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = _NORM_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Local seed dictionary (RU/International). Every entry carries
# ``components`` (canonical active ingredients) and an optional ``inn``.
# Multi-component pack variants (Femoston) are expressed via ``variant`` rows.
# ─────────────────────────────────────────────────────────────────────────────

_LOCAL_SEED: dict[str, dict] = {
    "бепантен": {
        "kind": "medication",
        "form": "мазь / крем",
        "strength": "5%",
        "manufacturer": "Bayer",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": False,
        "instructions": "Наносить на пораженные или чувствительные участки кожи 1-2 раза в день.",
        "components": [{"name": "Декспантенол", "inn": "Dexpanthenol"}],
    },
    "пантенол": {
        "kind": "medication",
        "form": "крем / спрей",
        "strength": "5%",
        "manufacturer": "Фармстандарт / Акрихин",
        "storage_conditions": "при температуре 15-25°C",
        "prescription_required": False,
        "instructions": "Наносить тонким слоем на поврежденные участки кожи.",
        "components": [{"name": "Декспантенол", "inn": "Dexpanthenol"}],
    },
    "хлоргексидин": {
        "kind": "supply",
        "form": "раствор водный",
        "strength": "0.05%",
        "manufacturer": "ПФК Обновление / Биосинтез",
        "storage_conditions": "в защищенном от света месте до 25°C",
        "prescription_required": False,
        "instructions": "Для гигиенической и антисептической обработки кожных покровов и слизистых.",
        "components": [{"name": "Хлоргексидина биглюконат", "inn": "Chlorhexidine digluconate"}],
    },
    "мирамистин": {
        "kind": "supply",
        "form": "раствор местный",
        "strength": "0.01%",
        "manufacturer": "Инфамед",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": False,
        "instructions": "Орошение и обработка кожных покровов и слизистых.",
        "components": [
            {
                "name": "Бензилдиметил[3-(миристоиламино)пропил]аммоний хлорид",
                "inn": "Benzyldimethyl[3-(myristoylamino)propyl]ammonium chloride monohydrate",
            }
        ],
    },
    "ибупрофен": {
        "kind": "medication",
        "form": "таблетки",
        "strength": "200 мг / 400 мг",
        "manufacturer": "Синтез / Акрихин",
        "storage_conditions": "в сухом месте до 25°C",
        "prescription_required": False,
        "instructions": "Принимать внутрь после еды, запивая водой.",
        "components": [{"name": "Ибупрофен", "inn": "Ibuprofen"}],
    },
    "нурофен": {
        "kind": "medication",
        "form": "таблетки / капсулы",
        "strength": "400 мг",
        "manufacturer": "Reckitt Benckiser",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": False,
        "instructions": "Принимать внутрь при болевом синдроме.",
        "components": [{"name": "Ибупрофен", "inn": "Ibuprofen"}],
    },
    "прогинова": {
        "kind": "medication",
        "form": "драже",
        "strength": "2 мг",
        "manufacturer": "Bayer",
        "storage_conditions": "при температуре не выше 30°C",
        "prescription_required": True,
        "instructions": "Принимать строго по схеме гормональной терапии ежедневно в одно время.",
        "components": [{"name": "Эстрадиола валерат", "inn": "Estradiol valerate", "amount": 2, "unit": "мг"}],
    },
    "андрокур": {
        "kind": "medication",
        "form": "таблетки",
        "strength": "10 мг / 50 мг",
        "manufacturer": "Bayer",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": True,
        "instructions": "Принимать строго по назначению врача в схемах ГТ.",
        "components": [{"name": "Ципротерона ацетат", "inn": "Cyproterone acetate"}],
    },
    "сустанон": {
        "kind": "medication",
        "form": "раствор для инъекций",
        "strength": "250 мг/мл",
        "manufacturer": "Organon",
        "storage_conditions": "в защищенном от света месте 8-30°C",
        "prescription_required": True,
        "instructions": "Внутримышечные инъекции по назначенной схеме ГТ.",
        "components": [{"name": "Тестостерона эфиры", "inn": "Testosterone (mixture of esters)"}],
    },
    "троксевазин": {
        "kind": "medication",
        "form": "гель 2%",
        "strength": "20 мг/г",
        "manufacturer": "Balkanpharma",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": False,
        "instructions": "Наносить легкими массирующими движениями на место гематом/синяков.",
        "components": [{"name": "Троксерутин", "inn": "Troxerutin"}],
    },
    "спасатель": {
        "kind": "supply",
        "form": "бальзам",
        "strength": "30 г",
        "manufacturer": "Люми",
        "storage_conditions": "при температуре 15-25°C",
        "prescription_required": False,
        "instructions": "Обильно наносить на поврежденную поверхность кожи.",
        "components": [
            {"name": "Масло облепиховое", "inn": "Sea buckthorn oil"},
            {"name": "Нафталан", "inn": "Naphthalan"},
            {"name": "Токоферол (витамин E)", "inn": "Tocopherol"},
            {"name": "Пчелиный воск", "inn": "Beeswax"},
        ],
    },
    "эутирокс": {
        "kind": "medication",
        "form": "таблетки",
        "strength": "25–150 мкг",
        "manufacturer": "Merck",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": True,
        "instructions": "Утром натощак за 30 мин до еды, строго по назначению врача.",
        "components": [{"name": "Левотироксин натрия", "inn": "Levothyroxine sodium", "unit": "мкг"}],
    },
    "омепразол": {
        "kind": "medication",
        "form": "капсулы",
        "strength": "20 мг",
        "manufacturer": "разные (дженерики)",
        "storage_conditions": "в сухом защищенном от света месте",
        "prescription_required": False,
        "instructions": "Утром до еды, капсулу не разжевывать.",
        "components": [{"name": "Омепразол", "inn": "Omeprazole", "amount": 20, "unit": "мг"}],
    },
    "дуфастон": {
        "kind": "medication",
        "form": "таблетки, покрытые оболочкой",
        "strength": "10 мг",
        "manufacturer": "Abbott",
        "storage_conditions": "при температуре не выше 30°C",
        "prescription_required": True,
        "instructions": "Принимать по схеме ГТ, в одно и то же время.",
        "components": [{"name": "Дидрогестерон", "inn": "Dydrogesterone", "amount": 10, "unit": "мг"}],
    },
    "аквадетрим": {
        "kind": "supplement",
        "form": "капли для приема внутрь",
        "strength": "15000 МЕ/мл",
        "manufacturer": "Medana Pharma",
        "storage_conditions": "в защищенном от света месте 5-25°C",
        "prescription_required": False,
        "instructions": "Растворить в ложке жидкости, принимать во время еды.",
        "components": [
            {
                "name": "Колекальциферол (витамин D3)",
                "inn": "Colecalciferol",
                "unit": "МЕ",
                "daily_max_amt": 100,
                "daily_max_unit": "мкг",
                "daily_max_note": "Взрослым обычно до 100 мкг (4000 МЕ)/сут, по назначению врача",
            }
        ],
    },
    "магне в6": {
        "kind": "supplement",
        "form": "таблетки, покрытые оболочкой",
        "strength": "Mg 48 мг + B6 5 мг",
        "manufacturer": "Sanofi",
        "storage_conditions": "при температуре не выше 25°C",
        "prescription_required": False,
        "instructions": "Принимать во время еды, запивая стаканом воды.",
        "components": [
            {"name": "Магния лактата дигидрат", "inn": "Magnesium lactate dihydrate"},
            {"name": "Пиридоксин (витамин B6)", "inn": "Pyridoxine", "amount": 5, "unit": "мг"},
        ],
    },
    "глицин": {
        "kind": "supplement",
        "form": "таблетки подъязычные",
        "strength": "100 мг",
        "manufacturer": "разные (дженерики)",
        "storage_conditions": "в сухом защищенном от света месте",
        "prescription_required": False,
        "instructions": "Держать под языком до полного растворения.",
        "components": [{"name": "Глицин", "inn": "Glycine", "amount": 100, "unit": "мг"}],
    },
    "парацетамол": {
        "kind": "medication",
        "form": "таблетки",
        "strength": "500 мг",
        "manufacturer": "разные (дженерики)",
        "storage_conditions": "в сухом месте до 25°C",
        "prescription_required": False,
        "instructions": "Взрослым по 500-1000 мг не чаще 4 раз/сут, не более 4 г/сут.",
        "components": [
            {
                "name": "Парацетамол",
                "inn": "Paracetamol",
                "amount": 500,
                "unit": "мг",
                "daily_max_amt": 4,
                "daily_max_unit": "г",
                "daily_max_note": "Максимум 4 г/сут для взрослых",
            }
        ],
    },
    "амоксициллин": {
        "kind": "medication",
        "form": "капсулы",
        "strength": "250/500 мг",
        "manufacturer": "разные (дженерики)",
        "storage_conditions": "в сухом месте до 25°C",
        "prescription_required": True,
        "instructions": "Принимать по схеме антибиотикотерапии, курс завершать полностью.",
        "components": [{"name": "Амоксициллин", "inn": "Amoxicillin", "amount": 500, "unit": "мг"}],
    },
    "компливит": {
        "kind": "supplement",
        "form": "таблетки, покрытые оболочкой",
        "strength": "комплекс витаминов и минералов",
        "manufacturer": "Фармстандарт-УфаВИТА",
        "storage_conditions": "в сухом защищенном от света месте до 25°C",
        "prescription_required": False,
        "instructions": "По 1 таблетке в день во время еды.",
        "components": [
            {"name": "Ретинол (витамин A)", "inn": "Retinol", "unit": "мкг"},
            {"name": "Тиамин (витамин B1)", "inn": "Thiamine", "unit": "мг"},
            {"name": "Рибофлавин (витамин B2)", "inn": "Riboflavin", "unit": "мг"},
            {"name": "Пиридоксин (витамин B6)", "inn": "Pyridoxine", "unit": "мг"},
            {"name": "Цианокобаламин (витамин B12)", "inn": "Cyanocobalamin", "unit": "мкг"},
            {"name": "Аскорбиновая кислота (витамин C)", "inn": "Ascorbic acid", "unit": "мг"},
            {"name": "Колекальциферол (витамин D3)", "inn": "Colecalciferol", "unit": "мкг"},
            {"name": "Кальций", "inn": "Calcium", "unit": "мг"},
            {"name": "Магний", "inn": "Magnesium", "unit": "мг"},
            {"name": "Железо", "inn": "Iron", "unit": "мг"},
            {"name": "Цинк", "inn": "Zinc", "unit": "мг"},
        ],
    },
}

# Фемостон по маске: «Фемостон N/M» / «Femoston N/M».
# Схема пачки: таблетки 1–14 — только эстрадиол N мг; 15–28 — эстрадиол N мг + дидрогестерон M мг.
# «Фемостон конти» — непрерывный режим: все 28 таблеток эстрадиол 2 мг + дидрогестерон 10 мг.
_FEMOSTON_RE = re.compile(r"^(фемостон|femoston)\s*(?:конти|conti)?\s*([0-9]+)?\s*[/хx]\s*([0-9]+)$", re.IGNORECASE)
_FEMOSTON_BASE = {
    "kind": "medication",
    "form": "таблетки, покрытые оболочкой",
    "strength": "2 мг + 10 мг (двухфазный режим)",
    "manufacturer": "Abbott",
    "storage_conditions": "при температуре не выше 30°C",
    "prescription_required": True,
    "instructions": "По 1 таблетке в день строго по схеме ГТ (белые 1–14, затем серые 15–28).",
}


def _build_femoston(name: str, estradiol_mg: int, dydrogesterone_mg: int, continuous: bool = False) -> dict:
    base = dict(_FEMOSTON_BASE)
    base["name"] = name
    est = {"name": "Эстрадиол", "inn": "Estradiolum", "amount": estradiol_mg, "unit": "мг"}
    dyd = {"name": "Дидрогестерон", "inn": "Dydrogesteronum", "amount": dydrogesterone_mg, "unit": "мг"}
    if continuous:
        base["strength"] = f"{estradiol_mg} мг + {dydrogesterone_mg} мг (непрерывный режим)"
        base["instructions"] = "По 1 таблетке в день ежедневно без перерыва, строго по схеме ГТ."
        base["components"] = [est, dyd]
    else:
        base["strength"] = f"{estradiol_mg} мг + {dydrogesterone_mg} мг (двухфазный режим)"
        base["components"] = [
            {**est, "variant": "белые 1–14 (эстрадиол)"},
            {**est, "variant": "серые 15–28 (эстрадиол + дидрогестерон)"},
            {**dyd, "variant": "серые 15–28 (эстрадиол + дидрогестерон)"},
        ]
    base["active_ingredient"] = "Эстрадиол + Дидрогестерон"
    return base


def _seed_lookup(clean_name: str) -> dict | None:
    """Seed lookup (normalized). Фемостон сначала обрабатывается по маске."""
    norm = _norm(clean_name)
    if not norm:
        return None

    m = _FEMOSTON_RE.match(clean_name.strip())
    if m:
        n = int(m.group(2)) if m.group(2) else 2
        d = int(m.group(3)) if m.group(3) else 10
        if n > 0 and d > 0:
            return _build_femoston(clean_name.strip(), n, d)
    if re.search(r"конти|conti", clean_name, re.IGNORECASE) and "фемостон" in norm:
        return _build_femoston(clean_name.strip(), 2, 10, continuous=True)

    for key, data in sorted(_LOCAL_SEED.items(), key=lambda kv: -len(kv[0])):
        nk = _norm(key)
        if not nk:
            continue
        if norm == nk or (len(nk) >= 4 and nk in norm) or (len(norm) >= 4 and norm in nk):
            return {"name": clean_name, **data}
    return None


def _payload(data: dict) -> dict:
    """Нормализованный ответ для формы: поля + components[] (без variant-less дублей)."""
    components = data.get("components") or []
    if not components and data.get("active_ingredient"):
        components = [{"name": data["active_ingredient"]}]
    payload = {k: v for k, v in data.items() if k != "components"}
    payload["components"] = components
    if not payload.get("active_ingredient") and components:
        payload["active_ingredient"] = " + ".join(dict.fromkeys(c.get("name", "") for c in components if c.get("name")))
    return payload


_LLM_SYSTEM = (
    "Ты — фармацевтический справочник. По торговому наименованию препарата/БАД верни "
    "только JSON без пояснений в формате: "
    '{"kind": "medication|supplement|supply|device", "form": string, "strength": string, '
    '"manufacturer": string|null, "storage_conditions": string|null, '
    '"prescription_required": bool, "instructions": string|null, '
    '"components": [{"name": "действующее вещество", "inn": "МНН или null", '
    '"amount": число-мг/мкг/МЕ на единицу или null, "unit": "мг|мкг|г|МЕ|мл" или null, '
    '"variant": "название таблетки в пачке если разные составы, иначе null"}]}. '
    "Правила: 1) указывай ТОЛЬКО реальные действующие вещества, никаких выдумок; если состав "
    "неизвестен — components: []. 2) Для витаминно-минеральных комплексов перечисли все значимые "
    "компоненты (до 20). 3) Если в пачке таблетки разного состава (например Фемостон 2/10) — "
    "раздели компоненты полем variant. 4) amount — дозировка НА ОДНУ единицу (таблетку/мл). "
    "5) Для косметики/расходников kind: supply. 6) Не выдумывай manufacturer/instructions — "
    "допустимо null. 7) Ответ — строго валидный JSON объект."
)


def _sanitize_llm(data: dict, clean_name: str) -> dict | None:
    if not isinstance(data, dict):
        return None
    comps_raw = data.get("components")
    components: list[dict] = []
    if isinstance(comps_raw, list):
        for c in comps_raw:
            if not isinstance(c, dict):
                continue
            name = (c.get("name") or "").strip()
            if not name:
                continue
            comp: dict = {"name": name, "inn": (c.get("inn") or "").strip() or None}
            amount = c.get("amount")
            if isinstance(amount, str):
                amount = amount.strip() or None
            try:
                amount = float(amount) if amount not in (None, "") else None
            except (TypeError, ValueError):
                amount = None
            if amount is not None:
                comp["amount"] = amount
            unit = (c.get("unit") or "").strip() or None
            if unit:
                comp["unit"] = unit
            variant = (c.get("variant") or "").strip() or None
            if variant:
                comp["variant"] = variant
            components.append(comp)
    if not components and not any(k in data for k in ("form", "strength", "kind")):
        return None
    kind = str(data.get("kind") or "medication").strip().lower()
    if kind not in ("medication", "supplement", "supply", "device"):
        kind = "medication"
    return {
        "name": clean_name,
        "kind": kind,
        "form": (str(data.get("form") or "")).strip() or None,
        "strength": (str(data.get("strength") or "")).strip() or None,
        "manufacturer": (str(data.get("manufacturer") or "")).strip() or None,
        "storage_conditions": (str(data.get("storage_conditions") or "")).strip() or None,
        "prescription_required": bool(data.get("prescription_required", False)),
        "instructions": (str(data.get("instructions") or "")).strip() or None,
        "components": components,
    }


async def _llm_enrich(db: AsyncSession, user_id: uuid.UUID, clean_name: str) -> dict | None:
    """Реальный LLM-разбор состава через BYOK-конфиг (json_mode + json_repair)."""
    try:
        from app.llm.client import call_llm
        from app.llm.pipeline import get_active_llm_config
        from app.llm.repair import parse_llm_json

        config = await get_active_llm_config(db, user_id, capability="text")
        if config is None:
            return None
        result = await call_llm(
            config,
            system_prompt=_LLM_SYSTEM,
            user_message=f"Наименование: {clean_name}",
            json_mode=True,
        )
        content = (result.get("content") or "").strip()
        if not content:
            return None
        try:
            parsed = parse_llm_json(content, is_last_attempt=True)
        except Exception as exc:  # noqa: BLE001 — repair исчерпан
            logger.warning("LLM pharma parse failed for %r: %s", clean_name, exc)
            return None
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            return None
        return _sanitize_llm(parsed, clean_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM pharma enrichment failed for %r: %s", clean_name, exc)
        return None


async def enrich_medication_info(
    db: AsyncSession,
    user_id: uuid.UUID,
    med_name: str,
    locale: str = "ru",
) -> dict | None:
    """Enrich medication master data by name.

    Returns full prefill payload (form fields + components[]) or ``None``
    (honest "not found" — caller decides how to tell the user).
    """
    clean_name = med_name.strip()
    if not clean_name:
        return None

    hit = _seed_lookup(clean_name)
    if hit is not None:
        return _payload(hit)

    llm = await _llm_enrich(db, user_id, clean_name)
    if llm is not None:
        return _payload(llm)

    return None
