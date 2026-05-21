#!/bin/bash
# =========================================================================
# Open WebUI アカウント新規登録制限適用スクリプト
# =========================================================================
set -euo pipefail

# 1. Tailscale IPの自動検出
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "127.0.0.1")

echo "⏳ DISABLE_SIGNUP=True を適用して Open WebUI コンテナを再構築中..."
docker stop open-webui
docker rm open-webui

docker run -d \
  --name open-webui \
  --network ollama-net \
  --restart unless-stopped \
  -e OLLAMA_BASE_URL=http://ollama:11434 \
  -e ENABLE_RAG_WEB_SEARCH=True \
  -e RAG_WEB_SEARCH_ENGINE=searxng \
  -e RAG_WEB_SEARCH_API_BASE_URL=http://searxng:8080/search \
  -e DISABLE_SIGNUP=True \
  -e USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -v /mnt/data/open-webui:/app/backend/data \
  -p "${TAILSCALE_IP}:3000:8080" \
  ghcr.io/open-webui/open-webui:main

echo "✅ セキュリティ制限が適用されました！新規ユーザー登録は無効化されています。"
