#!/bin/bash
set -euo pipefail

MODELS_DIR="/mnt/data/llama-models"
export PATH="$HOME/.local/bin:$PATH"

echo "================================================================"
echo "📥 Agentic Switch用 最適化モデルのダウンロードを開始します"
echo "保存先: $MODELS_DIR"
echo "================================================================"

# 1. Askモード用: Qwen2.5-14B (爆速応答用)
echo "⏳ [1/2] Qwen2.5-14B-Instruct-GGUF (Q4_K_M) をダウンロード中..."
hf download Qwen/Qwen2.5-14B-Instruct-GGUF --include "qwen2.5-14b-instruct-q4_k_m*.gguf" --local-dir "$MODELS_DIR" || echo "⚠️ 14Bのダウンロードに失敗しました。"

# 2. Reviewモード用: Gemma-4-31B-it (Q3_K_M) 
echo "⏳ [2/2] gemma-4-31B-it-GGUF (Q3_K_M) をダウンロード中..."
hf download unsloth/gemma-4-31B-it-GGUF gemma-4-31B-it-Q3_K_M.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Gemma-4のダウンロードに失敗しました。"

echo "================================================================"
echo "🎉 Agentic Switch用モデルのダウンロードが完了しました。"
echo "================================================================"
