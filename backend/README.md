# OfficeCookAssistant backend

FastAPI/PostgreSQL backend for the web migration. The current implementation includes the initial
SQLAlchemy/Alembic schema, versioned Legacy calculation engine, typed API contracts, and a
manifest-verified JSON migration CLI, and the catalog, cooks, expression-preview, and balances HTTP APIs.
Payment data is imported for balance calculations but intentionally has no public list or mutation API in v1.

## Local development with uv

The Python 3.13 toolchain is pinned by `.python-version` and installed/selected by
[uv](https://docs.astral.sh/uv/). A separate virtual environment or system Python is not required.

```powershell
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The committed `uv.lock` is the reproducibility source. Change dependencies in `pyproject.toml`, run
`uv lock` (or a targeted `uv lock --upgrade-package <name>`), run the checks, and commit both files.

## Database configuration

By default, settings use localhost PostgreSQL. Compose passes host, port, database, user, and
password separately; SQLAlchemy builds the URL and safely escapes password characters. An explicit
`OFFICE_COOK_DATABASE_URL` remains available for advanced use, but its credentials must be
percent-encoded and its driver must be `postgresql+asyncpg`.

## Legacy JSON migration

The compatibility CLI is retained for installations that still need to import Legacy JSON. Source
data and its manifest are private deployment inputs and are not part of this repository. Always run
validation and dry-run before importing:

```powershell
uv run office-cook-migrate validate --data <legacy-data> --manifest <manifest.json>
uv run office-cook-migrate dry-run --data <legacy-data> --manifest <manifest.json> --report <dry-run-report.json>
```

After PostgreSQL is migrated and backed up, import with:

```powershell
uv run office-cook-migrate import --data <legacy-data> --manifest <manifest.json> --report <import-report.json>
```

## Docker Compose

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build
docker compose exec backend uv run alembic upgrade head
```

Replace the example password before startup. Development API and PostgreSQL ports are bound to
`127.0.0.1`; use `compose.prod.yaml` for an authenticated public deployment.
`GET http://127.0.0.1:8000/health` is a process-liveness probe and
does not access PostgreSQL. `GET http://127.0.0.1:8000/ready` is the readiness probe and returns
success only when PostgreSQL accepts a query.

Host and CORS settings use explicit localhost allowlists. Override them only with JSON arrays, for
example `OFFICE_COOK_CORS_ORIGINS=["http://localhost:5173"]`; wildcard values are rejected. The
current API deliberately rejects all `DELETE` requests until deletion semantics are approved.

## Authentication and roles

All `/api/v1` routes except login require a revocable server-side session. The browser receives an
HttpOnly session cookie and a separate CSRF token. Roles are hierarchical: `viewer` can read,
`editor` can also manage cooks and run calculations, and `admin` can additionally manage catalogs
and login access. Passwords are stored as salted scrypt hashes.

After applying migrations, enable the first administrator on an existing imported user:

```powershell
uv run office-cook-auth list-users
uv run office-cook-auth set-user --legacy-id 1 --username admin --role admin
```

The command prompts for the password without putting it in shell history. Further accounts are
managed on the **Доступы** page. Changing an account revokes all of that user's sessions.
