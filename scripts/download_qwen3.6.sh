#!/bin/bash
set -e

MODEL_DIR="/home/irom/dev/ollama/models"
mkdir -p "$MODEL_DIR"

echo "Downloading Qwen3.6-27B-GGUF (IQ4_XS) from unsloth..."
# 注意: URLはダミーではなく、Hugging Faceの標準的なファイルパスの構造を使用
# wget -c (continue) で中断・再開に対応
wget -c "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/main/Qwen3.6-27B-IQ4_XS.gguf" -O "$MODEL_DIR/Qwen3.6-27B-IQ4_XS.gguf"

echo "Download completed: $MODEL_DIR/Qwen3.6-27B-IQ4_XS.gguf"
