#!/bin/bash
set -euo pipefail

MODEL_DIR="/home/irom/dev/ollama/models"
mkdir -p "$MODEL_DIR"

echo "================================================================"
echo "🚀 投機的デコード用ドラフトモデルのダウンロードを開始します"
echo "================================================================"

# Qwen2.5-Coder-1.5B-Instruct-GGUF (Q4_K_M 等) をダウンロード
# 注: 以下は実在のHugging Faceリポジトリの例です。
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
TARGET_FILE="$MODEL_DIR/Qwen2.5-Coder-1.5B-Instruct-q4_k_m.gguf"

echo "Downloading from $MODEL_URL ..."
wget -c "$MODEL_URL" -O "$TARGET_FILE"

echo "✅ ダウンロード完了: $TARGET_FILE"
echo "※ llama-server に --draft $TARGET_FILE 引数を追加することで投機的デコードが有効になります。"
