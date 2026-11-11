#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly APP_DIR="/opt/officecooking"
readonly COMPOSE_FILE="compose.prod.yaml"
readonly COMPOSE_NEXT="compose.prod.yaml.next"
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

# The rest of stdin is compose.prod.yaml from the release tag. The repository is the only source of this file:
# the shared Caddy serves other tenants of this VDS, and their ingress networks must live in it.
cat > "$COMPOSE_NEXT"
if [[ ! -s "$COMPOSE_NEXT" ]]; then
  echo "compose.prod.yaml from the release is required on stdin after the GHCR token." >&2
  exit 64
fi
docker compose --env-file .env -f "$COMPOSE_NEXT" config --quiet
diff -u "$COMPOSE_FILE" "$COMPOSE_NEXT" || true

# External networks (tenant ingresses) the release attaches caddy to.
external_networks() {
  docker compose --env-file .env -f "$1" config --format json \
    | python3 -c 'import json, sys
for key, net in json.load(sys.stdin).get("networks", {}).items():
    if net.get("external"):
        print(net.get("name") or key)'
}

# Networks the running caddy is attached to, without its own Compose default network.
caddy_networks() {
  local id
  id="$(docker compose --env-file .env -f "$COMPOSE_FILE" ps -q caddy)"
  if [[ -n "$id" ]]; then
    docker inspect --format '{{ range $name, $_ := .NetworkSettings.Networks }}{{ println $name }}{{ end }}' "$id" \
      | grep -v -e '^$' -e '_default$' || true
  fi
}

mapfile -t TENANT_NETWORKS < <(external_networks "$COMPOSE_NEXT")

# Preflight: every release recreates caddy, so it must not lose a network on the way.
preflight_failed=0
for network in "${TENANT_NETWORKS[@]}"; do
  if ! docker network inspect "$network" >/dev/null 2>&1; then
    echo "External network $network from $COMPOSE_FILE does not exist on this host." >&2
    preflight_failed=1
  fi
done
while IFS= read -r network; do
  if [[ ! " ${TENANT_NETWORKS[*]} " == *" $network "* ]]; then
    echo "Network $network is on this host or on the running caddy, but $COMPOSE_FILE does not attach caddy to it." >&2
    echo "Recreating caddy would cut that tenant off (502). Add it to $COMPOSE_FILE in the repository." >&2
    preflight_failed=1
  fi
done < <({ docker network ls --format '{{ .Name }}' | grep -e '-ingress$' || true; caddy_networks; } | sort -u)
if [[ "$preflight_failed" -ne 0 ]]; then
  echo "Refusing to recreate the shared Caddy. Nothing has been changed." >&2
  exit 78
fi

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

cp "$COMPOSE_FILE" "${COMPOSE_FILE}.previous"
install -m 644 "$COMPOSE_NEXT" "$COMPOSE_FILE"
rm -f "$COMPOSE_NEXT"

compose=(docker compose --env-file .env --env-file "$RELEASE_ENV" -f "$COMPOSE_FILE")
"${compose[@]}" run --rm --no-deps backend uv run --no-sync alembic upgrade head
"${compose[@]}" up -d --no-build --wait --wait-timeout 180

# Postflight: the recreated caddy must be on every tenant ingress, or those tenants answer 502.
readonly ATTACHED_NETWORKS="$(caddy_networks)"
missing_networks=()
for network in "${TENANT_NETWORKS[@]}"; do
  if ! grep -qx -- "$network" <<< "$ATTACHED_NETWORKS"; then
    missing_networks+=("$network")
  fi
done
if [[ ${#missing_networks[@]} -gt 0 ]]; then
  echo "Shared Caddy is not attached to: ${missing_networks[*]}. Those tenants answer 502 now." >&2
  echo "Restore with: docker network connect <network> \$(docker compose -f $APP_DIR/$COMPOSE_FILE ps -q caddy)" >&2
  exit 71
fi

curl --fail --silent --show-error "$APP_ORIGIN/ready" >/dev/null
readonly VERSION_JSON="$(curl --fail --silent --show-error "$APP_ORIGIN/version")"
if [[ "$VERSION_JSON" != *"\"version\":\"$VERSION\""* ]]; then
  echo "Published backend version does not match $VERSION: $VERSION_JSON" >&2
  exit 70
fi

echo "OfficeCooking $VERSION deployed successfully."
echo "Backend built: $BACKEND_BUILD_DATE"
echo "Frontend built: $FRONTEND_BUILD_DATE"
