# PracticeLoop icon pack

Локальный набор оригинальных outline-иконок для интерфейса PracticeLoop.

- сетка: `24×24`;
- толщина линии: `1.75`;
- окончания и соединения: `round`;
- цвет: `currentColor`;
- emoji и смешивание outline/filled в UI не требуются;
- исходная геометрия и генератор принадлежат проекту, внешних runtime-зависимостей нет.

Содержимое:

- `svg/` — отдельные SVG-файлы;
- `sprite.svg` — единый SVG-sprite со всеми символами `icon-{name}`;
- `preview.html` — визуальный каталог;
- `favicon/` — favicon, Apple Touch Icon, Android/PWA icons, Safari pinned tab и manifest;
- `INTEGRATION_AGENT.md` — точная инструкция агенту, который будет выполнять интеграцию.

Пакет покрывает как фактический интерфейс v0.8-actual, так и будущие модули, описанные в
`examples/New_doc`: Personal Foundation, Chastity Timer, Media Vault, журналы, Care,
Medication/Health/Cycle, Insights, Social, verification/moderation и D/s capability grants.

Перегенерация:

```bash
python3 tools/generate_icon_pack.py
```

Генератор требует Pillow только для экспорта PNG/ICO. Интерфейсные SVG создаются без сторонних
библиотек.
