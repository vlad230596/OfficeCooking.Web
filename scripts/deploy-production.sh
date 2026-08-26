#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly APP_DIR="/opt/officecooking"
readonly COMPOSE_FILE="compose.prod.yaml"
readonly RELEASE_ENV=".release.env"
readonly BACKUP_DIR="/var/backups/officecooking"

if [[ $# -ne 4 ]]; then
  echo "Usage: deploy-production.sh VERSION BACKEND_IMAGE FRONTEND_IMAGE GHCR_USER" >&2
  exit 64
fi

readonly VERSION="$1"
readonly BACKEND_IMAGE="$2"
readonly FRONTEND_IMAGE="$3"
readonly GHCR_USER="$4"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must be a SemVer core such as 1.0.0." >&2
  exit 64
fi

if [[ ! "$BACKEND_IMAGE" =~ ^ghcr\.io/[a-z0-9_.-]+/officecooking-backend@sha256:[a-f0-9]{64}$ ]]; then
  echo "Backend image must be an approved GHCR digest reference." >&2
  exit 64
fi
if [[ ! "$FRONTEND_IMAGE" =~ ^ghcr\.io/[a-z0-9_.-]+/officecooking-frontend@sha256:[a-f0-9]{64}$ ]]; then
  echo "Frontend image must be an approved GHCR digest reference." >&2
  exit 64
fi
if [[ ! "$GHCR_USER" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "Invalid GHCR username." >&2
  exit 64
fi

IFS= read -r GHCR_TOKEN
if [[ -z "$GHCR_TOKEN" ]]; then
  echo "GHCR token is required on stdin." >&2
  exit 64
fi

exec 9>"/run/lock/officecooking-deploy.lock"
if ! flock -n 9; then
  echo "Another OfficeCooking deployment is already running." >&2
  exit 75
fi

cd "$APP_DIR"
test -f .env
test -f "$COMPOSE_FILE"

set -a
# shellcheck disable=SC1091
source .env
set +a
: "${APP_ORIGIN:?APP_ORIGIN must be set in /opt/officecooking/.env}"

cleanup() {
  GHCR_TOKEN=""
  docker logout ghcr.io >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf '%s\n' "$GHCR_TOKEN" | docker login ghcr.io --username "$GHCR_USER" --password-stdin >/dev/null
docker pull "$BACKEND_IMAGE"
docker pull "$FRONTEND_IMAGE"

readonly BACKEND_BUILD_DATE="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.created" }}' "$BACKEND_IMAGE")"
readonly FRONTEND_BUILD_DATE="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.created" }}' "$FRONTEND_IMAGE")"
readonly BACKEND_VERSION="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$BACKEND_IMAGE")"
readonly FRONTEND_VERSION="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$FRONTEND_IMAGE")"

if [[ "$BACKEND_VERSION" != "$VERSION" || "$FRONTEND_VERSION" != "$VERSION" ]]; then
  echo "Image version labels do not match release $VERSION." >&2
  exit 65
fi

install -d -m 700 "$BACKUP_DIR"
readonly BACKUP_PATH="$BACKUP_DIR/before-release-${VERSION}-$(date -u +%Y%m%d-%H%M%SZ).dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-officecook}" -d "${POSTGRES_DB:-officecook}" -Fc \
  > "$BACKUP_PATH"
test -s "$BACKUP_PATH"
chmod 600 "$BACKUP_PATH"
sha256sum "$BACKUP_PATH"

if [[ -f "$RELEASE_ENV" ]]; then
  cp "$RELEASE_ENV" "${RELEASE_ENV}.previous"
fi
cat > "${RELEASE_ENV}.next" <<EOF
APP_VERSION=$VERSION
BUILD_DATE=$BACKEND_BUILD_DATE
BACKEND_IMAGE=$BACKEND_IMAGE
FRONTEND_IMAGE=$FRONTEND_IMAGE
EOF
mv "${RELEASE_ENV}.next" "$RELEASE_ENV"

compose=(docker compose --env-file .env --env-file "$RELEASE_ENV" -f "$COMPOSE_FILE")
"${compose[@]}" run --rm --no-deps backend uv run --no-sync alembic upgrade head
"${compose[@]}" up -d --no-build --wait --wait-timeout 180

curl --fail --silent --show-error "$APP_ORIGIN/ready" >/dev/null
readonly VERSION_JSON="$(curl --fail --silent --show-error "$APP_ORIGIN/version")"
if [[ "$VERSION_JSON" != *"\"version\":\"$VERSION\""* ]]; then
  echo "Published backend version does not match $VERSION: $VERSION_JSON" >&2
  exit 70
fi

echo "OfficeCooking $VERSION deployed successfully."
echo "Backend built: $BACKEND_BUILD_DATE"
echo "Frontend built: $FRONTEND_BUILD_DATE"
