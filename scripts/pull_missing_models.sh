#!/bin/bash
# =========================================================================
# WebUI用: ベンチマーク済みモデル (Gemma 4 & Qwen2.5-Coder 32B) の登録スクリプト
# =========================================================================
set -euo pipefail

LOG_FILE="/home/irom/dev/ollama/pull_missing_models.log"

echo "================================================================" >> "$LOG_FILE"
echo "📥 モデルのPullを開始します (開始時刻: $(date '+%Y-%m-%d %H:%M:%S'))" >> "$LOG_FILE"
echo "================================================================" >> "$LOG_FILE"

# 追加対象モデル一覧
MODELS=(
  "qwen2.5-coder:32b"
  "hf.co/unsloth/gemma-4-31B-it-GGUF:Q4_K_M"
)

for MODEL in "${MODELS[@]}"; do
  echo "⏳ [$(date '+%Y-%m-%d %H:%M:%S')] ${MODEL} のダウンロードを開始します..." | tee -a "$LOG_FILE"
  if docker exec ollama ollama pull "$MODEL" >> "$LOG_FILE" 2>&1; then
    echo "✅ [$(date '+%Y-%m-%d %H:%M:%S')] ${MODEL} のダウンロードが完了しました。" | tee -a "$LOG_FILE"
  else
    echo "❌ [$(date '+%Y-%m-%d %H:%M:%S')] ${MODEL} のダウンロード中にエラーが発生しました。" | tee -a "$LOG_FILE"
  fi
done

echo "================================================================" >> "$LOG_FILE"
echo "🎉 すべてのモデルのPull処理が終了しました (終了時刻: $(date '+%Y-%m-%d %H:%M:%S'))" >> "$LOG_FILE"
echo "================================================================" >> "$LOG_FILE"
