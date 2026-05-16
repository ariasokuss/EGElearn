#!/usr/bin/env bash
# deploy-dev.sh — called by GitLab CI over SSH to deploy to the dev server.
#
# Expected env vars (injected by the CI job):
#   DEPLOY_REF      — git commit SHA to deploy
#   REPO_DIR        — absolute path to the repo on this server
#   ENV_FILE        — path to the .env file (default: .env)
set -euo pipefail

: "${DEPLOY_REF:?DEPLOY_REF is required}"
: "${REPO_DIR:?REPO_DIR is required}"
ENV_FILE="${ENV_FILE:-.env}"

echo "==> [deploy-dev] ref=$DEPLOY_REF repo=$REPO_DIR env=$ENV_FILE"

cd "$REPO_DIR"

COMPOSE_FILE="docker-compose.yml"
echo "==> Using $COMPOSE_FILE"

echo "==> Running migrations..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm --build migrate

echo "==> Building and restarting services..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build --remove-orphans api # processing-worker

echo "==> Waiting for api to become healthy..."
for i in $(seq 1 12); do
    STATUS=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps --format json api \
        | python3 -c "import sys,json; data=sys.stdin.read().strip(); rows=json.loads(data) if data.startswith('[') else [json.loads(l) for l in data.splitlines() if l]; print(rows[0].get('Health','') or rows[0].get('State',''))" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "running" ]; then
        echo "==> api is $STATUS"
        break
    fi
    echo "    ($i/12) api status: $STATUS — waiting 5s..."
    sleep 5
done

echo "==> Deploy $DEPLOY_REF complete."
