# Развёртывание OfficeCooking.Web из GitHub

Этот документ описывает настроенный путь от локального изменения до production-сайта. Общая конфигурация VDS, DNS,
TLS, портов и резервного копирования находится в [DEPLOYMENT.md](DEPLOYMENT.md).

## Краткая схема

```text
Локальные изменения
  -> commit и push в main                         вручную
  -> CI для main                                 автоматически
  -> создание и push тега X.Y.Z                  вручную
  -> повторный CI, сборка и публикация в GHCR    автоматически
  -> подтверждение Environment production        вручную
  -> backup, migrations, запуск и health checks  автоматически
  -> открытие сайта и функциональная проверка    вручную
```

Push обычного commit в `main` **не разворачивает production**. Production меняется только после релизного тега и
ручного подтверждения deployment.

## Что уже настроено

- `.github/workflows/ci.yml` запускается для каждого push в `main`, pull request в `main` и как обязательная часть
  release workflow;
- `.github/workflows/release.yml` запускается для тегов строго формата `X.Y.Z`, например `1.0.1`, или вручную для
  уже существующего тега;
- backend и frontend собираются GitHub runners для `linux/amd64` и публикуются в GitHub Container Registry (GHCR);
- версия и одна UTC-дата сборки передаются обоим образам и отображаются приложением;
- production использует digest-ссылки `image@sha256:...`, поэтому сервер запускает именно проверенные образы;
- GitHub Environment `production` требует ручного approval и допускает теги `*.*.*`;
- одновременные production releases запрещены через `concurrency`;
- GitHub подключается по SSH как `officecooking-deploy`. Этот пользователь может через `sudo` запустить только
  `/usr/local/sbin/officecooking-deploy` и не имеет произвольного root- или Docker-доступа.

В Environment `production` хранятся secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_PRIVATE_KEY`,
`VPS_SSH_KNOWN_HOSTS` и variable `VPS_PORT`. Их значения нельзя добавлять в Git или документацию.

## Полный выпуск новой версии

Ниже пример выпуска следующей версии `1.0.1`. Команды выполняются локально из корня репозитория.

### 1. Подготовить и проверить изменения — вручную

Перед commit убедиться, что в рабочем дереве нет случайных файлов, credentials или дампов:

```powershell
git status --short
git diff --check
```

Выполнить проверки из `AGENTS.md`. Минимально для затронутой frontend-части:

```powershell
cd frontend
npm run build
npm test
npm run test:e2e
cd ..
```

Для backend выполнить Ruff, Pytest, проверку lock-файла и генерацию Alembic SQL.

### 2. Создать commit и отправить `main` — вручную

```powershell
git add -- <нужные-файлы>
git commit -m "Краткое описание изменения"
git push origin main
```

После push GitHub автоматически запускает `CI`. Он проверяет:

- backend: `ruff`, `pytest`, `uv lock --check`, полную Alembic SQL-цепочку;
- frontend: TypeScript/Vite build, Vitest и Playwright в desktop/mobile viewport.

Нужно вручную открыть вкладку **Actions**, выбрать запуск `CI` для commit и дождаться зелёного результата. Сейчас CI
проверяет каждый push, но без отдельной branch-protection настройки GitHub технически не запрещает прямой push в
`main` с ошибкой.

### 3. Создать релизный тег — вручную

Тег должен указывать ровно на проверенный commit из `main`. Префикс `v` не используется.

```powershell
git switch main
git pull --ff-only
git tag -a 1.0.1 -m "OfficeCooking 1.0.1"
git push origin 1.0.1
```

Тег нельзя переносить на другой commit или повторно публиковать через force push. Если после создания тега найдена
ошибка, исправление получает новый commit и следующий номер версии.

### 4. Проверки, сборка и публикация — автоматически

Push тега запускает `Release and deploy`. До обращения к VDS GitHub автоматически:

1. проверяет формат версии;
2. повторяет полный CI именно для commit, на который указывает тег;
3. собирает отдельные backend и frontend images;
4. записывает tag как версию и текущую UTC-дату как дату сборки;
5. публикует version- и commit-SHA tags в GHCR;
6. создаёт attestations образов;
7. передаёт следующему job фактические SHA-256 digests.

Если любой шаг завершился ошибкой, production не меняется. Нужно исправить причину новым commit и выпустить новый
тег. Не следует подтверждать deployment, пока build/test jobs не зелёные.

### 5. Разрешить production deployment — вручную

После успешной публикации workflow остановится на job `deploy` со статусом **Waiting**:

1. открыть запуск **Release and deploy** на вкладке GitHub **Actions**;
2. нажать **Review deployments**;
3. выбрать `production`;
4. проверить tag/commit и нажать **Approve and deploy**.

До этого на VDS продолжает работать предыдущая версия.

### 6. Обновить VDS — автоматически

После approval GitHub по закреплённому SSH host key подключается пользователем `officecooking-deploy` и передаёт
версии образов по digest. Root-owned deploy script автоматически:

1. берёт эксклюзивную блокировку, чтобы исключить параллельный deployment;
2. проверяет SemVer, допустимые GHCR image names и digest format;
3. авторизуется в GHCR временным `GITHUB_TOKEN` и скачивает образы;
4. сверяет OCI version/build labels с релизной версией;
5. создаёт PostgreSQL backup `/var/backups/officecooking/before-release-<version>-<UTC>.dump`;
6. сохраняет активные digest и build metadata в `/opt/officecooking/.release.env`;
7. запускает `alembic upgrade head` новым backend image;
8. обновляет Compose services без сборки исходников на VDS;
9. ждёт health checks и проверяет публичные `/ready` и `/version`.

Job становится зелёным только после этих проверок. Автоматического отката базы нет: при неудачной миграции нельзя
считать простой возврат старых контейнеров безопасным rollback.

### 7. Проверить результат — вручную

После зелёного job `deploy` открыть:

```text
https://office-cooking.duckdns.org:8443
```

Проверить:

- сайт открывается по HTTPS;
- вход и изменённый пользовательский сценарий работают;
- в информационном блоке внизу страницы frontend и backend показывают ожидаемую версию и дату;
- `https://office-cooking.duckdns.org:8443/ready` возвращает `{"status":"ready"}`;
- `https://office-cooking.duckdns.org:8443/version` возвращает ожидаемую backend-версию.

Если браузер оставил старую вкладку открытой, сначала выполнить обычное обновление страницы, а при необходимости —
обновление без кеша.

## Повторный запуск и предыдущая версия

На вкладке **Actions → Release and deploy → Run workflow** можно указать существующий tag. Это повторно собирает и
разворачивает исходники именно этого тега, снова требуя production approval. Механизм подходит для восстановления
предыдущей версии приложения, только если её схема совместима с уже применёнными миграциями.

Перед восстановлением обязательно проверить backup и характер миграций. Container rollback и database rollback —
разные операции; pipeline намеренно не выполняет разрушительное восстановление PostgreSQL автоматически.

## Что нельзя делать

- не создавать production tag до зелёного CI нужного commit;
- не использовать `latest` как production-версию;
- не перемещать и не force-push уже опубликованные release tags;
- не копировать `.env`, SSH private keys, GitHub tokens или database dumps в репозиторий;
- не запускать production Compose вручную без `.release.env`, если задача не является осознанным аварийным
  восстановлением;
- не считать успешный запуск контейнера достаточной проверкой — итогом служат зелёный deploy job, `/ready`,
  `/version` и ручная проверка пользовательского сценария.
