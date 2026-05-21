#!/bin/bash
# =========================================================================
# Ollama + SearXNG + Open WebUI クリーンアップ・初期化スクリプト
# =========================================================================
set -euo pipefail

echo "⚠️ 警告: このスクリプトはすべての Ollama スタックコンテナを停止して削除します。"
echo "ボリュームデータを削除することを選択した場合、ダウンロード済みのモデルやアカウント設定は【完全に消失】します。"
read -p "コンテナのクリーンアップを実行しますか？ (y/N): " confirm
if [[ ! "$confirm" =~ ^[yY]$ ]]; then
  echo "クリーンアップはキャンセルされました。"
  exit 0
fi

# 1. コンテナの停止と削除
echo "⏳ コンテナを停止・削除中 (open-webui, searxng, ollama)..."
docker stop open-webui searxng ollama 2>/dev/null || true
docker rm open-webui searxng ollama 2>/dev/null || true

# 2. ブリッジネットワークの削除
echo "⏳ Docker ネットワークを削除中 (ollama-net)..."
docker network rm ollama-net 2>/dev/null || true

# 3. ボリュームデータの削除確認（完全初期化）
read -p "/mnt/data 内のすべての永続データ（モデルおよびユーザーアカウント）も削除しますか？ (y/N): " delete_data
if [[ "$delete_data" =~ ^[yY]$ ]]; then
  echo "⏳ 永続データディレクトリを削除中..."
  rm -rf /mnt/data/ollama /mnt/data/open-webui /mnt/data/searxng
  echo "✅ 永続データディレクトリが削除されました。"
else
  echo "ℹ️ 永続データは保持されました。スタックを再起動すれば、既存의モデルとアカウントを引き続き利用できます。"
fi

# 4. スタックの再起動プロンプト（容易な初期化・再構築の実現）
read -p "今すぐ Ollama スタックを再起動（再構築）しますか？ (y/N): " restart_stack
if [[ "$restart_stack" =~ ^[yY]$ ]]; then
  echo "⏳ スタックを起動中..."
  if [ -f "./start-ollama-tailscale-stack.sh" ]; then
    ./start-ollama-tailscale-stack.sh
  else
    echo "⚠️ 現在のディレクトリに start-ollama-tailscale-stack.sh が見つかりません。"
  fi
fi

echo "================================================================"
echo "✅ クリーンアップおよび初期化処理が正常に完了しました！"
echo "================================================================"
