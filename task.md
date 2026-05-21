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


