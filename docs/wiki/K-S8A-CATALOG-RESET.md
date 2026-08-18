# S8a — reset legacy activity catalog

18 августа 2026 перед проектированием нового 18+ starter set создан PostgreSQL custom dump
`/tmp/practice_loop_pre_catalog_reset_20260818.dump` (283 KiB).

Read-only precheck подтвердил: в `entities` было 30 записей, все принадлежали
`roman@gorbunovr.ru`; связанных activity logs, opt-ins, schedule rules и body/location/inventory
requirements не было. Удалены только эти 30 записей. После операции `entities=0`, сквозной
`activity_catalog=25`, users=13, `/healthz` отвечает 200.

`activity_catalog` не является удалённым справочником действий: это сохранённый межмодульный
справочник типов Care/Journal/Timer. Legacy `SEED_ENTITIES` нельзя повторно запускать до его
замены новым проверенным manifest по `docs/catalog/ADULT_ACTIVITY_CATALOG.md`.
