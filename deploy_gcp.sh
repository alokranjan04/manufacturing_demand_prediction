#!/usr/bin/env bash
# deploy_gcp.sh — Manual one-shot deploy of Chem AI to GCP Cloud Run
# Usage: chmod +x deploy_gcp.sh && ./deploy_gcp.sh
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT="nth-infusion-490008-h8"
REGION="asia-south1"
REPO="chem-ai"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
BACKEND_SERVICE="chem-ai-backend"
FRONTEND_SERVICE="chem-ai-frontend"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")

echo "=== Chem AI GCP Deploy ==="
echo "Project:  $PROJECT"
echo "Region:   $REGION"
echo "Tag:      $TAG"
echo ""

# ── 1. Auth + project ─────────────────────────────────────────────────────────
gcloud config set project "$PROJECT"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── 2. Enable APIs ────────────────────────────────────────────────────────────
echo "--- Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT" --quiet

# ── 3. Create Artifact Registry repo (idempotent) ────────────────────────────
echo "--- Creating Artifact Registry repo (if not exists)..."
gcloud artifacts repositories describe "$REPO" \
  --location="$REGION" --project="$PROJECT" &>/dev/null \
  || gcloud artifacts repositories create "$REPO" \
       --repository-format=docker \
       --location="$REGION" \
       --project="$PROJECT" --quiet

# ── 4. Store secrets (skip if already exist) ──────────────────────────────────
echo "--- Storing secrets in Secret Manager..."

store_secret() {
  local name=$1
  local value=$2
  if gcloud secrets describe "$name" --project="$PROJECT" &>/dev/null; then
    echo "  Secret $name already exists — skipping (use 'gcloud secrets versions add' to update)"
  else
    printf '%s' "$value" | gcloud secrets create "$name" \
      --data-file=- --project="$PROJECT"
    echo "  Created secret: $name"
  fi
}

# ── Edit these values before running ──────────────────────────────────────────
store_secret "OPENROUTER_API_KEY"             "REPLACE_WITH_OPENROUTER_API_KEY"
store_secret "DATABRICKS_TOKEN"               "REPLACE_WITH_DATABRICKS_TOKEN"
store_secret "DATABRICKS_SERVER_HOSTNAME"     "REPLACE_WITH_HOSTNAME"
store_secret "DATABRICKS_HTTP_PATH"           "REPLACE_WITH_HTTP_PATH"
store_secret "DATABRICKS_JOB_ID"              "REPLACE_WITH_JOB_ID"
store_secret "DATABRICKS_VOLUME_INCOMING_PATH" "/Volumes/chem_ai/bronze/raw_files"

# ── 5. Build + push backend ───────────────────────────────────────────────────
echo "--- Building backend..."
docker build -t "${REGISTRY}/backend:${TAG}" -t "${REGISTRY}/backend:latest" ./backend
docker push "${REGISTRY}/backend:${TAG}"
docker push "${REGISTRY}/backend:latest"

# ── 6. Deploy backend ─────────────────────────────────────────────────────────
echo "--- Deploying backend to Cloud Run..."
gcloud run deploy "$BACKEND_SERVICE" \
  --image="${REGISTRY}/backend:${TAG}" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --cpu=2 \
  --memory=2Gi \
  --min-instances=1 \
  --max-instances=5 \
  --concurrency=20 \
  --timeout=120 \
  --port=8080 \
  --set-secrets="OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest,DATABRICKS_TOKEN=DATABRICKS_TOKEN:latest,DATABRICKS_SERVER_HOSTNAME=DATABRICKS_SERVER_HOSTNAME:latest,DATABRICKS_HTTP_PATH=DATABRICKS_HTTP_PATH:latest,DATABRICKS_JOB_ID=DATABRICKS_JOB_ID:latest,DATABRICKS_VOLUME_INCOMING_PATH=DATABRICKS_VOLUME_INCOMING_PATH:latest" \
  --set-env-vars="OPENROUTER_MODEL=minimax/minimax-m3.1-flash:free,CHEM_AI_CATALOG=chem_ai,DEVIATION_THRESHOLD_PCT=10,AGENT_AUTO_RUN=false" \
  --quiet

BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" \
  --region="$REGION" --format="value(status.url)")
echo "Backend live: $BACKEND_URL"

# Update ALLOWED_ORIGINS on backend once frontend URL is known (done after frontend deploy)

# ── 7. Build + push frontend ──────────────────────────────────────────────────
echo "--- Building frontend..."
docker build \
  --build-arg "VITE_API_BASE_URL=${BACKEND_URL}" \
  -t "${REGISTRY}/frontend:${TAG}" \
  -t "${REGISTRY}/frontend:latest" \
  ./frontend
docker push "${REGISTRY}/frontend:${TAG}"
docker push "${REGISTRY}/frontend:latest"

# ── 8. Deploy frontend ────────────────────────────────────────────────────────
echo "--- Deploying frontend to Cloud Run..."
gcloud run deploy "$FRONTEND_SERVICE" \
  --image="${REGISTRY}/frontend:${TAG}" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --cpu=1 \
  --memory=512Mi \
  --min-instances=0 \
  --max-instances=3 \
  --concurrency=80 \
  --port=80 \
  --quiet

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" \
  --region="$REGION" --format="value(status.url)")
echo "Frontend live: $FRONTEND_URL"

# ── 9. Update backend CORS with live frontend URL ─────────────────────────────
echo "--- Updating backend CORS with frontend URL..."
gcloud run services update "$BACKEND_SERVICE" \
  --region="$REGION" \
  --set-env-vars="OPENROUTER_MODEL=minimax/minimax-m3.1-flash:free,CHEM_AI_CATALOG=chem_ai,DEVIATION_THRESHOLD_PCT=10,AGENT_AUTO_RUN=false,ALLOWED_ORIGINS=${FRONTEND_URL}" \
  --quiet

# ── 10. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=== Deploy complete ==="
echo "Backend:  $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
echo "Health:   ${BACKEND_URL}/health"
echo ""
echo "Verify:"
echo "  curl -s ${BACKEND_URL}/health | python -m json.tool"
