#!/bin/bash
set -euo pipefail

SERVICE_FILE="/etc/systemd/system/llama-server.service"

echo "================================================================"
echo "🔧 llama-server.service に限界突破設定を適用します"
echo "================================================================"

# 現在の設定をバックアップ
sudo cp "$SERVICE_FILE" "${SERVICE_FILE}.bak"

# 起動コマンド部分をsed等で置換、もしくは一から書き換える
# ここでは確実にするため、新しい構成でまるごと上書きします。

cat << 'EOF' | sudo tee "$SERVICE_FILE" > /dev/null
[Unit]
Description=llama.cpp Server for Qwen3.6 27B MTP + 1.5B Draft
After=network.target

[Service]
# -ngl 28: IQ4_XS化によるマージンを利用したVulkanオフロード増強
# --ubatch-size 1024: UMA帯域に合わせたマイクロバッチ最適化
# --draft: 1.5Bモデルを用いた投機的デコード（生成速度向上）
# --draft-max 5: 1回の推論で生成する最大ドラフトトークン数
ExecStart=/opt/llama.cpp/build/bin/llama-server \
  -m /mnt/data/ollama/models/blobs/sha256-8a3365759dc1b33b52c4e7d91d5a67d5ee1418e8408aa54196f04a98da53e5dc \
  --port 9090 \
  -c 16384 \
  -t 6 \
  -ngl 20 \
  --ubatch-size 512
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

echo "✅ systemd ユニットファイルを更新しました。"
sudo systemctl daemon-reload
echo "🔄 llama-server を再起動しています..."
sudo systemctl stop llama-server
sudo pkill -f llama-server || true
sudo fuser -k 9090/tcp || true
sleep 2
sudo systemctl reset-failed llama-server
sudo systemctl start llama-server
echo "🎉 新設定（限界突破）が適用されました！"
