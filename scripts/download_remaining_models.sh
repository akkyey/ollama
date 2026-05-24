#!/bin/bash
set -euo pipefail

MODELS_DIR="/mnt/data/llama-models"
export PATH="$HOME/.local/bin:$PATH"

echo "================================================================"
echo "📥 追加のベンチマーク用モデル（2026年最新版）のダウンロードを開始します"
echo "保存先: $MODELS_DIR"
echo "================================================================"

# 候補A: Qwen 3.6 27B MTP対応版
echo "⏳ [1/2] Qwen3.6-27B-MTP-GGUF (Q4_K_M) をダウンロード中..."
hf download unsloth/Qwen3.6-27B-MTP-GGUF Qwen3.6-27B-Q4_K_M.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Qwen3.6のダウンロードに失敗しました。"

# 候補B: Gemma 4 31B (マルチモーダル対応)
echo "⏳ [2/2] gemma-4-31B-it-GGUF (Q4_K_M) をダウンロード中..."
hf download unsloth/gemma-4-31B-it-GGUF gemma-4-31B-it-Q4_K_M.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Gemma-4のダウンロードに失敗しました。"

echo "================================================================"
echo "🎉 追加ダウンロード処理が完了しました。"
echo "================================================================"
