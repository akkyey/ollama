# タスク管理 (ollama)

Ollamaプロジェクトを `gemini-core` ガバナンス環境下で運用するためのタスク管理ボードです。

## 1. セットアップ・タスク
- [x] Task-01: `.gitignore` の作成と安全除外設定の配置 <!-- status: DONE -->
- [x] Task-02: `task.md` の新規作成と初期定義 <!-- status: DONE -->
- [x] Task-03: `gemini-brain-mcp` への `ollama` プロジェクトインデックス登録 <!-- status: DONE -->
- [x] Task-04: 未追跡ファイル群 of クリーンな初期 Git コミット (Initial Commit) <!-- status: DONE -->

## 2. 開発インフラ検証タスク
- [x] Task-05: `git status` による安全除外（無視）の正常性検証 <!-- status: DONE -->
- [x] Task-06: `sync_tasks` ツールによるタスク同期の結合テスト <!-- status: DONE -->
- [x] Task-07: `brain_get_sarag_status` によるインデックス状況の検証 <!-- status: DONE -->

## 3. リモートサーバー導入タスク
- [x] Task-08: Ollama & Open WebUI リモートサーバー構築（Docker + SSHトンネリング） <!-- status: DONE -->
  - [x] Task-08-01: 起動スクリプト `start-ollama-tailscale-stack.sh` の作成と配置 <!-- status: DONE -->
  - [x] Task-08-02: セキュリティ制限適用スクリプト `apply-security-restriction.sh` の作成と配置 <!-- status: DONE -->
  - [x] Task-08-03: クリーンアップ・初期化スクリプト `cleanup-ollama-stack.sh` の作成と配置 <!-- status: DONE -->
  - [x] Task-08-04: テストケース01：コンテナの正常起動とログ検証 <!-- status: DONE -->
  - [x] Task-08-05: テストケース02：ネットワークバインドの露出防止検証（ローカルホスト限定バインド） <!-- status: DONE -->
  - [x] Task-08-06: テストケース03：クライアント接続と対話の結合テスト（ブラウザからのTailscale疎通） <!-- status: DONE -->
  - [x] Task-08-07: テストケース04：Tailscale以外の物理NICポート遮断テスト <!-- status: DONE -->
  - [x] Task-08-08: テストケース05：VSCode SSH接続時の拡張機能（Continue等）からの直接疎通テスト <!-- status: DONE -->
  - [x] Task-08-09: クリーンアップ・初期化後の自動再起動の検証テスト <!-- status: DONE -->

## 4. RAGコンテキスト改善タスク
- [x] Task-09: Web Loaderのバイパス設定によるRAG品質の改善
  - [x] Task-09-01: 起動スクリプト `start-ollama-tailscale-stack.sh` への `BYPASS_WEB_SEARCH_WEB_LOADER=True` の追加
  - [x] Task-09-02: 制限適用スクリプト `apply-security-restriction.sh` への `BYPASS_WEB_SEARCH_WEB_LOADER=True` の追加
  - [x] Task-09-03: スクリプトの実行（コンテナの再構築）
  - [x] Task-09-04: 動作検証（静岡県沼津市の明日の天気の検索とLLM回答の確認）

## 5. 検索クエリ最適化タスク
- [x] Task-10: Web検索クエリ生成の有効化とクエリ自動変換の確認 <!-- status: DONE -->
  - [x] Task-10-01: 起動スクリプト `start-ollama-tailscale-stack.sh` への `ENABLE_SEARCH_QUERY_GENERATION=True` および `ENABLE_RETRIEVAL_QUERY_GENERATION=True` の追加
  - [x] Task-10-02: 制限適用スクリプト `apply-security-restriction.sh` への `ENABLE_SEARCH_QUERY_GENERATION=True` および `ENABLE_RETRIEVAL_QUERY_GENERATION=True` の追加
  - [x] Task-10-03: スクリプトの実行（コンテナの再構築）
  - [x] Task-10-04: クエリ生成JSONパースパッチの適用と Web Loader 有効化 (`BYPASS_WEB_SEARCH_WEB_LOADER=False`)
  - [x] Task-10-05: 動作検証（静岡県沼津市の明日の天気の検索とLLM回答の確認）



