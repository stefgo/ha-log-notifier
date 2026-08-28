#!/bin/bash
# Builds the card and deploys the integration, the card and the blueprint to
# the Home Assistant instance.
#
# Configuration comes from .env (see .env.example); environment variables that
# are already set take precedence.

set -e

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

HOST="${HA_HOST:-}"
CONFIG="${HA_CONFIG:-/config}"
TARGET="${HA_TARGET:-${CONFIG}/custom_components}"
SSH_PORT="${HA_SSH_PORT:-22}"

if [ -z "$HOST" ]; then
  echo "HA_HOST is not set. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

echo "Building card ..."
npm --prefix card ci --silent
npm --prefix card run build

echo "Deploying integration to ${HOST}:${TARGET} ..."
rsync -az --delete \
  -e "ssh -p ${SSH_PORT}" \
  --exclude '__pycache__' \
  custom_components/lognotifier "${HOST}:${TARGET}/"

echo "Deploying blueprint ..."
ssh -p "${SSH_PORT}" "${HOST}" "mkdir -p ${CONFIG}/blueprints/automation/lognotifier"
scp -P "${SSH_PORT}" blueprints/automation/lognotifier/*.yaml \
  "${HOST}:${CONFIG}/blueprints/automation/lognotifier/"

VERSION="$(node -p "require('./card/package.json').version")"

echo "Done. Deployed card version: ${VERSION}"
echo "Restart Home Assistant so the integration is reloaded."
