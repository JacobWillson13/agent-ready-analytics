#!/usr/bin/env bash
# Load generated parquet into BigQuery: raw/<dataset>/<table>.parquet -> <dataset>.<table>,
# truth/*.parquet -> eval_truth.*  Usage: GCP_PROJECT=my-proj scripts/load_bq.sh [data_dir]
set -euo pipefail
DATA=${1:-data}
: "${GCP_PROJECT:?set GCP_PROJECT}"
LOC=${BQ_LOCATION:-US}

for ds in raw_salesforce raw_app raw_segment raw_metronome raw_support raw_pypi raw_github eval_truth; do
  bq --location="$LOC" mk -f --dataset "$GCP_PROJECT:$ds" >/dev/null
done

for f in "$DATA"/raw/*/*.parquet; do
  ds=$(basename "$(dirname "$f")"); t=$(basename "$f" .parquet)
  echo "loading $ds.$t"
  bq --location="$LOC" load --replace --source_format=PARQUET --parquet_enable_list_inference \
    "$GCP_PROJECT:$ds.$t" "$f"
done

for f in "$DATA"/truth/*.parquet; do
  t=$(basename "$f" .parquet)
  echo "loading eval_truth.$t"
  bq --location="$LOC" load --replace --source_format=PARQUET "$GCP_PROJECT:eval_truth.$t" "$f"
done
echo "done. Remember: the agent's service account must NOT have access to eval_truth."
