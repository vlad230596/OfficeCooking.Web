# Развёртывание OfficeCooking.Web на VDS

Документ фиксирует фактическое production-окружение на 26 августа 2026 года, принятые решения,
операционные команды и ограничения. Секреты и персональные данные здесь не хранятся.

## Текущее production-окружение

| Параметр | Значение |
| --- | --- |
| Провайдер | FastVPS |
| Публичный IPv4 | `5.45.117.224` |
| DNS | `office-cooking.duckdns.org` |
| Публичный URL | `https://office-cooking.duckdns.org:8443` |
| ОС | Ubuntu 24.04.4 LTS |
| Docker | 29.2.1 |
| Docker Compose | 5.0.2 |
| Каталог приложения | `/opt/officecooking` |
| Production Compose | `/opt/officecooking/compose.prod.yaml` |
| Production env | `/opt/officecooking/.env`, владелец `root:root`, режим `600` |
| Active release | `1.0.0`, build date `2026-08-26T18:44:20Z` |
| Release metadata | `/opt/officecooking/.release.env`, владелец `root:root`, режим `600` |
| PostgreSQL | 17.6, только во внутренней Docker-сети |
| Alembic | `0003_authentication (head)` |

Production `1.0.0` развёрнут из commit `d6505ec89d8c673df68c94d56accde45bfdb7083` через GitHub Actions.
Backend и frontend запущены из GHCR по зафиксированным SHA-256 digest, а не из изменяемого тега.

## DNS и TLS

В DuckDNS настроена A-запись:

```text
office-cooking.duckdns.org -> 5.45.117.224
```

IPv4 фиксированный, поэтому DuckDNS updater на VDS не устанавливался. AAAA-запись не создавалась.
DuckDNS token не нужен серверу, не хранится в `.env` и не должен попадать в Git или документацию.

Caddy автоматически получает и продлевает сертификат Let's Encrypt. Для этого проекта HTTPS
опубликован на нестандартном порту `8443`; порт `443` не входит в контур OfficeCooking. Caddy
использует HTTP-01 challenge через порт 80, поэтому порт 80 должен оставаться доступным снаружи
для выпуска и продления сертификата.

Запрос к `http://office-cooking.duckdns.org` перенаправляется на:

```text
https://office-cooking.duckdns.org:8443
```

Данные Caddy, включая ACME account и сертификаты, хранятся в Docker volume
`officecooking_caddy-data`. Удаление этого volume приведёт к повторному выпуску сертификата.

## Карта портов

### OfficeCooking

| Порт | Доступ | Назначение |
| --- | --- | --- |
| `80/tcp` | публичный | Caddy: HTTP-01 challenge и redirect на HTTPS `:8443` |
| `8443/tcp` | публичный | Caddy: основной HTTPS frontend и API |
| `8443/udp` | публичный | Caddy: HTTP/3; для основной работы не обязателен |
| `80/tcp` frontend | только Docker network | nginx со статическим React frontend и proxy `/api/` |
| `8000/tcp` backend | только Docker network | FastAPI/uvicorn |
| `5432/tcp` PostgreSQL | только Docker network | база данных приложения |
| `2019/tcp` Caddy | только внутри контейнера | Caddy admin endpoint, наружу не опубликован |

FastAPI и PostgreSQL не должны публиковаться на host-интерфейсе.

Для OfficeCooking в UFW добавлены только:

```text
80/tcp
8443/tcp
8443/udp
```

## Архитектура production

```text
Internet
  |
  +-- TCP 80 ----------> Caddy: ACME + redirect
  +-- TCP/UDP 8443 ----> Caddy: TLS
                              |
                              v
                         frontend/nginx:80
                              |
                              +-- static React
                              +-- /api/* --> backend:8000 --> PostgreSQL:5432
```

Backend является источником истины. Frontend, backend и PostgreSQL доступны друг другу только в
Compose network. Снаружи запросы проходят через Caddy и nginx.

## Production-переменные

Файл `/opt/officecooking/.env` содержит примерно такую конфигурацию:

```dotenv
POSTGRES_DB=officecook
POSTGRES_USER=officecook
POSTGRES_PASSWORD=<secret>
APP_DOMAIN=office-cooking.duckdns.org
APP_ORIGIN=https://office-cooking.duckdns.org:8443
APP_HTTPS_PORT=8443
```

Правила:

- `APP_DOMAIN` содержит только hostname, без схемы, порта и завершающего `/`;
- `APP_ORIGIN` содержит полный browser origin и нестандартный порт;
- `APP_HTTPS_PORT` задаёт одновременно host- и container-порт Caddy;
- production требует secure session cookie;
- пароль PostgreSQL генерируется отдельно и нигде не документируется;
- `.env` нельзя копировать в Git, Docker image или обычный архив исходников.

## Изменения production-конфигурации

На основании фактического развёртывания изменены:

- `.env.example` — добавлены `APP_ORIGIN` и `APP_HTTPS_PORT`;
- `compose.prod.yaml` — CORS получает полный origin, Caddy поддерживает настраиваемый HTTPS-порт;
- `Caddyfile` — site address использует `APP_HTTPS_PORT`, default остаётся `443`;
- `backend/Dockerfile` — uv-cache доступен непривилегированному UID 65532, production-команды
  запускаются через `uv run --no-sync` без изменения `.venv` при старте;
- этот `DEPLOYMENT.md` — production runbook.

Для обычного VDS без конфликта портов достаточно оставить:

```dotenv
APP_ORIGIN=https://example.com
APP_HTTPS_PORT=443
```

## Данные production

Изначально production-база была создана миграциями `0001 -> 0002 -> 0003`. Затем в неё был
перенесён локальный test state из PostgreSQL 18.6:

- использован консистентный data-only dump без DDL;
- `alembic_version` не переносился, поскольку target schema уже находилась на том же head;
- очистка target-таблиц и восстановление выполнялись одной транзакцией;
- sequences и идентификаторы перенесены;
- все 14 таблиц проверены сравнением точных counts и row-level digest;
- результат проверки: полное совпадение локальной и production-базы на момент snapshot.

Контрольные количества после переноса:

| Таблица | Строк |
| --- | ---: |
| `users` | 47 |
| `cooks` | 241 |
| `cook_members` | 1939 |
| `cook_member_votes` | 2753 |
| `cook_product_prices` | 2630 |
| `cook_vote_variants` | 981 |
| `cook_templates` | 15 |
| `template_ingredients` | 156 |
| `template_vote_variants` | 46 |
| `payments` | 484 |
| `payment_types` | 5 |
| `user_contacts` | 5 |
| `import_runs` | 1 |
| `auth_sessions` | 2 |

Настроены две учётные записи с password hash и `auth_enabled`. Cookies локального адреса не
переносятся между origin, поэтому на production нужно войти заново с теми же credentials.

Перед импортом создан root-only backup прежней production-базы:

```text
/var/backups/officecooking/before-local-state-20260826.dump
```

Это backup состояния **до** переноса локальной базы. Автоматические периодические backup ещё не
настроены — это отдельная обязательная эксплуатационная задача.

## Проверка состояния

Все команды выполняются на VDS:

```bash
cd /opt/officecooking
sudo docker compose -f compose.prod.yaml ps
```

Проверка миграции:

```bash
sudo docker compose -f compose.prod.yaml exec -T backend \
  uv run --no-sync alembic current
```

Проверка внутри VDS:

```bash
curl --fail https://office-cooking.duckdns.org:8443/ready
```

Ожидаемый ответ:

```json
{"status":"ready"}
```

Журналы:

```bash
sudo docker compose -f compose.prod.yaml logs --tail=200
sudo docker compose -f compose.prod.yaml logs --tail=200 caddy
sudo docker compose -f compose.prod.yaml logs --tail=200 backend
```

Проверка host listeners:

```bash
sudo ss -lntup
sudo ufw status verbose
```

## Резервное копирование вручную

Создать каталог один раз:

```bash
sudo install -d -m 700 -o root -g root /var/backups/officecooking
```

Создать custom-format dump:

```bash
cd /opt/officecooking
sudo sh -c 'docker compose -f compose.prod.yaml exec -T postgres \
  pg_dump -U officecook -d officecook -Fc \
  > /var/backups/officecooking/officecook-$(date +%Y%m%d-%H%M%S).dump'
```

Проверить созданный архив:

```bash
sudo ls -lh /var/backups/officecooking
sudo sha256sum /var/backups/officecooking/*.dump
```

Backup необходимо выгружать с самого VDS во внешнее хранилище и периодически проверять тестовое
восстановление. Один файл на том же диске не защищает от потери VDS.

## Аварийное ручное обновление

Основной путь обновления теперь проходит через GitHub Actions. Сборка непосредственно на VDS оставлена только как
аварийный вариант, если GitHub или GHCR временно недоступны.

1. Создать и проверить backup.
2. Получить нужный commit/tag.
3. Последовательно собрать образы, чтобы снизить пиковое потребление RAM.
4. Остановить публичные сервисы.
5. Применить миграции новым backend image.
6. Запустить весь Compose и проверить readiness.

Пример команд после получения проверенной версии исходников:

```bash
cd /opt/officecooking
sudo docker compose -f compose.prod.yaml build backend
sudo docker compose -f compose.prod.yaml build frontend
sudo docker compose -f compose.prod.yaml stop caddy frontend backend
sudo docker compose -f compose.prod.yaml run --rm --no-deps backend \
  uv run --no-sync alembic upgrade head
sudo docker compose -f compose.prod.yaml up -d --no-build --wait --wait-timeout 180
curl --fail https://office-cooking.duckdns.org:8443/ready
```

При ошибке миграции нельзя считать откат контейнеров полноценным rollback базы. Для потенциально
разрушающих migrations нужен проверенный backup и осознанное восстановление.

## Deployment по тегам через GitHub Actions

Пошаговый путь от локального commit до ручной проверки сайта вынесен в
[GITHUB_DEPLOYMENT.md](GITHUB_DEPLOYMENT.md).

Реализованный процесс:

```text
Git tag X.Y.Z
  -> GitHub Actions: tests
  -> build backend/frontend один раз
  -> publish immutable images в GHCR
  -> GitHub Environment production (с approval, если он включён в настройках репозитория)
  -> VDS: pull конкретной версии/digest
  -> backup
  -> migrations
  -> health check
```

Принятые решения:

- release создаётся по SemVer-тегу, а не по каждому commit в `main`;
- production deployment запускается кнопкой после успешной сборки;
- образы публикуются в GHCR с version tag и immutable commit SHA/digest;
- `latest` не используется как production-версия;
- VDS скачивает готовые образы и не собирает релиз заново;
- GitHub Environment `production` хранит deployment secrets и ограничивает допустимые tags;
- deployment имеет `concurrency`, чтобы одновременно выполнялся только один запуск;
- серверный deploy script делает backup, migration, запуск и readiness check;
- автоматический rollback контейнеров не должен автоматически откатывать БД.

### Как выпустить версию

Release workflow находится в `.github/workflows/release.yml`. Он запускается автоматически при публикации тега
строго формата `X.Y.Z`, например `1.0.0`. Повторный запуск уже существующего тега доступен на вкладке GitHub Actions
через кнопку **Run workflow** и параметр `version`.

Обычный релиз:

```bash
git switch main
git pull --ff-only
git tag -a 1.0.0 -m "OfficeCooking 1.0.0"
git push origin main
git push origin 1.0.0
```

Workflow выполняет полный CI, один раз собирает frontend и backend, публикует образы в GHCR с version- и SHA-тегами,
фиксирует их attestations и передаёт VDS ссылки на immutable SHA-256 digests. Сервер перед каждым изменением создаёт
custom-format PostgreSQL backup в `/var/backups/officecooking`, применяет Alembic migrations и проверяет `/ready` и
`/version`. Одновременно может выполняться только один production deployment.

Production Environment должен содержать:

| Имя | Тип | Значение |
| --- | --- | --- |
| `VPS_HOST` | secret | публичный IP VDS |
| `VPS_USER` | secret | `officecooking-deploy` |
| `VPS_SSH_PRIVATE_KEY` | secret | отдельный приватный Ed25519-ключ GitHub Actions |
| `VPS_SSH_KNOWN_HOSTS` | secret | закреплённая строка `known_hosts` для VDS |
| `VPS_PORT` | variable | `22` |

Для Environment рекомендуется включить required reviewer и разрешить deployment только для тегов `*.*.*`. Тогда
создание тега собирает и публикует образы, а изменение production начинается только после нажатия **Review deployments**.
Если reviewer не настроен, deployment после успешного CI выполняется автоматически.

На VDS GitHub подключается не под `root`, а под `officecooking-deploy`. Для него разрешена только одна sudo-команда:
`/usr/local/sbin/officecooking-deploy`. Root-owned копия этого скрипта устанавливается из
`scripts/deploy-production.sh`; пользователь не имеет доступа к production `.env` и Docker socket напрямую.

### Версии и даты сборки

Release workflow передаёт один tag и одну UTC-дату обеим сборкам. Значения записываются в OCI labels и в приложение:

- frontend показывает свою версию/дату и полученную от backend версию/дату внизу окна;
- backend возвращает метаданные без авторизации по `GET /version`;
- локальные сборки без release arguments честно отображаются как `dev` / `unknown`.

Пример production-проверки:

```bash
curl --fail https://office-cooking.duckdns.org:8443/version
```

Файл `/opt/officecooking/.release.env` хранит только активные version/build metadata и digest-ссылки на образы. Секретов
в нём нет. Предыдущее значение сохраняется как `.release.env.previous`, однако откат после миграций выполняется только
осознанно: смена контейнеров сама по себе не откатывает схему или данные PostgreSQL.

## Безопасность и housekeeping

- Временный интерактивный SSH-ключ настройки пока оставлен на VDS по решению владельца; pipeline его не использует.
  После проверки первого релиза его нужно отозвать отдельно. Постоянный deploy key ограничен специальной sudo-командой.
- Временные SQL/dump с персональными данными удалены с рабочей машины и VDS.
- Пользователь `codex-setup` заблокирован, имеет shell `nologin`, не имеет ключа и sudo. Его запись
  можно окончательно удалить командой `sudo userdel -r codex-setup`.
- Docker service включён в автозапуск; Compose services используют `restart: unless-stopped`.
- На VDS 2 GiB RAM и нет swap; release images собираются на GitHub runners, а VDS только скачивает их.
- На системном диске 20 GiB; после развёртывания было занято около 5.7 GiB.
- Backup перед каждым deployment настроен; периодические backup, внешнее хранение, мониторинг, alerting и ротация
  deployment history пока не настроены.
- Нельзя публиковать payment API/UI: платежи участвуют только во внутренних расчётах текущей v1.
- Нельзя добавлять в Git `.env`, database dumps, migration reports, manifests или пользовательские
  данные.

Подробности аутентификации находятся в [AUTHENTICATION.md](AUTHENTICATION.md).
