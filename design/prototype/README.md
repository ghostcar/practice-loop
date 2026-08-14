# PracticeLoop Design v2 prototype

Автономный статический прототип по `DESIGN_V2.md`. Он не подключён к FastAPI/Jinja и не меняет
рабочий frontend.

Открыть локально:

```bash
python3 -m http.server 8090 --directory design
```

Затем открыть `http://127.0.0.1:8090/prototype/`.

В прототипе пять согласованных представлений: Today, Active Timer, Tasks, Inventory и Social.
Переключение экранов и sidebar выполнено небольшим локальным скриптом только для демонстрации;
production-интеграция должна использовать SSR/HTMX и правила проекта.
