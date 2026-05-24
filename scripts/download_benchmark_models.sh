#!/bin/bash
set -euo pipefail

MODELS_DIR="/mnt/data/llama-models"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v hf &> /dev/null; then
  echo "Installing hf via pip..."
  pip install --user -U "huggingface_hub[cli]" --break-system-packages || pip install --user -U "huggingface_hub[cli]"
fi

echo "================================================================"
echo "📥 ベンチマーク用モデルのダウンロードを開始します"
echo "保存先: $MODELS_DIR"
echo "================================================================"

# 候補A: Qwen 3.6 27B Dense + MTP対応
echo "⏳ [1/3] Qwen3.6-27B-Instruct (MTP検証用) をダウンロード中..."
hf download bartowski/Qwen3.6-27B-Instruct-GGUF Qwen3.6-27B-Instruct-Q4_K_M.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Qwen3.6のダウンロードに失敗しました。"

# 候補B: Gemma 4 26B MoE
echo "⏳ [2/3] Gemma-4-26B-MoE (MoE検証用) をダウンロード中..."
hf download CelesteImperia/Gemma-4-26B-MoE-GGUF gemma-4-26b-moe-Q4_K_M.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Gemma-4-26B-MoEのダウンロードに失敗しました。"

# 候補C: Qwen 2.5 Coder 32B
echo "⏳ [3/3] Qwen2.5-Coder-32B-Instruct (コーディング特化) をダウンロード中..."
hf download Qwen/Qwen2.5-Coder-32B-Instruct-GGUF qwen2.5-coder-32b-instruct-q4_k_m.gguf --local-dir "$MODELS_DIR" || echo "⚠️ Qwen2.5-Coderのダウンロードに失敗しました。"

echo "================================================================"
echo "🎉 ダウンロード処理が完了しました。"
echo "================================================================"
