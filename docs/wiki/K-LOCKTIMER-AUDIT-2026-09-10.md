---
schema_version: memory/v2alpha1
id: K-LOCKTIMER-AUDIT-SUMMARY-2026-09-10
kind: knowledge
title: Результаты сопоставления LockTimer с исходным замыслом
status: active
authority: derived
owners:
  - project-owner
scope:
  - locktimer/core
  - locktimer/verification
  - locktimer/penalty
source_refs:
  - path: docs/audits/LOCKTIMER_AUDIT_2026-09-10.md
    relation: supports
  - path: examples/LT/docs/LockTimer_Project_Summary.md
    relation: origin
  - path: app/locktimer/services/materializer.py
    relation: implements
  - path: app/locktimer/services/execution.py
    relation: implements
  - path: app/reminders/engine.py
    relation: implements
last_verified_at: 2026-09-10T00:00:00Z
last_verified_commit: 36c5541ebb71f772c4c5dba891af08df35b797f5
review_on: source-change
---

# Аудит LockTimer — краткая память

Полный результат: [аудит 2026-09-10](../audits/LOCKTIMER_AUDIT_2026-09-10.md).
Работа ограничена обзором: код и продуктовые решения не изменялись.

## Основной вывод

В портале есть развитые свободное ношение, игры, дисциплина и Telegram, но базовый
планировщик, внутренние периоды и управляемая неизвестность остаются частичными.
Срок, фактическая отметка ношения, проверки и последствия меняются несколькими
несогласованными путями. Предложено сначала унифицировать исполнение, затем
реализовать гибкие фазы, рабочий график и разрешённые событийные сценарии.
Это рекомендации, не принятые ADR.

## Подтверждения

- 191 существующий тест в 16 файлах прошёл на Python 3.13 / SQLite за 55.89s.
- Отдельно без БД воспроизведены: неверное время для Europe/Moscow; одинаковые
  occurrence keys у разных диапазонов; ноль событий after_previous_close;
  уже просроченная daily-задача при старте; принятие LLM proposal с n=0.
- PostgreSQL, живой браузер и реальные OCR/LLM в этом аудите не проверялись.

## Ключевые находки по коду

- A01: срок от запуска считается при сохранении черновика; `None` не очищает
  конечную дату при переходе в свободный режим.
- A02–A05: start не запускает полную валидацию; конфликты не вычисляются;
  snapshot неполный; refill повторяет ключи; автоматический жизненный цикл
  scheduled/expired/completed не замкнут. Обычная scheduled-задача может быть
  видимой без кнопок reveal/complete.
- A06–A08: плановые окна не синхронизируют состояние свободного ношения;
  действия occurrences не проверяют активность родителя; часть штрафов только
  записывается; прибавка времени при freeze теряется после unfreeze;
  разные пути обходят выбранные пределы времени.
- A09–A10: report/media policy не включены в сдачу timer task; новый session
  photo endpoint подтверждает ручной код, не выполняя отдельные ai/community/
  keyholder pipelines; инспекция меняет текущую бирку без сравнения.
  Эмуляция допустима по ADR-129, но должна честно отличаться от проверки фото.
- A11–A13: шаблон теряет политики/срок; применение дописывает правила в
  singleton draft; часть LLM items получает applied без эффекта; выключатели
  игр не проверяются сервисом; XP в игровом журнале не равен транзакции баланса.
- A14: напоминания читают `verification_interval_hours` (default 6) вместо
  `verification_frequency_hours` и не проверяют `verification_required`.
- A15–A18: Timer Social adapter неполный; история берёт первые 100 событий;
  test_timer_standalone сам не запускает отдельную timer-композицию;
  fallback выбора штрафного Entity не проверяет opt-in.

## Как использовать

Перед исправлением читать соответствующий A01–A18 в полном отчёте и заново
проверять код: это снимок `36c5541e`, а не вечный статус модуля. Старые документы
отдельного `/home/roman/lt` с пометками «выполнено» не подтверждают готовность
портала. Поздние ADR о свободном ношении, делегировании, шести цифрах и эмуляции
учтены; их отмена не предлагается.
