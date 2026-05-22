#!/bin/bash
# =========================================================================
# Ollama サーバー環境セットアップスクリプト（再起動用・メモリ最適化込み）
# =========================================================================
# 用途: サーバー再起動後に実行し、OS・Docker・Ollamaの全環境を
#       メモリ圧縮・効率使用の設定込みで一括セットアップする。
#
# 実行方法:
#   cd /home/irom/dev/ollama
#   sudo ./setup-ollama-environment.sh
#
# 前提条件:
#   - Ubuntu ホストサーバー (48GB RAM, CPU推論)
#   - Docker がインストール済み
#   - Tailscale がセットアップ済み
#   - /mnt/data が NVMe SSD としてマウント済み
#   - Open WebUI の管理者アカウントが作成済み（本番運用状態）
# =========================================================================
set -euo pipefail

# =========================================================================
# 定数定義
# =========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/setup-$(date +%Y%m%d_%H%M%S).log"
DATA_DIR="/mnt/data"

# Ollama メモリ最適化パラメータ
OLLAMA_KV_CACHE_TYPE="q8_0"       # KVキャッシュ量子化（q8_0: 約50%メモリ削減）
OLLAMA_FLASH_ATTENTION="1"        # Flash Attention 有効化
OLLAMA_NUM_PARALLEL="2"           # 並列リクエスト数（CPU推論では2が最適）
OLLAMA_MAX_LOADED_MODELS="1"      # 同時ロードモデル数（メモリ節約のため1に制限）

# zRAM パラメータ
ZRAM_SIZE_PERCENT=50              # 物理RAMの50%をzRAMに割り当て
ZRAM_ALGORITHM="zstd"             # 圧縮アルゴリズム（zstd: 圧縮率と速度のバランスが最良）

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =========================================================================
# ユーティリティ関数
# =========================================================================
log_step() {
    local step_num="$1"
    local total="$2"
    local msg="$3"
    echo -e "${BLUE}⏳ [Step ${step_num}/${total}]${NC} ${msg}" | tee -a "$LOG_FILE"
}

log_ok() {
    echo -e "${GREEN}  ✅ $1${NC}" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}  ⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}  ❌ $1${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "  ℹ️  $1" | tee -a "$LOG_FILE"
}

TOTAL_STEPS=8

# =========================================================================
# Phase 1: OS レベルの前提条件チェック
# =========================================================================
echo "================================================================" | tee -a "$LOG_FILE"
echo "🚀 Ollama サーバー環境セットアップを開始します" | tee -a "$LOG_FILE"
echo "   実行日時: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "   ログ出力: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"

log_step 1 $TOTAL_STEPS "前提条件の確認（NVMe SSD / Tailscale / Docker）"

# NVMe SSD マウント確認
if mountpoint -q "$DATA_DIR" 2>/dev/null; then
    DISK_AVAIL=$(df -h "$DATA_DIR" | awk 'NR==2{print $4}')
    log_ok "/mnt/data マウント済み（空き容量: ${DISK_AVAIL}）"
else
    log_error "/mnt/data がマウントされていません。NVMe SSD を確認してください。"
    exit 1
fi

# Tailscale 接続確認
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")
if [ -z "$TAILSCALE_IP" ]; then
    log_warn "Tailscale IPが検出されませんでした。ローカルバインド（127.0.0.1）にフォールバックします。"
    TAILSCALE_IP="127.0.0.1"
else
    log_ok "Tailscale IP: ${TAILSCALE_IP}"
fi

# Docker デーモン確認
if docker info >/dev/null 2>&1; then
    log_ok "Docker デーモン稼働中"
else
    log_error "Docker デーモンが起動していません。'systemctl start docker' を実行してください。"
    exit 1
fi

# =========================================================================
# Phase 2: OS レベルのメモリ最適化
# =========================================================================
log_step 2 $TOTAL_STEPS "OS レベルのメモリ最適化（zRAM / swappiness / THP）"

# --- 2a. zRAM セットアップ ---
# 既存のzRAMデバイスがあるか確認
ZRAM_ACTIVE=false
if lsmod | grep -q zram 2>/dev/null; then
    ZRAM_ACTIVE=true
    log_info "zRAM カーネルモジュールは既にロード済み"
fi

if [ "$ZRAM_ACTIVE" = false ]; then
    # zRAM カーネルモジュールのロード
    if modprobe zram num_devices=1 2>/dev/null; then
        # 物理RAMの指定割合を計算
        TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        ZRAM_SIZE_KB=$((TOTAL_MEM_KB * ZRAM_SIZE_PERCENT / 100))
        ZRAM_SIZE_BYTES=$((ZRAM_SIZE_KB * 1024))

        # zRAMデバイスの設定
        echo "$ZRAM_ALGORITHM" > /sys/block/zram0/comp_algorithm 2>/dev/null || true
        echo "$ZRAM_SIZE_BYTES" > /sys/block/zram0/disksize 2>/dev/null || true
        mkswap /dev/zram0 >/dev/null 2>&1 || true
        swapon -p 100 /dev/zram0 2>/dev/null || true

        ZRAM_SIZE_MB=$((ZRAM_SIZE_KB / 1024))
        log_ok "zRAM 有効化完了（${ZRAM_SIZE_MB}MB, アルゴリズム: ${ZRAM_ALGORITHM}）"
    else
        log_warn "zRAM モジュールのロードに失敗しました（カーネルサポートが必要）"
    fi
else
    log_ok "zRAM は既にアクティブです"
fi

# --- 2b. swappiness の調整 ---
# LLM推論ではアクティブメモリの保持が重要なため、スワップアウトを控えめに設定
CURRENT_SWAPPINESS=$(cat /proc/sys/vm/swappiness)
TARGET_SWAPPINESS=10
if [ "$CURRENT_SWAPPINESS" -ne "$TARGET_SWAPPINESS" ]; then
    sysctl -w vm.swappiness=$TARGET_SWAPPINESS >/dev/null 2>&1
    log_ok "swappiness を ${CURRENT_SWAPPINESS} → ${TARGET_SWAPPINESS} に変更（スワップアウト抑制）"
else
    log_ok "swappiness は既に ${TARGET_SWAPPINESS} に設定済み"
fi

# --- 2c. Transparent Huge Pages (THP) の無効化 ---
# LLM推論のメモリアクセスパターンではTHPが逆効果になる場合があるため無効化
THP_PATH="/sys/kernel/mm/transparent_hugepage/enabled"
if [ -f "$THP_PATH" ]; then
    CURRENT_THP=$(cat "$THP_PATH" | grep -o '\[.*\]' | tr -d '[]')
    if [ "$CURRENT_THP" != "never" ]; then
        echo never > "$THP_PATH" 2>/dev/null || true
        log_ok "Transparent Huge Pages を無効化（LLM推論向け最適化）"
    else
        log_ok "Transparent Huge Pages は既に無効化済み"
    fi
fi

# =========================================================================
# Phase 3: ディレクトリ準備
# =========================================================================
log_step 3 $TOTAL_STEPS "データディレクトリの準備"

mkdir -p "$DATA_DIR/docker" "$DATA_DIR/ollama" "$DATA_DIR/open-webui" "$DATA_DIR/searxng"
chmod 777 "$DATA_DIR/ollama" "$DATA_DIR/open-webui" "$DATA_DIR/searxng"
log_ok "データディレクトリ準備完了 (${DATA_DIR})"

# =========================================================================
# Phase 4: Docker ネットワークとコンテナクリーンアップ
# =========================================================================
log_step 4 $TOTAL_STEPS "Docker ネットワーク作成と既存コンテナのクリーンアップ"

docker network create ollama-net 2>/dev/null || true
log_ok "Docker ブリッジネットワーク (ollama-net) 準備完了"

docker stop open-webui searxng ollama 2>/dev/null || true
docker rm open-webui searxng ollama 2>/dev/null || true
log_ok "既存コンテナのクリーンアップ完了"

# =========================================================================
# Phase 5: Ollama コンテナ起動（メモリ最適化環境変数付き）
# =========================================================================
log_step 5 $TOTAL_STEPS "Ollama コンテナ起動（KVキャッシュ量子化 + Flash Attention）"

docker run -d \
  --name ollama \
  --network ollama-net \
  --restart unless-stopped \
  -e OLLAMA_KV_CACHE_TYPE="${OLLAMA_KV_CACHE_TYPE}" \
  -e OLLAMA_FLASH_ATTENTION="${OLLAMA_FLASH_ATTENTION}" \
  -e OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL}" \
  -e OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS}" \
  -e OLLAMA_HOST="0.0.0.0" \
  -v "$DATA_DIR/ollama":/root/.ollama \
  -p 127.0.0.1:11434:11434 \
  ollama/ollama

log_ok "Ollama コンテナ起動完了"
log_info "  KV_CACHE_TYPE=${OLLAMA_KV_CACHE_TYPE} (キャッシュメモリ約50%削減)"
log_info "  FLASH_ATTENTION=${OLLAMA_FLASH_ATTENTION} (アテンション計算の効率化)"
log_info "  NUM_PARALLEL=${OLLAMA_NUM_PARALLEL} (並列リクエスト制限)"
log_info "  MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS} (同時ロードモデル数制限)"

# =========================================================================
# Phase 6: SearXNG コンテナ起動
# =========================================================================
log_step 6 $TOTAL_STEPS "SearXNG コンテナ起動（Web検索RAG用）"

docker run -d \
  --name searxng \
  --network ollama-net \
  --restart unless-stopped \
  -v "$DATA_DIR/searxng":/etc/searxng \
  searxng/searxng

log_ok "SearXNG コンテナ起動完了"

# =========================================================================
# Phase 7: Open WebUI コンテナ起動（セキュリティ制限適用済み）
# =========================================================================
log_step 7 $TOTAL_STEPS "Open WebUI コンテナ起動（Tailscaleバインド + セキュリティ制限）"

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
  -v "$DATA_DIR/open-webui":/app/backend/data \
  -p "${TAILSCALE_IP}:3000:8080" \
  ghcr.io/open-webui/open-webui:main

log_ok "Open WebUI コンテナ起動完了（新規登録は無効化済み）"

# =========================================================================
# Phase 8: Open WebUI バグパッチの一括適用
# =========================================================================
log_step 8 $TOTAL_STEPS "Open WebUI のバグパッチを一括適用中"

# コンテナのファイルシステムが利用可能になるまで待機
echo -n "  ⏳ コンテナ起動待機中..." | tee -a "$LOG_FILE"
for i in $(seq 1 10); do
    if docker exec open-webui test -f /app/backend/open_webui/main.py 2>/dev/null; then
        echo " OK" | tee -a "$LOG_FILE"
        break
    fi
    echo -n "." | tee -a "$LOG_FILE"
    sleep 1
done

# --- パッチ 8a: WebBaseLoader allow_redirects 重複バグ ---
PATCH_RESULT=$(docker exec open-webui sed -i '/allow_redirects=AIOHTTP_CLIENT_ALLOW_REDIRECTS,/d' /app/backend/open_webui/retrieval/web/utils.py 2>&1 && echo "OK" || echo "FAIL")
if [ "$PATCH_RESULT" = "OK" ]; then
    log_ok "パッチ適用: WebBaseLoader allow_redirects 重複バグ"
else
    log_warn "パッチ適用失敗: WebBaseLoader（既に適用済みの可能性あり）"
fi

# --- パッチ 8b: gemma2:2b Function Calling 無効化 ---
PATCH_FC=$(cat << 'PYEOF' | docker exec -i open-webui python 2>&1
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
    print("APPLIED")
elif replacement in content:
    print("ALREADY_PATCHED")
else:
    print("NOT_FOUND")
PYEOF
)
case "$PATCH_FC" in
    *APPLIED*)       log_ok "パッチ適用: gemma2:2b Function Calling 無効化" ;;
    *ALREADY*)       log_ok "パッチ確認: gemma2:2b FC無効化（適用済み）" ;;
    *)               log_warn "パッチ適用失敗: gemma2:2b FC無効化（${PATCH_FC}）" ;;
esac

# --- パッチ 8c: クエリ生成JSONパース修正 ---
PATCH_JSON=$(cat << 'PYEOF' | docker exec -i open-webui python 2>&1
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
    print("APPLIED")
elif replacement in content:
    print("ALREADY_PATCHED")
else:
    print("NOT_FOUND")
PYEOF
)
case "$PATCH_JSON" in
    *APPLIED*)       log_ok "パッチ適用: クエリ生成JSONパース修正" ;;
    *ALREADY*)       log_ok "パッチ確認: JSONパース修正（適用済み）" ;;
    *)               log_warn "パッチ適用失敗: JSONパース修正（${PATCH_JSON}）" ;;
esac

# --- パッチ 8d: API メタデータ NoneType エラー回避 ---
PATCH_META=$(cat << 'PYEOF' | docker exec -i open-webui python 2>&1
file_path = "/app/backend/open_webui/socket/main.py"
with open(file_path, "r") as f:
    content = f.read()

target_1 = """    # Channel mode: route pipeline output to channel message updates
    if request_info.get('chat_id', '').startswith('channel:'):"""
replacement_1 = """    # Channel mode: route pipeline output to channel message updates
    if (request_info.get('chat_id') or '').startswith('channel:'):"""

target_2 = """        if update_db and message_id and not request_info.get('chat_id', '').startswith('local:'):"""
replacement_2 = """        if update_db and message_id and not (request_info.get('chat_id') or '').startswith('local:'):"""

patched = False
if target_1 in content:
    content = content.replace(target_1, replacement_1)
    patched = True
if target_2 in content:
    content = content.replace(target_2, replacement_2)
    patched = True

if patched:
    with open(file_path, "w") as f:
        f.write(content)
    print("APPLIED")
elif replacement_1 in content and replacement_2 in content:
    print("ALREADY_PATCHED")
else:
    print("NOT_FOUND")
PYEOF
)
case "$PATCH_META" in
    *APPLIED*)       log_ok "パッチ適用: API メタデータ NoneType エラー回避" ;;
    *ALREADY*)       log_ok "パッチ確認: NoneType回避（適用済み）" ;;
    *)               log_warn "パッチ適用失敗: NoneType回避（${PATCH_META}）" ;;
esac

# パッチ適用後のコンテナ再起動
docker restart open-webui >/dev/null 2>&1
log_ok "Open WebUI をパッチ適用後に再起動しました"

# =========================================================================
# 完了サマリ
# =========================================================================
echo "" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
echo "🎉 Ollama サーバー環境セットアップが正常に完了しました！" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "📊 メモリ最適化設定サマリ:" | tee -a "$LOG_FILE"
echo "  ├── KVキャッシュ量子化 : ${OLLAMA_KV_CACHE_TYPE} (約50%メモリ削減)" | tee -a "$LOG_FILE"
echo "  ├── Flash Attention    : 有効" | tee -a "$LOG_FILE"
echo "  ├── 並列リクエスト     : ${OLLAMA_NUM_PARALLEL}" | tee -a "$LOG_FILE"
echo "  ├── 同時ロード数       : ${OLLAMA_MAX_LOADED_MODELS}" | tee -a "$LOG_FILE"
echo "  ├── swappiness         : ${TARGET_SWAPPINESS} (スワップアウト抑制)" | tee -a "$LOG_FILE"
echo "  └── zRAM               : ${ZRAM_SIZE_PERCENT}% of RAM (${ZRAM_ALGORITHM})" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "📌 アクセス先:" | tee -a "$LOG_FILE"
echo "  ├── Ollama API (ローカル) : http://127.0.0.1:11434" | tee -a "$LOG_FILE"
echo "  └── Open WebUI (VPN)     : http://${TAILSCALE_IP}:3000" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "📝 ログファイル: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
