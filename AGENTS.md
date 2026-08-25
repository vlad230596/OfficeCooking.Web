# AGENTS.md

## Назначение

OfficeCooking.Web — локальное клиент-серверное приложение для учёта офисных
готовок, расходов, участников, порций и взаиморасчётов. Backend является
источником истины; frontend отображает данные и отправляет команды.

## Архитектура

- `backend/` — Python 3.13, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic и Pydantic;
- `frontend/` — React 19, TypeScript, Vite, TanStack Query, Vitest и Playwright;
- `compose.yaml` — локальные PostgreSQL и backend;
- API без авторизации предназначен только для доверенного localhost.

## Доменные инварианты

- Строка расхода хранится lossless вместе с вычисленным значением, статусом и
  версией алгоритма. При изменении строки backend пересчитывает cache.
- Legacy-арифметика сохраняет типовую семантику, `float32`-квантизацию, порядок
  скидок, `ceilTo5` и защитные ошибки. Не заменять её обычным `eval`, `float` или
  произвольным Decimal-вычислением.
- Историческая готовка является snapshot. Изменение шаблона не меняет готовки.
- Backend сохраняет присланный упорядоченный состав готовки без сверки позиций с
  текущим шаблоном.
- `permanentSale` фиксируется в участнике готовки при добавлении и не меняется
  вслед за пользователем. При редактировании snapshot сохраняется.
- Пользователи не удаляются. Добавление пользователя не меняет историю.
- Платежи участвуют в балансах, но публичных payment mutation/list endpoints и
  UI платежей в v1 нет.
- Недельная группировка использует Gregorian FirstDay/Monday и календарный год
  исходной даты, а не ISO week-year.
- Для готовок сохраняются optimistic concurrency (`rowVersion`) и автоматический
  пересчёт Legacy-значений.

## Приватные данные

Legacy `data/`, реальные migration reports, manifests и полные golden snapshots
не входят в публичный репозиторий и перечислены в `.gitignore`. Не добавлять в
Git персональные данные, дампы БД, локальные credentials или производные от них
fixtures. Безопасный арифметический corpus находится в
`backend/tests/fixtures/legacy-expression-corpus.json`.

## Проверки

Backend:

```powershell
cd backend
uv sync --frozen
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head --sql
```

Frontend:

```powershell
cd frontend
npm ci
npm run build
npm test
npm run test:e2e
```

## Безопасная работа

- Не откатывать и не удалять пользовательские изменения вне задачи.
- Не менять `0001_initial_schema.py`; схему расширять новой Alembic revision.
- Не открывать сетевое прослушивание и не добавлять частичную авторизацию.
- Не добавлять payment UI/API без отдельного решения.
- При изменении contracts синхронизировать FastAPI и TypeScript.
- Не коммитить `.env`, данные пользователей, reports, manifests и дампы.
