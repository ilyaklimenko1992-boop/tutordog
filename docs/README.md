# TutorDog

Бот срезов знаний DocsInBox. n8n + Redis + Google Sheets + Пачка API.

## Структура
- `n8n/` — воркфлоу n8n (WF1–WF4)
- `dashboard/` — аналитический дашборд (FastAPI + HTML)
- `docs/` — документация

## Запуск дашборда
```bash
cd dashboard
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Важно
Файл `service_account.json` не хранится в репозитории — передаётся отдельно.
