#!/bin/bash
set -euo pipefail

LOG_FILE="/home/irom/dev/ollama/setup_llama_cpp.log"
INSTALL_DIR="/opt/llama.cpp"

echo "================================================================" | tee -a "$LOG_FILE"
echo "🚀 フェーズ2: llama.cpp のネイティブビルドを開始します ($(date '+%Y-%m-%d %H:%M:%S'))" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"

# 0. 依存パッケージのインストール
echo "0. 依存パッケージ (cmake, build-essential) をインストール中..." | tee -a "$LOG_FILE"
sudo apt-get update >> "$LOG_FILE" 2>&1
sudo apt-get install -y cmake build-essential >> "$LOG_FILE" 2>&1

# 1. ディレクトリの準備
echo "1. インストールディレクトリ (${INSTALL_DIR}) を準備中..." | tee -a "$LOG_FILE"
if [ ! -d "$INSTALL_DIR" ]; then
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown -R "$USER:$USER" "$INSTALL_DIR"
fi


cd "$INSTALL_DIR"

# 2. ソースコードの取得
if [ -d ".git" ]; then
    echo "2. 既存のリポジトリを更新中..." | tee -a "$LOG_FILE"
    git fetch origin
    git reset --hard origin/master
else
    echo "2. llama.cpp をクローン中..." | tee -a "$LOG_FILE"
    git clone https://github.com/ggerganov/llama.cpp .
fi

# 3. ネイティブビルドの実行 (CMake)
echo "3. CMakeを使用してネイティブビルド (-DGGML_NATIVE=ON) を実行中..." | tee -a "$LOG_FILE"
# 既存のビルドディレクトリを削除
rm -rf build

# CMakeの構成とビルド
cmake -B build -DGGML_NATIVE=ON >> "$LOG_FILE" 2>&1
cmake --build build --config Release -j 6 >> "$LOG_FILE" 2>&1

if [ -f "build/bin/llama-server" ]; then
    echo "✅ ビルド成功: llama-server バイナリが生成されました。" | tee -a "$LOG_FILE"
    ./build/bin/llama-server --help | head -n 5 | tee -a "$LOG_FILE"

else
    echo "❌ ビルド失敗: llama-server バイナリが見つかりません。" | tee -a "$LOG_FILE"
    exit 1
fi

echo "================================================================" | tee -a "$LOG_FILE"
echo "🎉 フェーズ2のタスクが完了しました ($(date '+%Y-%m-%d %H:%M:%S'))" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
