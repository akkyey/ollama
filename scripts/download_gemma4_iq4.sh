#!/bin/bash
set -euo pipefail

MODEL_DIR="/home/irom/dev/ollama/models"
mkdir -p "$MODEL_DIR"

echo "================================================================"
echo "🚀 Gemma4-26B-MoE-GGUF (IQ4_XS) のダウンロードを開始します"
echo "================================================================"

# ※ 注意: Gemma4(仮称/26B MoE) は検証用の最新モデルを想定したURLです。
# 実際には Hugging Face 上の対応するリポジトリを指定してください。
MODEL_URL="https://huggingface.co/unsloth/Gemma4-26B-MoE-GGUF/resolve/main/Gemma4-26B-MoE-IQ4_XS.gguf"
TARGET_FILE="$MODEL_DIR/Gemma4-26B-MoE-IQ4_XS.gguf"

echo "Downloading from $MODEL_URL ..."
wget -c "$MODEL_URL" -O "$TARGET_FILE"

echo "✅ ダウンロード完了: $TARGET_FILE"
echo "※ このモデルを llama-server に読み込ませるには、/etc/systemd/system/llama-server.service の -m 引数をこのファイルパスに変更し、systemctl restart llama-server を実行してください。"
