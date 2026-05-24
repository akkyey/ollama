#!/bin/bash
set -euo pipefail

LOG_FILE="/home/irom/dev/ollama/phase1_download.log"

echo "================================================================" >> "$LOG_FILE"
echo "🚀 フェーズ1: Qwen3.6-27B のダウンロードを開始します ($(date '+%Y-%m-%d %H:%M:%S'))" >> "$LOG_FILE"
echo "================================================================" >> "$LOG_FILE"

echo "1. Ollamaコンテナスタックの起動を確認・実行..." >> "$LOG_FILE"
bash /home/irom/dev/ollama/start-ollama-tailscale-stack.sh >> "$LOG_FILE" 2>&1

echo "2. Qwen3.6-27B (IQ4_XS) を Ollama 経由で取得中..." >> "$LOG_FILE"
if docker exec ollama ollama pull hf.co/unsloth/Qwen3.6-27B-GGUF:IQ4_XS >> "$LOG_FILE" 2>&1; then
  echo "✅ ダウンロードが完了しました。" >> "$LOG_FILE"
else
  echo "❌ ダウンロード中にエラーが発生しました。" >> "$LOG_FILE"
  exit 1
fi

echo "フェーズ1のタスクが完了しました。" >> "$LOG_FILE"
