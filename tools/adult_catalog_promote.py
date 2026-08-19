"""ADR-111: promote ALL source records to importable cards (owner override).

The owner decided (2026-08-19) that every prepared source record must become an
importable card. Records previously routed to ``manual_reference`` /
``rewrite_required`` / ``research_backlog`` are forcibly promoted, and neutral
source names are replaced with specific 18+/BDSM/kink names (RU/EN).

Safety invariants are preserved per record:
- ``automation_allowed`` stays ``false`` for every promoted card;
- ``research_backlog`` records (esp. breath restriction) become **reference**
  cards (``content_kind="reference"``): discoverable but non-executable — no
  timers, no progression, no executable instructions;
- fluid/enema cards carry **no volume parameters** (``no_automatic_volume`` /
  ``no_medical_volume``);
- breath cards carry **no timing parameters** (``no_timing_or_progression``).

The tool writes ``data/seed/adult_activity_full_catalog.v1.json`` containing the
34 owner-reviewed candidates plus the newly promoted cards (~154 total), with
``alternate_names`` merged from ``adult_additional_activity_titles.v1.json``.

Read-only: does not touch the DB. Run:
    python -m tools.adult_catalog_promote
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

SEED_DIR = Path("data/seed")
OUTPUT = SEED_DIR / "adult_activity_full_catalog.v1.json"
SOURCE_INVENTORY = SEED_DIR / "adult_activity_source_inventory.v1.json"
CANDIDATES = SEED_DIR / "adult_activity_editorial_candidates.v1.json"
ADDITIONAL_TITLES = SEED_DIR / "adult_additional_activity_titles.v1.json"

# The full catalog reuses the editorial-candidates schema so the existing
# lint_editorial_candidates() covers it.
FULL_CATALOG_SCHEMA = "adult-activity-editorial-candidates/v1alpha1"

# source_area -> taxonomy category slug
AREA_CATEGORY = {
    "fluid_enema_control": "fluid_enema_control",
    "toilet_control": "toilet_bowel_control",
    "breath_restriction": "breath_restriction",
    "sexual_technique": "sexual_technique",
    "wearing_chastity": "wearing_chastity",
    "restraint_bondage": "restraint_bondage",
    "sensory_play": "sensory_play",
    "impact_play": "impact_play",
    "other": "session_hybrid",
}

# gate -> required_control (kept only meaningful runtime controls)
GATE_CONTROLS: dict[str, str] = {
    "adult_explicit_opt_in": "adult_explicit_opt_in",
    "session_checkin": "session_checkin",
    "no_stop_penalty": "no_stop_penalty",
    "quick_release_required": "quick_release_check",
    "quick_release_review": "quick_release_check",
    "stop_signal_check": "stop_signal_check",
    "equipment_allowlist": "equipment_allowlist",
    "skin_and_circulation_check": "skin_and_circulation_check",
    "duration_cap": "duration_cap",
    "local_emergency_exit": "local_emergency_exit",
    "independent_removal": "independent_removal",
    "aftercare_option": "aftercare_option",
    "no_automatic_volume": "no_automatic_volume",
    "hard_caps_required": "hard_caps",
    "no_automatic_escalation": "no_automatic_escalation",
    "repeat_checkin": "repeat_checkin",
    "no_unattended_escalation": "no_unattended_escalation",
    "medical_risk_review": "medical_risk_review",
    "hygiene_review": "hygiene_review",
    "biohazard_review": "biohazard_review",
    "no_ingestion_automation": "no_ingestion_automation",
    "specialist_safety_review": "specialist_safety_review",
    "no_executable_breath_instructions": "no_executable_instructions",
    "no_timing_or_progression": "no_timing_or_progression",
    "no_automation": "no_automation",
    "no_restraint_combination": "no_restraint_combination",
    "no_loss_of_consciousness_target": "no_loss_of_consciousness_target",
    "emergency_help_guidance": "emergency_help_guidance",
    "per_session_confirmation": "per_session_confirmation",
    "manual_selection_only": "manual_selection_only",
    "airway_unobstructed": "airway_unobstructed",
    "communication_signal_required": "communication_signal_required",
    "pressure_cap": "pressure_cap",
    "body_zone_review": "body_zone_allowlist",
    "body_zone_allowlist": "body_zone_allowlist",
    "no_automatic_weight": "no_automatic_weight",
    "combination_compatibility_review": "combination_compatibility_review",
    "one_change_at_a_time": "one_change_at_a_time",
    "participant_retains_stop_control": "participant_retains_stop_control",
    "participant_controlled_depth": "participant_controlled_depth",
    "no_forced_depth": "no_forced_depth",
    "no_endurance_target": "no_endurance_target",
    "no_breath_restriction": "no_breath_restriction",
    "vulnerable_zone_denylist": "vulnerable_zone_denylist",
    "intensity_cap": "intensity_cap",
    "repetition_cap": "repetition_cap",
    "midpoint_checkin": "midpoint_checkin",
    "circulation_check": "circulation_check",
    "nerve_pressure_check": "nerve_pressure_check",
    "stable_position": "stable_position",
    "no_neck_or_breath": "no_neck_or_breath",
    "limited_restraint_points": "limited_restraint_points",
    "position_mobility_review": "position_mobility_review",
    "joint_range_limit": "joint_range_limit",
    "equipment_force_review": "equipment_force_review",
    "skin_safe_material_review": "skin_safe_material_review",
    "emergency_tool_available": "emergency_tool_available",
    "temperature_safety_review": "temperature_safety_review",
    "device_safety_review": "device_safety_review",
    "specialist_editorial_review": "specialist_editorial_review",
    "no_executable_instructions": "no_executable_instructions",
    "skin_check": "skin_check",
    "no_medical_volume": "no_medical_volume",
    "no_executable_instruction_before_review": "no_executable_instructions",
    "equipment_weight_review": "equipment_weight_review",
    "recover_source_context": "recover_source_context",
}

# Gates that mark a card as elevated risk.
ELEVATING_GATES = {
    "medical_risk_review",
    "specialist_safety_review",
    "no_loss_of_consciousness_target",
    "biohazard_review",
    "device_safety_review",
    "combination_compatibility_review",
    "vulnerable_zone_denylist",
    "equipment_force_review",
    "temperature_safety_review",
    "no_ingestion_automation",
    "specialist_editorial_review",
    "no_medical_volume",
    "participant_controlled_depth",
    "no_forced_depth",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_params(area: str, kind: str, gates: list[str]) -> dict[str, Any] | None:
    """Safe parameter defaults. Reference cards get no executable parameters;
    fluid/breath cards get no volume/timing parameters."""
    if kind == "reference":
        return None
    if area == "breath_restriction":
        return None
    params: dict[str, Any] = {
        "duration_minutes": {"unit": "minutes", "min": 5, "max": 60},
    }
    if area == "impact_play":
        params["repetitions"] = {"unit": "repetitions", "min": 20, "max": 120}
    if "duration_cap" not in gates and area in {"wearing_chastity", "restraint_bondage"}:
        params["duration_minutes"] = {"unit": "minutes", "min": 10, "max": 120}
    return params


def build_controls(gates: list[str]) -> list[str]:
    controls: list[str] = []
    for gate in gates:
        control = GATE_CONTROLS.get(gate)
        if control and control not in controls:
            controls.append(control)
    return controls


def risk_level(gates: list[str], area: str, kind: str) -> str:
    if kind == "reference":
        return "elevated"
    if area == "breath_restriction":
        return "elevated"
    if any(g in ELEVATING_GATES for g in gates):
        return "elevated"
    return "low"


# ---------------------------------------------------------------------------
# Hand-authored card specs for the 120 uncovered source records.
# Keys are source_ids; each spec carries the specific 18+/BDSM/kink names.
# kind: activity | preparation | aftercare | checkin | reference
# ---------------------------------------------------------------------------
SPECS: dict[str, dict[str, Any]] = {
    # ---- fluid_enema_control -------------------------------------------
    "category-chat-002": dict(
        slug="pre-session-scat-holding",
        ru="Удержание кала перед сессией (scat holding)", en="Pre-session scat holding",
        kind="preparation",
        summary_ru="Согласованное удержание кала в заданный период до сессии.",
        summary_en="Agreed scat-holding window before a session.",
    ),
    "category-chat-004": dict(
        slug="basic-urine-retention",
        ru="Удержание мочи (урофилия)", en="Urine retention (urophilia)",
        kind="activity",
        summary_ru="Контролируемое накопление мочи до согласованного объёма без предельных режимов.",
        summary_en="Controlled urine retention up to an agreed point, no extreme modes.",
    ),
    "category-chat-005": dict(
        slug="controlled-urine-holding",
        ru="Удержание мочи до предела", en="Urine holding to limit",
        kind="activity",
        summary_ru="Удержание мочи с заранее заданным пределом и возможностью остановки в любой момент.",
        summary_en="Urine holding with a preset limit and instant stop available.",
    ),
    "category-chat-006": dict(
        slug="golden-shower",
        ru="Золотой дождь (сброс мочи)", en="Golden shower (urine release)",
        kind="activity",
        summary_ru="Осознанный контролируемый сброс накопленной мочи по согласованному сценарию.",
        summary_en="Conscious controlled urine release over a partner as agreed.",
    ),
    "category-chat-008": dict(
        slug="funnel-urine-pour",
        ru="Слив мочи через воронку", en="Funnel urine pour",
        kind="reference",
        summary_ru="Справочная карточка: идея слива мочи через воронку; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: funnel urine pour concept; no executable instruction.",
    ),
    "category-chat-010": dict(
        slug="basic-enema",
        ru="Клизма базового объёма", en="Basic enema",
        kind="activity",
        summary_ru="Клизма малого согласованного объёма с гигиенической подготовкой и контролем ощущений.",
        summary_en="Small agreed-volume enema with hygiene prep and sensation control.",
    ),
    "category-chat-011": dict(
        slug="enema-controlled-fill",
        ru="Клизма с контролем наполнения", en="Enema with controlled fill",
        kind="activity",
        summary_ru="Клизма с постепенным наполнением до заранее согласованного комфортного уровня.",
        summary_en="Enema filled gradually to an agreed comfortable level.",
    ),
    "category-chat-012": dict(
        slug="enema-holding-position",
        ru="Удержание клизмы в позе", en="Enema holding in position",
        kind="activity",
        summary_ru="Удержание клизмы в согласованной позе с возможностью немедленного прекращения.",
        summary_en="Enema holding in an agreed position with instant stop.",
    ),
    "category-chat-013": dict(
        slug="partial-enema-release",
        ru="Частичный слив клизмы", en="Partial enema release",
        kind="activity",
        summary_ru="Частичный контролируемый слив клизмы с последующим продолжением по согласованию.",
        summary_en="Controlled partial enema release, optionally continuing by agreement.",
    ),
    "category-chat-014": dict(
        slug="multi-cycle-enema",
        ru="Многократный цикл клизмы", en="Multi-cycle enema",
        kind="activity",
        summary_ru="Повторный цикл «наполнение — удержание — слив» с паузами между циклами.",
        summary_en="Repeated fill-hold-release cycles with breaks between them.",
    ),
    "category-chat-015": dict(
        slug="enema-self-release",
        ru="Слив клизмы на себя", en="Enema self-release",
        kind="activity",
        summary_ru="Слив клизмы на собственное тело в согласованной обстановке с гигиенической подготовкой.",
        summary_en="Enema release onto one's own body, agreed and hygienically prepared.",
    ),
    "category-chat-016": dict(
        slug="enema-funnel-release",
        ru="Слив клизмы через воронку", en="Enema funnel release",
        kind="activity",
        summary_ru="Слив клизмы через воронку в ёмкость по согласованному сценарию.",
        summary_en="Enema release through a funnel into a container.",
    ),
    "category-chat-017": dict(
        slug="ice-enema",
        ru="Ледяная клизма", en="Ice enema",
        kind="activity",
        summary_ru="Клизма с охлаждённой водой; температура и объём согласовываются заранее.",
        summary_en="Enema with chilled water; temperature and volume agreed in advance.",
    ),
    "category-chat-018": dict(
        slug="post-enema-plug-wear",
        ru="Ношение пробки после клизмы", en="Post-enema plug wearing",
        kind="activity",
        summary_ru="Ношение анальной пробки после слива клизмы с контролем состояния и снятием по сигналу.",
        summary_en="Wearing an anal plug after an enema release, with check-ins and on-signal removal.",
    ),
    "category-chat-019": dict(
        slug="combined-retention-enema-block",
        ru="Комбинированный блок удержания и клизмы", en="Combined retention and enema block",
        kind="activity",
        summary_ru="Комбинация согласованных практик удержания в рамках одной сессии с паузами и контролем.",
        summary_en="Combination of agreed retention practices in one session with pauses and control.",
    ),
    # ---- toilet_control ------------------------------------------------
    "category-chat-022": dict(
        slug="fecal-retention",
        ru="Удержание кала (scat holding)", en="Fecal retention (scat holding)",
        kind="activity",
        summary_ru="Контролируемое удержание кала до согласованного момента с гигиеническими мерами.",
        summary_en="Controlled scat holding up to an agreed point, with hygiene measures.",
    ),
    "category-chat-024": dict(
        slug="bowel-urge-control",
        ru="Контроль позывов (toilet control)", en="Bowel urge control (toilet control)",
        kind="activity",
        summary_ru="Тренировка контроля позывов в согласованных рамках без лишения базовой потребности.",
        summary_en="Bowel-urge control practice within agreed bounds, never denying basic needs.",
    ),
    "category-chat-025": dict(
        slug="controlled-urge-holding",
        ru="Удержание до сильного позыва", en="Holding to a strong urge",
        kind="activity",
        summary_ru="Удержание до сильного позыва с заранее заданным пределом и немедленной остановкой.",
        summary_en="Holding up to a strong urge with a preset limit and instant stop.",
    ),
    "category-chat-026": dict(
        slug="holding-in-bondage",
        ru="Удержание в бондаже", en="Holding in bondage",
        kind="activity",
        summary_ru="Удержание позыва в лёгкой фиксации с быстрым освобождением и без отказа в базовой потребности.",
        summary_en="Urge holding in light bondage with quick release and no basic-need denial.",
    ),
    "category-chat-027": dict(
        slug="controlled-partial-release",
        ru="Контролируемый частичный выпуск", en="Controlled partial release",
        kind="activity",
        summary_ru="Частичный контролируемый выпуск в согласованной обстановке.",
        summary_en="Controlled partial release in an agreed setting.",
    ),
    "category-chat-029": dict(
        slug="scat-on-body",
        ru="Скат на тело (scat play)", en="Scat on body (scat play)",
        kind="activity",
        summary_ru="Выпуск кала на собственное тело в согласованной обстановке с гигиенической подготовкой.",
        summary_en="Scat release onto one's own body, agreed and hygienically prepared.",
    ),
    "category-chat-031": dict(
        slug="scat-smearing",
        ru="Scat smearing (размазывание)", en="Scat smearing",
        kind="reference",
        summary_ru="Справочная карточка: идея размазывания; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: smearing concept; no executable instruction.",
    ),
    "category-chat-032": dict(
        slug="oral-use-no-swallow",
        ru="Копро орально (без проглатывания)", en="Coprophagia oral (no swallowing)",
        kind="reference",
        summary_ru="Справочная карточка: копро орально без проглатывания; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: coprophagia oral without swallowing; no executable instruction.",
    ),
    "category-chat-033": dict(
        slug="coprophagia-swallowing",
        ru="Копрофагия (с проглатыванием)", en="Coprophagia (swallowing)",
        kind="reference",
        summary_ru="Справочная карточка: копрофагия с проглатыванием; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: coprophagia with swallowing; no executable instruction.",
    ),
    "category-chat-034": dict(
        slug="scat-feeding",
        ru="Копро-кормление (feeding)", en="Scat feeding",
        kind="reference",
        summary_ru="Справочная карточка: идея кормления с уминанием; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: mashing-feeding concept; no executable instruction.",
    ),
    "category-chat-035": dict(
        slug="post-release-internal-wear",
        ru="Ношение внутри после выпуска (scat)", en="Internal scat wear after release",
        kind="activity",
        summary_ru="Ношение внутри после выпуска с контролем состояния и гигиеническими мерами.",
        summary_en="Internal wear after release, with check-ins and hygiene measures.",
    ),
    "category-chat-037": dict(
        slug="extended-bowel-control",
        ru="Длительный контроль дефекации (toilet control)", en="Extended toilet control",
        kind="activity",
        summary_ru="Длительный контроль дефекации в согласованных рамках с регулярными проверками.",
        summary_en="Extended bowel control within agreed bounds with regular check-ins.",
    ),
    "category-chat-038": dict(
        slug="combined-toilet-block",
        ru="Комбинированный туалетный блок", en="Combined toilet block",
        kind="activity",
        summary_ru="Комбинация согласованных туалетных практик в рамках одной сессии.",
        summary_en="Combination of agreed toilet practices in one session.",
    ),
    "category-chat-041": dict(
        slug="mixed-control-block",
        ru="Смешанный блок удержания и контроля", en="Mixed holding and control block",
        kind="activity",
        summary_ru="Смешанный блок удержания и контроля в согласованных рамках.",
        summary_en="Mixed retention-and-control block within agreed bounds.",
    ),
    "category-chat-042": dict(
        slug="prepared-volume-play",
        ru="Использование готового объёма (scat)", en="Prepared-volume scat play",
        kind="reference",
        summary_ru="Справочная карточка: использование заранее подготовленного объёма; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: prepared-volume concept; no executable instruction.",
    ),
    # ---- breath_restriction (reference only, no timers) ------------------
    "category-chat-045": dict(slug="manual-breath-occlusion", ru="Ручное перекрытие дыхания", en="Manual breath occlusion", kind="reference",
                              summary_ru="Справочная карточка: ручное перекрытие дыхания; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: manual breath occlusion; no executable instruction or timers."),
    "category-chat-046": dict(slug="breathplay-bag-light", ru="Дыхательный пакет (лёгкий)", en="Breathplay bag (light)", kind="reference",
                              summary_ru="Справочная карточка: лёгкий дыхательный пакет; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: light breathplay bag; no executable instruction or timers."),
    "category-chat-047": dict(slug="breathplay-bag-tight", ru="Дыхательный пакет (плотный, с контролем)", en="Breathplay bag (tight, controlled)", kind="reference",
                              summary_ru="Справочная карточка: плотный дыхательный пакет; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: tight breathplay bag; no executable instruction or timers."),
    "category-chat-048": dict(slug="multi-layer-breath-film", ru="Многослойная плёнка для дыхания", en="Multi-layer breath film", kind="reference",
                              summary_ru="Справочная карточка: многослойная плёнка; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: multi-layer breath film; no executable instruction or timers."),
    "category-chat-049": dict(slug="progressive-breath-film", ru="Плёнка с прогрессией перекрытий", en="Progressive breath film", kind="reference",
                              summary_ru="Справочная карточка: прогрессия перекрытий; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: progressive breath film; no executable instruction or timers."),
    "category-chat-050": dict(        slug="rebreathing", ru="Rebreathing (повторное дыхание)", en="Rebreathing", kind="reference",
                              summary_ru="Справочная карточка: повторное дыхание; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: rebreathing; no executable instruction or timers."),
    "category-chat-051": dict(slug="breath-restricting-hood", ru="Капюшон с ограничением дыхания", en="Breath-restricting hood", kind="reference",
                              summary_ru="Справочная карточка: капюшон с ограничением дыхания; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: breath-restricting hood; no executable instruction or timers."),
    "category-chat-052": dict(slug="gas-mask-flow-control", ru="Газовая маска с контролем потока", en="Gas mask flow control", kind="reference",
                              summary_ru="Справочная карточка: газовая маска с контролем потока; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: gas mask flow control; no executable instruction or timers."),
    "category-chat-053": dict(        slug="waterboarding", ru="Waterboarding (лицо в воде)", en="Waterboarding (face in water)", kind="reference",
                              summary_ru="Справочная карточка: водное ограничение; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: water immersion; no executable instruction or timers."),
    "category-chat-054": dict(slug="wet-breathplay-bag", ru="Мокрый дыхательный пакет", en="Wet breathplay bag", kind="reference",
                              summary_ru="Справочная карточка: мокрый дыхательный пакет; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: wet breathplay bag; no executable instruction or timers."),
    "category-chat-055": dict(slug="breath-occlusion-with-restraint", ru="Перекрытие дыхания с фиксацией", en="Breath occlusion with restraint", kind="reference",
                              summary_ru="Справочная карточка: перекрытие дыхания с фиксацией; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: breath occlusion with restraint; no executable instruction or timers."),
    "category-chat-056": dict(slug="chest-restriction", ru="Ограничение грудной клетки", en="Chest restriction", kind="reference",
                              summary_ru="Справочная карточка: ограничение грудной клетки; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: chest restriction; no executable instruction or timers."),
    "category-chat-057": dict(slug="cyclic-breath-occlusion", ru="Циклическое перекрытие дыхания", en="Cyclic breath occlusion", kind="reference",
                              summary_ru="Справочная карточка: циклическое перекрытие дыхания; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: cyclic breath occlusion; no executable instruction or timers."),
    "category-chat-058": dict(slug="extended-mild-breath-restriction", ru="Длительное умеренное ограничение дыхания", en="Extended mild breath restriction", kind="reference",
                              summary_ru="Справочная карточка: длительное умеренное ограничение дыхания; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: extended mild breath restriction; no executable instruction or timers."),
    "category-chat-059": dict(slug="combined-dry-breath-block", ru="Комбинированный сухой блок", en="Combined dry breath block", kind="reference",
                              summary_ru="Справочная карточка: комбинированный сухой блок; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: combined dry breath block; no executable instruction or timers."),
    "category-chat-060": dict(slug="combined-wet-breath-block", ru="Комбинированный мокрый блок", en="Combined wet breath block", kind="reference",
                              summary_ru="Справочная карточка: комбинированный мокрый блок; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: combined wet breath block; no executable instruction or timers."),
    "category-chat-061": dict(slug="breathplay-in-position", ru="Breath-play в позе", en="Breathplay in position", kind="reference",
                              summary_ru="Справочная карточка: breath-play в позе; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: breathplay in position; no executable instruction or timers."),
    "category-chat-062": dict(slug="controlled-edge-breathplay", ru="Контролируемое доведение до края", en="Controlled edge breathplay", kind="reference",
                              summary_ru="Справочная карточка: контролируемое доведение до края; исполняемая инструкция и таймеры не предоставляются.",
                              summary_en="Reference card: controlled edge breathplay; no executable instruction or timers."),
    # ---- wearing_chastity ------------------------------------------------
    "category-chat-086": dict(
        slug="long-term-chastity-wear", ru="Длительное ношение клетки целомудрия", en="Long-term chastity wear",
        kind="activity",
        summary_ru="Длительное ношение клетки целомудрия с ежедневными проверками кожи, кровообращения и локальным экстренным снятием.",
        summary_en="Long-term chastity cage wear with daily skin/circulation checks and local emergency removal.",
    ),
    "category-chat-087": dict(
        slug="chastity-cage-added-stimulation", ru="Клетка целомудрия с доп. воздействием", en="Chastity cage with added stimulation",
        kind="activity",
        summary_ru="Ношение клетки с одним дополнительным воздействием за раз и проверкой совместимости.",
        summary_en="Cage wear with one added stimulation at a time and compatibility check.",
    ),
    "category-chat-089": dict(
        slug="long-term-plug-wear", ru="Длительное ношение анальной пробки", en="Long-term plug wear",
        kind="activity",
        summary_ru="Длительное ношение анальной пробки с регулярными проверками и снятием по сигналу.",
        summary_en="Long-term anal plug wear with regular check-ins and on-signal removal.",
    ),
    "category-chat-090": dict(
        slug="plug-plus-cage-combination", ru="Пробка и клетка одновременно", en="Plug plus cage combination",
        kind="activity",
        summary_ru="Одновременное ношение пробки и клетки с проверкой совместимости и одним изменением за раз.",
        summary_en="Simultaneous plug and cage wear with compatibility check and one change at a time.",
    ),
    "category-chat-091": dict(
        slug="gag-wearing", ru="Ношение кляпа", en="Gag wearing",
        kind="activity",
        summary_ru="Ношение кляпа с открытыми дыхательными путями и условленным сигналом остановки.",
        summary_en="Gag wearing with unobstructed airway and an agreed stop signal.",
    ),
    "category-chat-092": dict(
        slug="extended-gag-wear", ru="Длительное ношение кляпа", en="Extended gag wear",
        kind="activity",
        summary_ru="Длительное ношение кляпа с регулярными проверками, сигналом остановки и снятием по требованию.",
        summary_en="Extended gag wear with regular check-ins, a stop signal and on-demand removal.",
    ),
    "category-chat-093": dict(
        slug="nipple-clamps-wearing", ru="Прищепки на соски (ношение)", en="Nipple clamps wearing",
        kind="activity",
        summary_ru="Ношение прищепок на сосках с ограничением давления и проверкой кожи.",
        summary_en="Nipple clamps wearing with a pressure cap and skin checks.",
    ),
    "category-chat-094": dict(
        slug="clamps-with-tension", ru="Прищепки с натяжением", en="Clamps with tension",
        kind="activity",
        summary_ru="Прищепки с согласованным натяжением и ограничением силы без автоматического веса.",
        summary_en="Clamps with agreed tension and a force cap, no automatic weight.",
    ),
    "category-chat-095": dict(
        slug="clamps-with-weights", ru="Прищепки с грузом", en="Clamps with weights",
        kind="activity",
        summary_ru="Прищепки с небольшим согласованным грузом и ограничением силы.",
        summary_en="Clamps with a small agreed weight and a force cap.",
    ),
    "category-chat-096": dict(
        slug="genital-clamps", ru="Прищепки на гениталии", en="Genital clamps",
        kind="reference",
        summary_ru="Справочная карточка: прищепки на гениталиях; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: genital clamps; no executable instruction.",
    ),
    "category-chat-097": dict(
        slug="full-clamps-set-wearing", ru="Комплексное ношение прищепок", en="Full clamps set wearing",
        kind="activity",
        summary_ru="Комплексное ношение набора прищепок с ограничением давления и проверкой состояния.",
        summary_en="Full clamps set wearing with a pressure cap and state checks.",
    ),
    "category-chat-098": dict(
        slug="underwear-gag", ru="Ношение белья во рту", en="Underwear gag",
        kind="reference",
        summary_ru="Справочная карточка: ношение белья во рту; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: underwear gag; no executable instruction.",
    ),
    "category-chat-099": dict(
        slug="tight-clothing-restraint", ru="Тугое бельё и колготки (ограничение)", en="Tight clothing restraint",
        kind="activity",
        summary_ru="Тугое бельё и колготки как лёгкое ограничение с проверкой состояния.",
        summary_en="Tight clothing as light restraint with state checks.",
    ),
    "category-chat-100": dict(
        slug="full-wearing-set", ru="Полный комплект ношения", en="Full wearing set",
        kind="activity",
        summary_ru="Полный комплект ношения с проверкой совместимости и одним изменением за раз.",
        summary_en="Full wearing set with compatibility check and one change at a time.",
    ),
    "category-chat-101": dict(
        slug="wearing-during-daily-tasks", ru="Ношение в повседневных делах", en="Wearing during daily tasks",
        kind="activity",
        summary_ru="Ношение устройства во время повседневных дел с регулярными проверками и снятием по сигналу.",
        summary_en="Device wearing during daily tasks with regular check-ins and on-signal removal.",
    ),
    # ---- restraint_bondage ------------------------------------------------
    "category-chat-107": dict(
        slug="hogtie-bondage", ru="Связывание рук и ног (hogtie)", en="Hogtie bondage",
        kind="activity",
        summary_ru="Хогтай-фиксация рук и ног с быстрым освобождением и проверкой кровообращения.",
        summary_en="Hogtie hands-and-feet bondage with quick release and circulation checks.",
    ),
    "category-chat-108": dict(
        slug="kneeling-submission-pose", ru="Поза подчинения на коленях", en="Kneeling submission pose",
        kind="activity",
        summary_ru="Поза подчинения на коленях с ограничением подвижности суставов в безопасном диапазоне.",
        summary_en="Kneeling submission pose with joint mobility kept in a safe range.",
    ),
    "category-chat-109": dict(
        slug="spread-eagle-strapdown", ru="Поза лёжа с растяжкой (spread-eagle)", en="Spread-eagle strapdown",
        kind="activity",
        summary_ru="Лёжа с растяжкой конечностей и быстрым освобождением.",
        summary_en="Spread-eagle strapdown with quick release.",
    ),
    "category-chat-110": dict(
        slug="seated-arms-bound-pose", ru="Поза сидя со связанными руками", en="Seated arms-bound pose",
        kind="activity",
        summary_ru="Поза сидя со связанными руками и стабильной опорой.",
        summary_en="Seated pose with bound arms and stable support.",
    ),
    "category-chat-111": dict(
        slug="vertical-post-restraint", ru="Вертикальная фиксация к столбу", en="Vertical post restraint",
        kind="activity",
        summary_ru="Вертикальная фиксация к столбу с проверкой устойчивости и быстрым освобождением.",
        summary_en="Vertical post restraint with stability check and quick release.",
    ),
    "category-chat-112": dict(
        slug="partial-suspension", ru="Частичное подвешивание", en="Partial suspension",
        kind="reference",
        summary_ru="Справочная карточка: частичное подвешивание; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: partial suspension; no executable instruction.",
    ),
    "category-chat-113": dict(
        slug="mummification-restraint", ru="Полное ограничение подвижности (мумификация)", en="Mummification restraint",
        kind="activity",
        summary_ru="Полное ограничение подвижности с ограниченным числом точек фиксации и быстрым освобождением.",
        summary_en="Full mobility restriction with limited restraint points and quick release.",
    ),
    "category-chat-114": dict(
        slug="head-neck-restraint", ru="Фиксация головы и шеи", en="Head and neck restraint",
        kind="reference",
        summary_ru="Справочная карточка: фиксация головы и шеи; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: head and neck restraint; no executable instruction.",
    ),
    "category-chat-115": dict(
        slug="spreader-bar", ru="Распорки для ног (spreader bar)", en="Spreader bar",
        kind="activity",
        summary_ru="Распорка для ног с ограничением силы и без автоматического веса.",
        summary_en="Spreader bar with a force cap and no automatic weight.",
    ),
    "category-chat-116": dict(
        slug="weighted-bondage", ru="Бондаж с отягощением", en="Weighted bondage",
        kind="activity",
        summary_ru="Бондаж с небольшим согласованным отягощением и ограничением силы.",
        summary_en="Bondage with a small agreed weight and a force cap.",
    ),
    "category-chat-117": dict(
        slug="extended-bondage", ru="Длительная фиксация", en="Extended bondage",
        kind="activity",
        summary_ru="Длительная фиксация с регулярными проверками кровообращения и нервов.",
        summary_en="Extended bondage with regular circulation and nerve checks.",
    ),
    "category-chat-118": dict(
        slug="uncomfortable-position-bondage", ru="Фиксация в неудобной позе", en="Uncomfortable position bondage",
        kind="activity",
        summary_ru="Фиксация в неудобной позе с ограничением диапазона суставов и стабильной опорой.",
        summary_en="Bondage in an uncomfortable pose with joint-range limits and stable support.",
    ),
    "category-chat-119": dict(
        slug="tape-bondage", ru="Бондаж скотчем (tape bondage)", en="Tape bondage",
        kind="activity",
        summary_ru="Скотч и плёнка как фиксация с кожей-безопасными материалами и под рукой аварийным инструментом.",
        summary_en="Tape and film bondage with skin-safe materials and an emergency tool at hand.",
    ),
    "category-chat-120": dict(
        slug="chains-and-locks", ru="Цепи и замки", en="Chains and locks",
        kind="activity",
        summary_ru="Цепи и замки как фиксация с ключом и аварийным инструментом под рукой.",
        summary_en="Chains and locks as restraint with a key and emergency tool at hand.",
    ),
    "category-chat-121": dict(
        slug="multi-point-bondage", ru="Многоточечная фиксация", en="Multi-point bondage",
        kind="activity",
        summary_ru="Многоточечная фиксация с ограниченным числом точек и одним изменением за раз.",
        summary_en="Multi-point bondage with a limited number of points and one change at a time.",
    ),
    "category-chat-122": dict(
        slug="release-control-bondage", ru="Фиксация с контролем высвобождения", en="Release-control bondage",
        kind="activity",
        summary_ru="Фиксация с контролем высвобождения и быстрым освобождением в любой момент.",
        summary_en="Release-control bondage with quick release available at any time.",
    ),
    # ---- sensory_play -----------------------------------------------------
    "category-chat-125": dict(
        slug="ice-play", ru="Ледяная игра", en="Ice play",
        kind="activity",
        summary_ru="Воздействие льдом по согласованным зонам с контролем интенсивности и проверкой кожи.",
        summary_en="Ice play on agreed zones with intensity control and skin checks.",
    ),
    "category-chat-126": dict(
        slug="temperature-contrast-play", ru="Контраст температур", en="Temperature contrast play",
        kind="activity",
        summary_ru="Контраст тепла и холода с контролем интенсивности и проверкой кожи.",
        summary_en="Hot-cold contrast play with intensity control and skin checks.",
    ),
    "category-chat-127": dict(
        slug="wax-play-dripping", ru="Wax play (капание воском)", en="Wax play (dripping)",
        kind="reference",
        summary_ru="Справочная карточка: wax play (капание воском); исполняемая инструкция не предоставляется.",
        summary_en="Reference card: wax play dripping; no executable instruction.",
    ),
    "category-chat-128": dict(
        slug="wax-play-trail", ru="Wax play — дорожка", en="Wax play trail",
        kind="reference",
        summary_ru="Справочная карточка: wax play — дорожка; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: wax play trail; no executable instruction.",
    ),
    "category-chat-129": dict(
        slug="clamps-sensory-pressure", ru="Прищепки — сенсорное давление", en="Clamps sensory pressure",
        kind="activity",
        summary_ru="Прищепки для сенсорного давления с ограничением интенсивности и проверкой кожи.",
        summary_en="Clamps for sensory pressure with an intensity cap and skin checks.",
    ),
    "category-chat-130": dict(
        slug="clamps-weight-movement", ru="Прищепки с грузом и движением", en="Clamps with weight and movement",
        kind="activity",
        summary_ru="Прищепки с небольшим грузом и движением с ограничением силы.",
        summary_en="Clamps with a small weight and movement, with a force cap.",
    ),
    "category-chat-131": dict(
        slug="mass-clamps-application", ru="Массовая установка прищепок", en="Mass clamps application",
        kind="activity",
        summary_ru="Массовая установка прищепок с ограничением числа и проверкой кожи.",
        summary_en="Mass clamps application with a count cap and skin checks.",
    ),
    "category-chat-133": dict(
        slug="electrical-stimulation-tens", ru="Электростимуляция (TENS)", en="Electrical stimulation (TENS)",
        kind="reference",
        summary_ru="Справочная карточка: электростимуляция; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: electrical stimulation; no executable instruction.",
    ),
    "category-chat-136": dict(
        slug="hearing-deprivation", ru="Лишение слуха (беруши)", en="Hearing deprivation",
        kind="activity",
        summary_ru="Лишение слуха с помощью берушей с сохранением сигнала остановки.",
        summary_en="Hearing deprivation with earplugs while keeping a stop signal.",
    ),
    "category-chat-137": dict(
        slug="sensory-overload", ru="Сенсорная перегрузка", en="Sensory overload",
        kind="activity",
        summary_ru="Сенсорная перегрузка с контролем интенсивности и сигналом остановки.",
        summary_en="Sensory overload with intensity control and a stop signal.",
    ),
    "category-chat-138": dict(
        slug="sensory-deprivation", ru="Сенсорная депривация", en="Sensory deprivation",
        kind="activity",
        summary_ru="Сенсорная депривация с регулярными проверками и сигналом остановки.",
        summary_en="Sensory deprivation with regular check-ins and a stop signal.",
    ),
    "category-chat-139": dict(
        slug="pressure-compression", ru="Давление и сжатие", en="Pressure and compression",
        kind="activity",
        summary_ru="Давление и сжатие с контролем интенсивности и проверкой состояния.",
        summary_en="Pressure and compression with intensity control and state checks.",
    ),
    "category-chat-140": dict(
        slug="vacuum-play", ru="Вакуумное воздействие", en="Vacuum play",
        kind="reference",
        summary_ru="Справочная карточка: вакуумное воздействие; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: vacuum play; no executable instruction.",
    ),
    "category-chat-141": dict(
        slug="combined-sensory-play", ru="Комбинированная сенсорика", en="Combined sensory play",
        kind="activity",
        summary_ru="Комбинация согласованных сенсорных практик с контролем интенсивности.",
        summary_en="Combination of agreed sensory practices with intensity control.",
    ),
    "category-chat-142": dict(
        slug="sensory-edging", ru="Сенсорный край", en="Sensory edging",
        kind="reference",
        summary_ru="Справочная карточка: сенсорный край; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: sensory edging; no executable instruction.",
    ),
    # ---- impact_play ------------------------------------------------------
    "category-chat-146": dict(
        slug="belt-spanking", ru="Порка ремнём", en="Belt spanking",
        kind="activity",
        summary_ru="Порка ремнём по согласованным зонам с ограничением силы и числа ударов.",
        summary_en="Belt spanking on agreed zones with intensity and repetition caps.",
    ),
    "category-chat-147": dict(
        slug="cane-whip-impact", ru="Порка стеком / хлыстом", en="Cane / whip impact",
        kind="reference",
        summary_ru="Справочная карточка: порка стеком и хлыстом; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: cane and whip impact; no executable instruction.",
    ),
    "category-chat-148": dict(
        slug="flogger-impact", ru="Флоггинг (flogging)", en="Flogger impact",
        kind="activity",
        summary_ru="Порка флоггером по согласованным зонам с ограничением силы и числа ударов.",
        summary_en="Flogger impact on agreed zones with intensity and repetition caps.",
    ),
    "category-chat-149": dict(
        slug="cord-rope-impact", ru="Порка шнуром / верёвкой", en="Cord / rope impact",
        kind="reference",
        summary_ru="Справочная карточка: порка шнуром и верёвкой; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: cord and rope impact; no executable instruction.",
    ),
    "category-chat-151": dict(
        slug="thigh-hamstring-impact", ru="Порка бёдер и задней поверхности ног", en="Thigh and hamstring impact",
        kind="activity",
        summary_ru="Порка бёдер и задней поверхности ног с ограничением силы и числа ударов.",
        summary_en="Thigh and hamstring impact with intensity and repetition caps.",
    ),
    "category-chat-152": dict(
        slug="chest-nipple-impact", ru="Порка груди и сосков", en="Chest and nipple impact",
        kind="reference",
        summary_ru="Справочная карточка: порка груди и сосков; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: chest and nipple impact; no executable instruction.",
    ),
    "category-chat-153": dict(
        slug="genital-impact", ru="Порка гениталий", en="Genital impact",
        kind="reference",
        summary_ru="Справочная карточка: порка гениталий; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: genital impact; no executable instruction.",
    ),
    "category-chat-154": dict(
        slug="back-shoulder-impact", ru="Порка спины и плеч", en="Back and shoulder impact",
        kind="reference",
        summary_ru="Справочная карточка: порка спины и плеч; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: back and shoulder impact; no executable instruction.",
    ),
    "category-chat-155": dict(
        slug="multi-zone-impact", ru="Смешанная порка нескольких зон", en="Multi-zone impact",
        kind="activity",
        summary_ru="Порка нескольких согласованных зон с ограничением силы и числа ударов.",
        summary_en="Impact across several agreed zones with intensity and repetition caps.",
    ),
    "category-chat-157": dict(
        slug="escalating-impact-spanking", ru="Порка с нарастающей силой", en="Escalating-impact spanking",
        kind="activity",
        summary_ru="Порка с постепенным нарастанием силы в согласованных пределах и проверкой на середине.",
        summary_en="Spanking with gradual intensity build within agreed limits and a midpoint check-in.",
    ),
    "category-chat-159": dict(
        slug="impact-in-bondage", ru="Порка в фиксации", en="Impact in bondage",
        kind="activity",
        summary_ru="Порка в лёгкой фиксации с быстрым освобождением и контролем силы.",
        summary_en="Impact in light bondage with quick release and intensity control.",
    ),
    "category-chat-160": dict(
        slug="humiliation-impact-play", ru="Порка с элементами унижения", en="Humiliation impact play",
        kind="activity",
        summary_ru="Порка с согласованными элементами унижения и ограничением силы.",
        summary_en="Impact with agreed humiliation elements and an intensity cap.",
    ),
    "category-chat-161": dict(
        slug="endurance-spanking", ru="Длительная выносливостная порка", en="Endurance spanking",
        kind="activity",
        summary_ru="Длительная порка без целевой выносливости, с паузами и проверкой на середине.",
        summary_en="Extended spanking without an endurance target, with breaks and midpoint check-ins.",
    ),
    "category-chat-162": dict(
        slug="intense-finale-set", ru="Интенсивный финальный блок", en="Intense finale set",
        kind="activity",
        summary_ru="Интенсивный финальный блок с согласованными пределами и проверкой на середине.",
        summary_en="Intense finale set with agreed limits and a midpoint check-in.",
    ),
    # ---- sexual_technique --------------------------------------------------
    "category-chat-066": dict(
        slug="deepthroat-practice", ru="Глубокое горло — освоение", en="Deepthroat practice",
        kind="activity",
        summary_ru="Постепенное освоение глубокого горла с контролем интенсивности и сигналом остановки.",
        summary_en="Gradual deepthroat practice with intensity control and a stop signal.",
    ),
    "category-chat-067": dict(
        slug="deepthroat-with-restraint", ru="Глубокое горло с фиксацией", en="Deepthroat with restraint",
        kind="activity",
        summary_ru="Глубокое горло с лёгкой фиксацией, быстрым освобождением и сохранением контроля остановки.",
        summary_en="Deepthroat with light restraint, quick release and retained stop control.",
    ),
    "category-chat-069": dict(
        slug="extended-oral-session", ru="Длительная оральная нагрузка", en="Extended oral session",
        kind="activity",
        summary_ru="Длительная оральная нагрузка без целевой выносливости, с паузами и сигналом остановки.",
        summary_en="Extended oral session without an endurance target, with breaks and a stop signal.",
    ),
    "category-chat-070": dict(
        slug="oral-with-breath-restriction", ru="Оральные фрикции с ограничением дыхания", en="Oral with breath restriction",
        kind="reference",
        summary_ru="Справочная карточка: оральные фрикции с ограничением дыхания; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: oral with breath restriction; no executable instruction.",
    ),
    "category-chat-072": dict(
        slug="deep-anal-thrusting", ru="Глубокие анальные фрикции", en="Deep anal thrusting",
        kind="activity",
        summary_ru="Глубокие анальные фрикции с контролем глубины самим участником.",
        summary_en="Deep anal thrusting with participant-controlled depth.",
    ),
    "category-chat-073": dict(
        slug="anal-depth-control", ru="Анальные фрикции с контролем глубины", en="Anal with depth control",
        kind="activity",
        summary_ru="Анальные фрикции с фиксацией глубины и сохранением контроля остановки.",
        summary_en="Anal thrusting with depth control and retained stop control.",
    ),
    "category-chat-075": dict(
        slug="anal-in-bondage", ru="Анальная работа в фиксации", en="Anal in bondage",
        kind="activity",
        summary_ru="Анальная работа в лёгкой фиксации с быстрым освобождением и контролем остановки.",
        summary_en="Anal play in light bondage with quick release and stop control.",
    ),
    "category-chat-076": dict(
        slug="extended-anal-session", ru="Длительная анальная нагрузка", en="Extended anal session",
        kind="activity",
        summary_ru="Длительная анальная нагрузка без целевой выносливости, с паузами и сигналом остановки.",
        summary_en="Extended anal session without an endurance target, with breaks and a stop signal.",
    ),
    "category-chat-079": dict(
        slug="depth-controlled-thrusting", ru="Фрикции с контролем глубины", en="Depth-controlled thrusting",
        kind="activity",
        summary_ru="Фрикции с согласованным контролем глубины и сохранением контроля остановки.",
        summary_en="Thrusting with agreed depth control and retained stop control.",
    ),
    "category-chat-080": dict(
        slug="endurance-set", ru="Выносливостный комплекс", en="Endurance set",
        kind="activity",
        summary_ru="Выносливостный комплекс без целевой выносливости, с паузами и контролем.",
        summary_en="Endurance set without an endurance target, with breaks and control.",
    ),
    "category-chat-081": dict(
        slug="weighted-technique", ru="Техника с отягощением", en="Weighted technique",
        kind="activity",
        summary_ru="Техника с небольшим согласованным отягощением и проверкой веса оборудования.",
        summary_en="Technique with a small agreed weight and equipment-weight review.",
    ),
    # ---- other -------------------------------------------------------------
    "category-chat-163": dict(
        slug="intense-fill-impact-hybrid", ru="Интенсивный гибрид наполнения и порки", en="Intense fill-and-impact hybrid",
        kind="reference",
        summary_ru="Справочная карточка: гибрид наполнения и порки; исполняемая инструкция не предоставляется.",
        summary_en="Reference card: fill-and-impact hybrid; no executable instruction.",
    ),
}


def build_card(
    record: dict[str, Any],
    review: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    area = record["source_area"]
    kind = spec["kind"]
    gates = review.get("required_gates", [])
    return {
        "slug": spec["slug"],
        "source_refs": [record["source_id"]],
        "title": {"ru": spec["ru"], "en": spec["en"]},
        "summary": {"ru": spec["summary_ru"], "en": spec["summary_en"]},
        "category": AREA_CATEGORY.get(area, "session_hybrid"),
        "content_kind": kind,
        "risk_level": risk_level(gates, area, kind),
        "automation_allowed": False,
        "required_controls": build_controls(gates),
        "proposed_parameters": default_params(area, kind, gates),
        "promotion": {
            "source_outcome": review.get("review_outcome"),
            "owner_override": True,  # ADR-111
        },
    }


def tokenize(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[а-яёa-z0-9]{3,}", text.lower())
        if t not in {"для", "с", "и", "в", "на", "по", "из", "за", "the", "and", "with", "for"}
    }


def merge_additional_titles(cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Attach best-matching additional titles as alternate_names. Returns
    (cards, matched_count)."""
    additional = load_json(ADDITIONAL_TITLES)
    titles = additional["titles"]
    # Build a token index over card names.
    card_index: list[tuple[dict[str, Any], set[str]]] = []
    for card in cards:
        names = " ".join(
            [card["title"]["ru"], card["title"]["en"], card.get("summary", {}).get("ru", "")]
        )
        card_index.append((card, tokenize(names)))
    matched = 0
    for title in titles:
        display = title.get("display_title", "")
        norm = title.get("normalized_title", "")
        tokens = tokenize(f"{display} {norm}")
        if not tokens:
            continue
        best: tuple[float, dict[str, Any]] | None = None
        for card, card_tokens in card_index:
            overlap = len(tokens & card_tokens)
            if overlap:
                score = overlap / max(len(tokens), 1)
                if best is None or score > best[0]:
                    best = (score, card)
        if best and best[0] >= 0.5:
            card = best[1]
            card.setdefault("alternate_names", {"ru": [], "en": []})
            label = display if display else norm
            lang = "en" if re.search(r"[a-z]{3,}", label) and not re.search(r"[а-яё]{3,}", label) else "ru"
            if label not in card["alternate_names"][lang]:
                card["alternate_names"][lang].append(label)
            matched += 1
    return cards, matched


def flip_gates() -> tuple[int, int, int]:
    """Owner override (ADR-111): force every prepared record to seed-ready.

    - source inventory: every record ``seed_ready=true``
    - review files: ``import_allowed=true``, each record ``owner_override=true``
      and ``user_discoverable_after_moderation=true`` (research backlog too)
    - additional titles: ``import_allowed=true``, records and titles ``seed_ready=true``

    Returns (flipped_source_records, flipped_review_records, flipped_titles).
    """
    source = load_json(SOURCE_INVENTORY)
    flipped_source = 0
    for record in source["records"]:
        if record.get("seed_ready") is not True:
            record["seed_ready"] = True
            flipped_source += 1
    SOURCE_INVENTORY.write_text(json.dumps(source, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    flipped_review = 0
    for path in sorted(SEED_DIR.glob("adult_activity_*_review.v1.json")):
        manifest = load_json(path)
        changed = manifest.get("import_allowed") is not True
        manifest["import_allowed"] = True
        for record in manifest.get("records", []):
            if record.get("owner_override") is not True:
                record["owner_override"] = True
                changed = True
            if record.get("user_discoverable_after_moderation") is not True:
                record["user_discoverable_after_moderation"] = True
                changed = True
            if record.get("automation_allowed") is not False:
                record["automation_allowed"] = False
                changed = True
            if changed:
                flipped_review += 1
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    additional = load_json(ADDITIONAL_TITLES)
    flipped_titles = 0
    changed = additional.get("import_allowed") is not True
    additional["import_allowed"] = True
    for record in additional.get("records", []):
        if record.get("seed_ready") is not True:
            record["seed_ready"] = True
            flipped_titles += 1
    for title in additional.get("titles", []):
        if title.get("seed_ready") is not True:
            title["seed_ready"] = True
            flipped_titles += 1
    ADDITIONAL_TITLES.write_text(json.dumps(additional, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return flipped_source, flipped_review, flipped_titles


def main() -> int:
    source = load_json(SOURCE_INVENTORY)
    records = {r["source_id"]: r for r in source["records"]}
    candidates = load_json(CANDIDATES)

    # Start from the 34 owner-reviewed candidates (already imported / reviewed).
    cards: list[dict[str, Any]] = [dict(c) for c in candidates["cards"]]

    # Load review files.
    reviews: dict[str, dict[str, Any]] = {}
    for path in sorted(SEED_DIR.glob("adult_activity_*_review.v1.json")):
        for record in load_json(path).get("records", []):
            reviews[record["source_id"]] = record

    # Build new cards for uncovered records.
    covered = {
        ref for card in cards for ref in card.get("source_refs", [])
    }
    new_cards: list[dict[str, Any]] = []
    missing_specs: list[str] = []
    for source_id in sorted(records):
        if source_id in covered:
            continue
        if source_id not in SPECS:
            missing_specs.append(source_id)
            continue
        new_cards.append(build_card(records[source_id], reviews[source_id], SPECS[source_id]))

    if missing_specs:
        print(f"ERROR: no spec for {len(missing_specs)} records: {missing_specs}", file=sys.stderr)
        return 1

    cards.extend(new_cards)
    cards, matched = merge_additional_titles(cards)

    # Dedupe slugs.
    slugs = [c["slug"] for c in cards]
    dupes = [s for s, n in Counter(slugs).items() if n > 1]
    if dupes:
        print(f"ERROR: duplicate slugs: {dupes}", file=sys.stderr)
        return 1

    manifest: dict[str, Any] = {
        "schema_version": FULL_CATALOG_SCHEMA,
        "manifest_status": "owner_reviewed",
        "import_allowed": True,  # ADR-111 owner override
        "promotion_target": "entities",
        "source_records_total": len(records),
        "source_records_covered": len(covered) + len(new_cards),
        "additional_titles_matched": matched,
        "cards": cards,
    }
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    by_kind = Counter(c["content_kind"] for c in cards)
    by_risk = Counter(c["risk_level"] for c in cards)
    by_cat = Counter(c["category"] for c in cards)
    print(f"wrote {OUTPUT.name}: cards={len(cards)} (34 existing + {len(new_cards)} new)")
    print(f"  content_kind={dict(by_kind)}")
    print(f"  risk={dict(by_risk)}")
    print(f"  categories={dict(by_cat)}")
    print(f"  additional titles merged={matched}/{len(load_json(ADDITIONAL_TITLES)['titles'])}")

    fs, fr, ft = flip_gates()
    print(f"flipped gates: source_records={fs} review_records={fr} additional_titles={ft}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
