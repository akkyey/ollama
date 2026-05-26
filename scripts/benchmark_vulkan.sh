#!/bin/bash
set -e

MODELS_DIR="/mnt/data/llama-models"
LLAMA_BENCH="/opt/llama.cpp/build/bin/llama-bench"

if [ ! -f "$LLAMA_BENCH" ]; then
    echo "Error: llama-bench not found. Please build it first."
    exit 1
fi

echo "=========================================================="
echo "🚀 性能測定 (全モデル一括テスト) を開始します..."
echo "=========================================================="

for MODEL in "$MODELS_DIR"/*.gguf; do
    echo ""
    echo "----------------------------------------------------------"
    BASENAME=$(basename "$MODEL")
    echo "📦 測定対象: $BASENAME"
    echo "----------------------------------------------------------"
    # iGPU (RADV) の DeviceLost 回避のため、Gemma等重いモデルはレイヤー数を減らします
    NGL=20
    if [[ "$MODEL" == *"gemma"* ]]; then
        NGL=0
    fi
    $LLAMA_BENCH -m "$MODEL" -p 512 -n 128 -t 6 -ngl $NGL
done

echo "=========================================================="
echo "✅ 全モデルの性能測定完了"
