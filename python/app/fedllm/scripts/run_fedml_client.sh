#!/usr/bin/env bash
set -e

BASE_DIR="$(dirname "$0")"
BASE_DIR="$(realpath "${BASE_DIR}/../")"
cd "${BASE_DIR}"

export WANDB_MODE=disabled # remove this line if you want to use wandb

# FedML setting
RANK="$1"
RUN_ID="$2"

# GPU setting
TORCH_DISTRIBUTED_DEFAULT_PORT="${TORCH_DISTRIBUTED_DEFAULT_PORT:-29500}"

MASTER_ADDR="${3:-"localhost"}"
MASTER_PORT="${4:-$((TORCH_DISTRIBUTED_DEFAULT_PORT + RANK))}"
NUM_NODES="${5:-1}"

# FedML config
CONFIG_PATH="fedml_config/fedml_config.yaml"

bash scripts/run_fedml.sh \
  "${MASTER_ADDR}" \
  "${MASTER_PORT}" \
  "${NUM_NODES}" \
  main_fedllm.py \
  --cf "${CONFIG_PATH}" \
  --rank "${RANK}" \
  --role client \
  --run_id "${RUN_ID}"
