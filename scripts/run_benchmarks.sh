#!/bin/bash
set -euo pipefail

MODELS_DIR="/mnt/data/llama-models"
LLAMA_BENCH="/opt/llama.cpp/build/bin/llama-bench"

if [ ! -f "$LLAMA_BENCH" ]; then
  echo "Error: llama-bench not found at $LLAMA_BENCH. Please build llama.cpp first."
  exit 1
fi

if [ ! -d "$MODELS_DIR" ] || [ -z "$(ls -A "$MODELS_DIR"/*.gguf 2>/dev/null)" ]; then
  echo "Error: No .gguf models found in $MODELS_DIR."
  echo "Please download models (e.g. Qwen2.5-Coder, Gemma 4, Qwen3.6) into $MODELS_DIR first."
  exit 1
fi

echo "================================================================"
echo "🚀 Starting Benchmarks for all GGUF models in $MODELS_DIR"
echo "================================================================"

for model in "$MODELS_DIR"/*.gguf; do
  model_name=$(basename "$model")
  echo ""
  echo "----------------------------------------------------------------"
  echo "📊 Benchmarking: $model_name"
  echo "----------------------------------------------------------------"
  
  # Standard benchmark (no MTP)
  echo "[Standard Run]"
  "$LLAMA_BENCH" -m "$model" -p 512,1024 -n 512 -t 6

  # Try MTP benchmark if the model might support it
  echo ""
  echo "[MTP (Multi-Token Prediction) Run]"
  "$LLAMA_BENCH" -m "$model" -p 512 -n 512 -t 6 --spec-type draft-mtp || echo "MTP run failed or unsupported for this model."

done

echo ""
echo "================================================================"
echo "🎉 All Benchmarks Completed!"
echo "================================================================"
