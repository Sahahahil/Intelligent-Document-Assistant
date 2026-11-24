#!/bin/bash
# Production deployment script for Intelligent Document Assistant
# Usage: ./scripts/deploy.sh [staging|production]

set -euo pipefail

ENVIRONMENT="${1:-production}"
PROJECT_NAME="intelligent-doc-assistant"
REGISTRY="ghcr.io"
IMAGE_TAG="${GITHUB_SHA:-latest}"

echo "🚀 Deploying ${PROJECT_NAME} to ${ENVIRONMENT}..."

# Configuration
case "${ENVIRONMENT}" in
  staging)
    COMPOSE_FILE="docker-compose.staging.yml"
    ;;
  production)
    COMPOSE_FILE="docker-compose.prod.yml"
    ;;
  *)
    echo "❌ Unknown environment: ${ENVIRONMENT}"
    echo "Usage: $0 [staging|production]"
    exit 1
    ;;
esac

# Check required environment variables
REQUIRED_VARS=(
  "NEXTAUTH_SECRET"
  "NEXTAUTH_URL"
  "DATABASE_URL"
  "REDIS_URL"
  "QDRANT_URL"
  "LLM_API_KEY"
  "LLM_MODEL"
)

for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "❌ Required environment variable ${var} is not set"
    exit 1
  fi
done

echo "✅ Environment variables validated"

# Pull latest images
echo "📥 Pulling Docker images..."
docker compose -f "${COMPOSE_FILE}" pull

# Run database migrations
echo "🔄 Running database migrations..."
docker compose -f "${COMPOSE_FILE}" run --rm api uv run alembic upgrade head

# Deploy with zero-downtime (rolling update)
echo "🚀 Starting services..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

# Wait for services to be healthy
echo "🏥 Waiting for services to be healthy..."
sleep 10

# Health checks
echo "🔍 Running health checks..."
for i in {1..30}; do
  if curl -sf "http://localhost:8000/health" > /dev/null && \
     curl -sf "http://localhost:3000" > /dev/null; then
    echo "✅ All services healthy"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "❌ Health check failed after 30 attempts"
    docker compose -f "${COMPOSE_FILE}" logs --tail=50
    exit 1
  fi
  echo "⏳ Waiting for services... (${i}/30)"
  sleep 2
done

# Cleanup old images
echo "🧹 Cleaning up old Docker images..."
docker image prune -f

echo "✅ Deployment complete!"
echo "🌐 Application available at: ${NEXTAUTH_URL}"