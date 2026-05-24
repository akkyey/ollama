#!/bin/bash
set -euo pipefail

LOG_FILE="/home/irom/dev/ollama/setup_llama_server_systemd.log"
SERVICE_FILE="/etc/systemd/system/llama-server.service"

# GGUFモデルのパス (OllamaがダウンロードしたBlobをそのまま参照する)
MODEL_BLOB="/mnt/data/ollama/models/blobs/sha256-8a3365759dc1b33b52c4e7d91d5a67d5ee1418e8408aa54196f04a98da53e5dc"

echo "================================================================" | tee -a "$LOG_FILE"
echo "🚀 フェーズ3: systemd ユニットとしての隔離とデプロイ ($(date '+%Y-%m-%d %H:%M:%S'))" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"

# 1. systemdユニットファイルの作成
echo "1. systemdユニットファイル ($SERVICE_FILE) を作成中..." | tee -a "$LOG_FILE"

sudo bash -c "cat << 'EOF' > $SERVICE_FILE
[Unit]
Description=llama.cpp Server for Qwen3.6 27B MTP
After=network.target

[Service]
ExecStart=/opt/llama.cpp/build/bin/llama-server -m ${MODEL_BLOB} --port 9090 -c 8192 -t 6
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF"

echo "✅ ユニットファイルを作成しました。" | tee -a "$LOG_FILE"

# 2. systemdデーモンのリロードとサービスの有効化
echo "2. systemdデーモンをリロードし、llama-server を有効化・起動中..." | tee -a "$LOG_FILE"
sudo systemctl daemon-reload >> "$LOG_FILE" 2>&1
sudo systemctl enable llama-server >> "$LOG_FILE" 2>&1
# sudo systemctl start llama-server >> "$LOG_FILE" 2>&1

echo "================================================================" | tee -a "$LOG_FILE"
echo "🎉 フェーズ3のタスクが完了しました ($(date '+%Y-%m-%d %H:%M:%S'))" | tee -a "$LOG_FILE"
echo "※ 実際の起動テストはzRAM等のメモリ周りの整備（フェーズ4）の後に行うか、手動で sudo systemctl start llama-server を実行してください。" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
