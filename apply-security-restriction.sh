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
  -e ENABLE_API_KEYS=True \
  -e BYPASS_WEB_SEARCH_WEB_LOADER=False \
  -e ENABLE_SEARCH_QUERY_GENERATION=True \
  -e ENABLE_RETRIEVAL_QUERY_GENERATION=True \
  -e USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -v /mnt/data/open-webui:/app/backend/data \
  -p "${TAILSCALE_IP}:3000:8080" \
  ghcr.io/open-webui/open-webui:main

# Open WebUI の WebBaseLoader バグ（allow_redirectsの重複によるTypeError）へのパッチ適用
echo "⏳ Open WebUI の WebBaseLoader へのバグパッチを適用中..."
sleep 3
docker exec open-webui sed -i '/allow_redirects=AIOHTTP_CLIENT_ALLOW_REDIRECTS,/d' /app/backend/open_webui/retrieval/web/utils.py

# gemma2:2b の Function Calling を無効化して強制RAGを有効化するパッチ
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

# クエリ生成JSONパースパッチの適用
echo "⏳ クエリ生成JSONパースパッチを適用中..."
cat << 'EOF' | docker exec -i open-webui python
import sys
file_path = "/app/backend/open_webui/utils/middleware.py"
with open(file_path, "r") as f:
    content = f.read()

target = """            bracket_start = response.rfind('{')
            bracket_end = response.rfind('}') + 1"""

replacement = """            bracket_start = response.find('{')
            bracket_end = response.rfind('}') + 1"""

if target in content:
    with open(file_path, "w") as f:
        f.write(content.replace(target, replacement))
    print("SUCCESS")
elif replacement in content:
    print("ALREADY PATCHED")
else:
    print("WARNING: Target string not found in middleware.py")
EOF

docker restart open-webui

echo "✅ セキュリティ制限が適用されました！新規ユーザー登録は無効化されています。"

