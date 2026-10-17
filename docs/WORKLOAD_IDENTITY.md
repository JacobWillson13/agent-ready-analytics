# Keyless CI auth: Workload Identity Federation

CI authenticates to Google Cloud without stored service account keys. GitHub Actions issues a short-lived
OIDC token for each run; Google Cloud exchanges it for temporary credentials on one of two service
accounts. The provider only accepts tokens from this repository.

| Service account | Used by | Access |
|---|---|---|
| `ara-ci` | `dbt` job | Read and write all datasets, including `eval_truth` (reconciliation tests) |
| `ara-agent` | `context-eval` job | Read all datasets except `eval_truth` |

## One-time setup

Run with the project's gcloud login (`source ~/.config/ara/env` sets `CLOUDSDK_CONFIG` and `GCP_PROJECT`).

```
PROJECT_ID=$GCP_PROJECT
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
REPO=JacobWillson13/agent-ready-analytics
POOL=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project $PROJECT_ID

gcloud iam workload-identity-pools create github \
  --project $PROJECT_ID --location global --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc agent-ready-analytics \
  --project $PROJECT_ID --location global --workload-identity-pool github \
  --display-name "agent-ready-analytics" \
  --issuer-uri https://token.actions.githubusercontent.com \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository == '$REPO'"

for SA in ara-ci ara-agent; do
  gcloud iam service-accounts add-iam-policy-binding $SA@$PROJECT_ID.iam.gserviceaccount.com \
    --project $PROJECT_ID --role roles/iam.workloadIdentityUser \
    --member "principalSet://iam.googleapis.com/$POOL/attribute.repository/$REPO"
done

gh variable set GCP_WIF_PROVIDER --body "$POOL/providers/agent-ready-analytics"
gh variable set GCP_CI_SA --body "ara-ci@$PROJECT_ID.iam.gserviceaccount.com"
gh variable set GCP_AGENT_SA --body "ara-agent@$PROJECT_ID.iam.gserviceaccount.com"
```

`GCP_PROJECT`, `ANTHROPIC_API_KEY`, and `LANGSMITH_API_KEY` stay as repository secrets.

## Retire the old keys

After one CI run passes with the new auth:

```
gh secret delete GCP_CI_SA_KEY
gh secret delete GCP_AGENT_SA_KEY
for SA in ara-ci ara-agent; do
  gcloud iam service-accounts keys list --iam-account $SA@$PROJECT_ID.iam.gserviceaccount.com --managed-by user
done
gcloud iam service-accounts keys delete KEY_ID --iam-account SA_EMAIL   # for each key listed above
```

## Why this is safe for a public repository

- The attribute condition rejects tokens from any other repository, including forks.
- GitHub does not give pull requests from forks an OIDC token or repository secrets, so the eval jobs skip
  on fork PRs.
- No long-lived credential exists to leak.
