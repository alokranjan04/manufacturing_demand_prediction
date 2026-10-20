# GCP Deployment Guide — Chemical Manufacturing AI

**Project:** `nth-infusion-490008-h8`
**Region:** `asia-south1` (Mumbai)
**Services:** `chem-ai-backend` · `chem-ai-frontend`
**Registry:** `asia-south1-docker.pkg.dev/nth-infusion-490008-h8/chem-ai`

---

## Deployment Architecture

```
GitHub push to main
        │
        ▼
GitHub Actions (.github/workflows/deploy.yml)
        │
        ├── Build backend image  → push to Artifact Registry
        │   └── Deploy chem-ai-backend  (Cloud Run, port 8080)
        │
        ├── Build frontend image (VITE_API_BASE_URL = backend URL)
        │   └── Deploy chem-ai-frontend (Cloud Run, nginx port 80)
        │
        └── Update backend CORS with frontend URL
```

Three deployment paths:

| Path | Trigger | Entry point |
|---|---|---|
| Manual | Run script locally | `deploy_gcp.sh` |
| Cloud Build | `gcloud builds submit` | `cloudbuild.yaml` |
| GitHub Actions | Push to `main` | `.github/workflows/deploy.yml` |

---

## 0. Prerequisites

```bash
gcloud version
docker version
gcloud auth login
gcloud config set project nth-infusion-490008-h8
```

---

## 1. One-Time Setup

### 1.1 Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project=nth-infusion-490008-h8 --quiet
```

### 1.2 Create Artifact Registry Repository

```bash
gcloud artifacts repositories create chem-ai \
  --repository-format=docker \
  --location=asia-south1 \
  --project=nth-infusion-490008-h8 --quiet
```

### 1.3 Configure Docker Authentication

```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet
```

---

## 2. Store Secrets in Secret Manager

All credentials are stored as GCP secrets — never in environment variables or code.

```bash
# OpenRouter LLM
printf 'sk-or-v1-YOUR_KEY' | gcloud secrets create OPENROUTER_API_KEY \
  --data-file=- --project=nth-infusion-490008-h8

# Databricks PAT token (must have all-apis scope)
printf 'dapiXXXXXXXXXXXXXXXX' | gcloud secrets create DATABRICKS_TOKEN \
  --data-file=- --project=nth-infusion-490008-h8

# Databricks SQL Warehouse hostname
printf 'dbc-94d529e8-ac2d.cloud.databricks.com' | gcloud secrets create DATABRICKS_SERVER_HOSTNAME \
  --data-file=- --project=nth-infusion-490008-h8

# Databricks SQL Warehouse HTTP path
printf '/sql/1.0/warehouses/6fa4cb8503195eed' | gcloud secrets create DATABRICKS_HTTP_PATH \
  --data-file=- --project=nth-infusion-490008-h8

# Databricks Job ID for the Chem_AI_pipeline job
printf '75154047801016' | gcloud secrets create DATABRICKS_JOB_ID \
  --data-file=- --project=nth-infusion-490008-h8

# Databricks Volume path for CSV uploads
printf '/Volumes/chem_ai/bronze/raw_files' | gcloud secrets create DATABRICKS_VOLUME_INCOMING_PATH \
  --data-file=- --project=nth-infusion-490008-h8
```

Update an existing secret:

```bash
printf 'NEW_VALUE' | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=nth-infusion-490008-h8
```

Verify all secrets exist:

```bash
gcloud secrets list --project=nth-infusion-490008-h8
```

---

## 3. IAM Permissions

### 3.1 GitHub Actions Service Account

```bash
gcloud iam service-accounts create github-sa \
  --display-name="GitHub Actions Deploy SA" \
  --project=nth-infusion-490008-h8

PROJECT=nth-infusion-490008-h8
SA_EMAIL="github-sa@${PROJECT}.iam.gserviceaccount.com"

for ROLE in \
  roles/run.admin \
  roles/artifactregistry.writer \
  roles/secretmanager.secretAccessor \
  roles/cloudbuild.builds.editor \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done

# Generate key for GitHub Secrets
gcloud iam service-accounts keys create github-sa-key.json \
  --iam-account="${SA_EMAIL}" --project=nth-infusion-490008-h8
```

### 3.2 Cloud Build Service Account

```bash
CB_SA=$(gcloud projects describe nth-infusion-490008-h8 \
  --format="value(projectNumber)")@cloudbuild.gserviceaccount.com

for ROLE in roles/run.admin roles/secretmanager.secretAccessor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding nth-infusion-490008-h8 \
    --member="serviceAccount:${CB_SA}" --role="$ROLE"
done
```

### 3.3 Cloud Run Runtime Service Account

```bash
CR_SA=$(gcloud projects describe nth-infusion-490008-h8 \
  --format="value(projectNumber)")-compute@developer.gserviceaccount.com

gcloud projects add-iam-policy-binding nth-infusion-490008-h8 \
  --member="serviceAccount:${CR_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 4. Path A — Manual Deploy

```bash
chmod +x deploy_gcp.sh
# Edit the REPLACE_WITH_* values in the script first
./deploy_gcp.sh
```

Script workflow:
1. Set project + authenticate Docker
2. Enable APIs
3. Create Artifact Registry repo (idempotent)
4. Store secrets (skip if already exist)
5. Build + push backend image
6. Deploy `chem-ai-backend` to Cloud Run
7. Build frontend with `VITE_API_BASE_URL` = live backend URL
8. Push + deploy `chem-ai-frontend` to Cloud Run
9. Update backend CORS with live frontend URL
10. Print both URLs

---

## 5. Path B — Cloud Build

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=nth-infusion-490008-h8
```

> **Note:** `cloudbuild.yaml` has placeholder backend/frontend URLs in the `build-frontend` step.
> Update these after the first deploy with the real Cloud Run URLs, then redeploy.

Watch logs:

```bash
gcloud builds log BUILD_ID --stream --project=nth-infusion-490008-h8
```

---

## 6. Path C — GitHub Actions (Recommended)

### 6.1 Add GitHub Secrets

In GitHub → repo → **Settings → Environments → GCP_Account_Setup → Secrets**:

| Secret | Value |
|---|---|
| `GCP_SA_KEY` | Contents of `github-sa-key.json` |
| `GCP_PROJECT_ID` | `nth-infusion-490008-h8` |

### 6.2 Trigger

```bash
git push origin main
```

Or manually in GitHub → **Actions → Deploy to GCP Cloud Run → Run workflow**.

The workflow:
1. Builds backend → pushes → deploys `chem-ai-backend`
2. Gets live backend URL
3. Builds frontend with that URL baked in → pushes → deploys `chem-ai-frontend`
4. Updates backend CORS with frontend URL
5. Posts summary with both URLs

---

## 7. Cloud Run Service Configuration

### Backend (`chem-ai-backend`)

| Setting | Value |
|---|---|
| Image | `asia-south1-docker.pkg.dev/nth-infusion-490008-h8/chem-ai/backend:SHA` |
| Port | 8080 |
| CPU | 2 vCPU |
| Memory | 2 GiB |
| Min instances | 1 (always warm) |
| Max instances | 5 |
| Timeout | 120s |
| Secrets mounted | All 6 Databricks + OpenRouter secrets |
| Env vars | `OPENROUTER_MODEL`, `CHEM_AI_CATALOG`, `DEVIATION_THRESHOLD_PCT`, `ALLOWED_ORIGINS` |

### Frontend (`chem-ai-frontend`)

| Setting | Value |
|---|---|
| Image | `asia-south1-docker.pkg.dev/nth-infusion-490008-h8/chem-ai/frontend:SHA` |
| Port | 80 (nginx) |
| CPU | 1 vCPU |
| Memory | 512 MiB |
| Min instances | 0 (scales to zero) |
| Max instances | 3 |
| Build arg | `VITE_API_BASE_URL` = backend Cloud Run URL |

---

## 8. Verify Deployment

```bash
# Get URLs
gcloud run services describe chem-ai-backend \
  --region=asia-south1 --format="value(status.url)"

gcloud run services describe chem-ai-frontend \
  --region=asia-south1 --format="value(status.url)"

# Health check
curl -s https://chem-ai-backend-HASH-el.a.run.app/health | python -m json.tool

# Tail logs
gcloud run services logs tail chem-ai-backend --region=asia-south1
gcloud run services logs tail chem-ai-frontend --region=asia-south1

# List images
gcloud artifacts docker images list \
  asia-south1-docker.pkg.dev/nth-infusion-490008-h8/chem-ai/backend \
  --include-tags
```

---

## 9. Subsequent Deploys

| Scenario | Command |
|---|---|
| Full redeploy (recommended) | `git push origin main` |
| Update a secret value | `printf 'NEW_VAL' \| gcloud secrets versions add SECRET_NAME --data-file=-` |
| Update env var only | `gcloud run services update chem-ai-backend --set-env-vars="KEY=VAL" --region=asia-south1` |
| Roll back | `gcloud run services update-traffic chem-ai-backend --to-revisions=REVISION=100 --region=asia-south1` |
| Force Cloud Build | `gcloud builds submit --config=cloudbuild.yaml` |

---

## 10. Files Created

| File | Purpose |
|---|---|
| `backend/Dockerfile` | Python 3.12-slim + uv, exposes port 8080 |
| `frontend/Dockerfile` | Multi-stage: Node build → nginx:alpine |
| `frontend/nginx.conf` | SPA routing fallback + static asset caching |
| `cloudbuild.yaml` | Cloud Build pipeline: build + push + deploy both services |
| `deploy_gcp.sh` | Manual one-shot deploy script |
| `.github/workflows/deploy.yml` | GitHub Actions: auto-deploy on push to main |
| `docs/gcp-deployment-guide.md` | This file |
