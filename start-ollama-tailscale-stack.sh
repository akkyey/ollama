#!/bin/bash
# =========================================================================
# Ollama + SearXNG + Open WebUI (Tailscaleバインド) Dockerスタック起動スクリプト
# =========================================================================
set -euo pipefail

# 1. Tailscale IPの自動検出
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")
if [ -z "$TAILSCALE_IP" ]; then
  echo "⚠️ Tailscale IPが検出されませんでした。Tailscaleが起動していない可能性があります。"
  echo "ローカルホスト（127.0.0.1）にバインドします。"
  TAILSCALE_IP="127.0.0.1"
else
  echo "ℹ️ 検出されたTailscale IP: $TAILSCALE_IP"
fi

# 2. ディレクトリ準備
echo "⏳ [Step 1/6] /mnt/data 配下にホストディレクトリを準備中..."
mkdir -p /mnt/data/docker /mnt/data/ollama /mnt/data/open-webui /mnt/data/searxng
chmod 777 /mnt/data/ollama /mnt/data/open-webui /mnt/data/searxng

# 3. ネットワーク作成
echo "⏳ [Step 2/6] 専用のDockerブリッジネットワークを作成中..."
docker network create ollama-net 2>/dev/null || true

# 4. 既存の同名コンテナのクリーンアップ（起動の冪等性確保）
echo "⏳ [Step 3/6] 既存のコンテナのクリーンアップを実行中..."
docker stop open-webui searxng ollama 2>/dev/null || true
docker rm open-webui searxng ollama 2>/dev/null || true

# 5. Ollama コンテナ起動 (ホスト側 127.0.0.1:11434 のみにバインド)
echo "⏳ [Step 4/6] Ollamaコンテナを起動中 (CPU最適化)..."
docker run -d \
  --name ollama \
  --network ollama-net \
  --restart unless-stopped \
  -v /mnt/data/ollama:/root/.ollama \
  -p 127.0.0.1:11434:11434 \
  ollama/ollama

# 6. SearXNG コンテナ起動 (ホストの外部ポートには露出させず、ブリッジ内でのみ通信)
echo "⏳ [Step 5/6] SearXNGコンテナを起動中 (Web検索RAG用)..."
docker run -d \
  --name searxng \
  --network ollama-net \
  --restart unless-stopped \
  -v /mnt/data/searxng:/etc/searxng \
  searxng/searxng

# 7. Open WebUI コンテナ起動 (Tailscale IPの3000番ポートにのみバインド)
# ※初回起動時は、管理者アカウント作成のために DISABLE_SIGNUP=True を指定せず起動します。
echo "⏳ [Step 6/6] Open WebUIコンテナを起動中 (Ollama & SearXNGに接続)..."
docker run -d \
  --name open-webui \
  --network ollama-net \
  --restart unless-stopped \
  -e OLLAMA_BASE_URL=http://ollama:11434 \
  -e ENABLE_RAG_WEB_SEARCH=True \
  -e RAG_WEB_SEARCH_ENGINE=searxng \
  -e RAG_WEB_SEARCH_API_BASE_URL=http://searxng:8080/search \
  -e BYPASS_WEB_SEARCH_WEB_LOADER=True \
  -e USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -v /mnt/data/open-webui:/app/backend/data \
  -p "${TAILSCALE_IP}:3000:8080" \
  ghcr.io/open-webui/open-webui:main

# 8. Open WebUI の WebBaseLoader バグ（allow_redirectsの重複によるTypeError）へのパッチ適用
echo "⏳ Open WebUI の WebBaseLoader へのバグパッチを適用中..."
# コンテナが起動してファイルシステムが利用可能になるまで待機
sleep 3
docker exec open-webui sed -i '/allow_redirects=AIOHTTP_CLIENT_ALLOW_REDIRECTS,/d' /app/backend/open_webui/retrieval/web/utils.py

# 9. gemma2:2b の Function Calling を無効化して強制RAGを有効化するパッチ
echo "⏳ gemma2:2b の Function Calling 無効化パッチを適用中..."
cat << 'EOF' | docker exec -i open-webui python
import sys
file_path = "/app/backend/open_webui/main.py"
with open(file_path, "r") as f:
    content = f.read()

target = """                'function_calling': (
                    'native'
                    if (
                        form_data.get('params', {}).get('function_calling') == 'native'
                        or model_info_params.get('function_calling') == 'native'
                    )
                    else 'default'
                ),"""

replacement = """                'function_calling': (
                    'native'
                    if (
                        (form_data.get('params', {}).get('function_calling') == 'native'
                        or model_info_params.get('function_calling') == 'native')
                        and model_id != 'gemma2:2b'
                    )
                    else 'default'
                ),"""

if target in content:
    with open(file_path, "w") as f:
        f.write(content.replace(target, replacement))
    print("SUCCESS")
elif replacement in content:
    print("ALREADY PATCHED")
else:
    print("WARNING: Target string not found in main.py")
EOF

docker restart open-webui

echo "================================================================"
echo "🎉 Ollama + SearXNG + Open WebUI スタックが正常に起動しました！"
echo "----------------------------------------------------------------"
echo "  📌 Ollama API (ローカル限定) : http://127.0.0.1:11434"
echo "  📌 Open WebUI (Tailscale)    : http://${TAILSCALE_IP}:3000"
echo "================================================================"
echo "👉 次のアクション: http://${TAILSCALE_IP}:3000 にアクセスして管理者登録を行ってください。"
echo "   登録完了後、制限をかけるために次のスクリプトを実行してください: ./apply-security-restriction.sh"

