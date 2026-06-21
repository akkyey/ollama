"""
Design Agent - ローカルLLM環境 (AMP) 特化型 自律開発エージェント

【概要】
ユーザーの要件定義からディレクトリ構成や仕様コメント入りファイルを自動生成し、
その後Aiderを自動で順次実行して実装まで一気通貫で完了させる開発支援スクリプトです。
Pythonに限らず、主要なテキスト形式のプログラミング言語に対応しています。

【使い方】
1. 一括フルオートモード (設計から実装まで自動実行)
   $ python design_agent.py requirements.md

2. 設計のみモード (フォルダと仕様コメント入りプレースホルダーの生成まで)
   $ python design_agent.py requirements.md --design-only

3. 実装のみモード (設計フェーズをスキップし、既存の未実装ファイルに対してAiderを実行)
   $ python design_agent.py --implement-only

4. レガシー設計モード (以前の XML API直叩き方式で設計を実行)
   $ python design_agent.py requirements.md --legacy-design
"""
import os
import re
import sys
import argparse
import subprocess
import json
import requests
from openai import OpenAI

# ============================================================
# セクション 1: 定数・設定・共通ユーティリティ
# ============================================================

# --- タイムアウト設定（環境変数でオーバーライド可能）---
_AIDER_TIMEOUT_SEC: int = int(os.environ.get("DESIGN_AGENT_AIDER_TIMEOUT", "3600"))
_DSL_TIMEOUT_SEC: int   = int(os.environ.get("DESIGN_AGENT_DSL_TIMEOUT",   "3600"))

# --- LLMサーバーエンドポイント（環境変数でオーバーライド可能）---
_LLAMA_SERVER_DESIGN_URL: str = os.environ.get(
    "DESIGN_AGENT_DESIGN_URL", "http://localhost:9090/v1"
)
_LLAMA_SERVER_IMPL_URL: str = os.environ.get(
    "DESIGN_AGENT_IMPL_URL", "http://localhost:9092/v1"
)

# --- DSL プロンプトファイルのパス（相対パスのみ・絶対パス禁止）---
_DSL_PROMPT_PATH: str = os.environ.get(
    "DESIGN_AGENT_DSL_PROMPT", "scripts/dsl_prompt.md"
)
_DSL_COMPILER_SCRIPT: str = "scripts/dsl_compiler.py"

# --- 未実装判定の閾値（マジックナンバー廃止）---
_UNIMPLEMENTED_THRESHOLD: int = 50

# --- パストラバーサル防止用 allowlist（生成対象の安全な拡張子）---
_SAFE_EXTENSIONS: frozenset = frozenset([
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs',
    '.html', '.css', '.c', '.cpp', '.h', '.hpp',
    '.java', '.kt', '.sh', '.yaml', '.yml', '.md',
])

# --- 除外するディレクトリ名（完全一致）---
_IGNORED_DIRS: frozenset = frozenset([
    '.git', '__pycache__', 'node_modules', '.aider', 'dist', 'build'
])

# --- DSL ウィジェットテンプレート（Q3: ロジックとデータを分離）---
# run_dsl_pipeline() によって src/widgets/dsl_widget.py として書き出される。
# ウィジェット仕様の変更はこの定数のみを編集すること。
_DSL_WIDGET_TEMPLATE: str = """\
from textual.widgets import Static
from typing import Any, List, Dict

class DSLWidget(Static):
    def __init__(self, service: Any, method_name: str, fmt_str: str, **kwargs):
        super().__init__(**kwargs)
        self.service = service
        self.method_name = method_name
        self.fmt_str = fmt_str

    def update_widget(self) -> None:
        method = getattr(self.service, self.method_name)
        val = method()
        formatted_text = self._format_data(val)
        self.update(formatted_text)

    def _format_data(self, val: Any) -> str:
        if val is None:
            return "No Data"
        if self.method_name == "get_disk_info":
            lines = []
            for d in val:
                lines.append(
                    f"{d['mountpoint']:<10} {d['percent']:>5.1f}% "
                    f"({self._to_gb(d['used'])}/{self._to_gb(d['total'])} GB)"
                )
            return "\\n".join(lines) if lines else "No Disk Info"
        elif self.method_name == "get_current_speeds":
            lines = []
            for nic, speeds in val.items():
                if nic.startswith("lo"):
                    continue
                up_kb   = speeds['bytes_sent'] / 1024.0
                down_kb = speeds['bytes_recv'] / 1024.0
                lines.append(f"{nic:<8} Up: {up_kb:>6.1f} KB/s | Down: {down_kb:>6.1f} KB/s")
            return "\\n".join(lines) if lines else "No Net Activity"
        elif self.method_name == "get_processes":
            lines = [f"{'PID':<6} {'NAME':<15} {'CPU':>5} {'MEM':>5}"]
            lines.append("-" * 35)
            for p in val[:10]:
                lines.append(
                    f"{p['pid']:<6} {p['name'][:15]:<15} "
                    f"{p['cpu_percent']:>5.1f}% {p['memory_percent']:>5.1f}%"
                )
            return "\\n".join(lines)
        try:
            return self.fmt_str.format(val)
        except Exception:
            return str(val)

    def _to_gb(self, num_bytes: int) -> float:
        return round(num_bytes / (1024 ** 3), 1)
"""


def _validate_path(path: str, base_dir: str) -> str:
    """
    LLM応答などの外部入力から受け取ったパスを検証し、安全な絶対パスを返す。
    - abspath で正規化しディレクトリトラバーサルを無効化
    - base_dir 配下に収まるか確認
    - _SAFE_EXTENSIONS に含まれる拡張子のみ許可
    違反時は ValueError を送出する。
    """
    abs_path = os.path.abspath(path)
    abs_base = os.path.abspath(base_dir)
    # base_dir 配下に収まるか確認
    if not abs_path.startswith(abs_base + os.sep) and abs_path != abs_base:
        raise ValueError(
            f"パストラバーサルを検出しました: '{path}' は '{base_dir}' の外部を指しています。"
        )
    # 拡張子が allowlist に含まれるか確認（拡張子なしのファイルは許可）
    ext = os.path.splitext(abs_path)[1].lower()
    if ext and ext not in _SAFE_EXTENSIONS:
        raise ValueError(
            f"許可されていない拡張子です: '{ext}' (path='{path}')"
        )
    return abs_path


def _get_aider_env() -> dict:
    """Aider 実行用の環境変数セットを一元管理して返す。"""
    env = os.environ.copy()
    env["OPENAI_API_BASE"] = _LLAMA_SERVER_IMPL_URL
    env["AIDER_TIMEOUT"]   = str(_AIDER_TIMEOUT_SEC)
    env["LITELLM_TIMEOUT"] = str(_AIDER_TIMEOUT_SEC)
    return env


def _graceful_terminate(process, timeout: int = _AIDER_TIMEOUT_SEC) -> None:
    """
    subprocess.Popen プロセスをタイムアウト付きで安全に終了させる。
    - wait(timeout) でタイムアウトを待つ
    - TimeoutExpired 発生時: terminate() -> wait(5s) -> kill() の順で強制終了
    """
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"\n⚠️ タイムアウト ({timeout}s) — プロセスを終了します...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("🛑 プロセスを強制終了しました。")


# ============================================================
# セクション 4: DSL パイプライン
# ============================================================

def run_dsl_pipeline(requirement_file):
    """
    要件定義ファイルからDSLをLLMで自動翻訳し、トランスパイラを実行して
    app.py と dsl_widget.py を自動生成する。
    """
    print("\n🔮 [DSL Pipeline] 自然言語要件からDSLへの翻訳を開始します...")

    # 定数を参照（A1 対応: ハードコード絶対パスの完全禁止）
    prompt_path     = _DSL_PROMPT_PATH
    compiler_script = _DSL_COMPILER_SCRIPT

    if not os.path.exists(prompt_path):
        print(f"❌ DSLプロンプトガイドが見つかりません: {prompt_path}")
        print("   環境変数 DESIGN_AGENT_DSL_PROMPT でパスを指定できます。")
        return False

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    with open(requirement_file, "r", encoding="utf-8") as f:
        user_prompt = f.read()

    data = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        "temperature": 0.1,
        "stream": False
    }

    url     = f"{_LLAMA_SERVER_DESIGN_URL}/chat/completions"
    headers = {'Content-Type': 'application/json'}

    try:
        print(f"[INFO] llama-server ({_LLAMA_SERVER_DESIGN_URL}) へ要件を送信中...")
        # B1 対応: `if True:` を削除し直接実行
        resp = requests.post(url, json=data, headers=headers, timeout=_DSL_TIMEOUT_SEC)
        resp.raise_for_status()
        res_json = resp.json()
        content  = res_json['choices'][0]['message']['content']

        dsl_match = re.search(r'```dsl\n(.*?)\n```', content, re.DOTALL)
        if dsl_match:
            dsl_content = dsl_match.group(1)
            dsl_path    = "app.dsl"
            with open(dsl_path, "w", encoding="utf-8") as tf:
                tf.write(dsl_content)
            print(f"✅ DSLファイルを生成しました: {dsl_path}")

            print("⚙️ DSLコンパイラを起動します...")
            os.makedirs("src/widgets", exist_ok=True)

            # Q3 対応: ヒアドキュメントの代わりにモジュールレベル定数を参照
            with open("src/widgets/dsl_widget.py", "w", encoding="utf-8") as wf:
                wf.write(_DSL_WIDGET_TEMPLATE)
            print("✅ dsl_widget.py を作成しました。")

            cmd = [sys.executable, compiler_script, dsl_path, "src/app.py"]
            subprocess.run(cmd, check=True)
            print("✅ app.py を自動コンパイルしました。")
            return True
        else:
            print("⚠️ 警告: 応答から ```dsl ... ``` を抽出できませんでした。")
            return False
    except Exception as e:
        print(f"❌ DSLパイプライン実行中にエラーが発生しました: {e}")
        return False


# ============================================================
# セクション 2: ファイルユーティリティ
# ============================================================

def is_unimplemented_file(file_path):
    """
    ファイルが未実装（プレースホルダー状態）であるか汎用的に判定する。
    コメントおよびインポート文等の参照宣言を除去した後の実体コード文字数が極めて短い場合を未実装とみなす。
    Python, JS, TS, Go, Rust, HTML, CSS 等の多言語に対応。
    """
    # __init__.py は常に除外
    if file_path.endswith('__init__.py'):
        return False

    # D2 対応: パス構成要素の完全一致で除外判定（部分文字列マッチの誤検知を防止）
    path_parts = set(os.path.normpath(file_path).split(os.sep))
    if path_parts & _IGNORED_DIRS:
        return False

    # バイナリ拡張子の除外
    binary_extensions = frozenset([
        '.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf',
        '.zip', '.tar', '.gz', '.db', '.sqlite'
    ])
    if any(file_path.endswith(ext) for ext in binary_extensions):
        return False

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read().strip()

        # 1. 複数行コメントの除去
        # Python/Ruby Docstring: """...""" または '''...'''
        content = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
        content = re.sub(r"'''.*?'''", '', content, flags=re.DOTALL)
        # JS/TS/Go/Rust/CSS/C/C++: /*...*/
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # HTML/XML: <!--...-->
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

        # 2. 単一行コメントの除去
        content = re.sub(r'//.*', '', content)   # JS/TS/Go/Rust/C/C++
        content = re.sub(r'#.*',  '', content)   # Python/Ruby/Shell/YAML

        # 3. インポート文・参照宣言の除去
        content = re.sub(
            r'^\s*(import|from|use|mod|#include)\s+.*$', '', content, flags=re.MULTILINE
        )
        # Go: import (...) の複数行ブロック
        content = re.sub(r'import\s*\((.*?)\)', '', content, flags=re.DOTALL)

        clean_content = content.strip()
        # D1 対応: マジックナンバーを定数参照に置き換え
        return len(clean_content) < _UNIMPLEMENTED_THRESHOLD
    except Exception:
        return False

def get_unimplemented_files(root_dir="src"):
    """ディレクトリ配下の未実装ソースファイルを再帰的に検索する（多言語対応）。"""
    unimplemented = []
    if not os.path.exists(root_dir):
        return unimplemented

    # 対象とするソースファイルの拡張子リスト
    target_extensions = frozenset([
        '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs',
        '.html', '.css', '.c', '.cpp', '.h', '.hpp',
        '.java', '.kt', '.sh', '.yaml', '.yml'
    ])

    for root, dirs, files in os.walk(root_dir):
        # D2 対応: dirs のインプレース代入で除外ディレクトリへの降下を事前カット（完全一致）
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in target_extensions:
                file_path = os.path.join(root, file)
                if is_unimplemented_file(file_path):
                    unimplemented.append(file_path)
    return unimplemented

def guess_class_name(file_path):
    """ファイル名からクラス名を推測する（スネークケース -> キャメルケース）"""
    basename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(basename)[0]
    if name_without_ext in ['main', 'app']:
        return None
    return "".join(word.capitalize() for word in name_without_ext.split("_"))

def _get_layer(path: str) -> int:
    """
    ファイルパスからレイヤー階層を判定する（1: 最上位〜4: その他）。
    inject_imports_to_placeholder() および main() 内ソート処理の共通ロジック（B3 対応）。
    """
    p = path.replace("\\", "/").lower()
    if "main" in p or "app" in p:
        return 1
    elif "widgets/" in p or "components/" in p:
        return 2
    elif "services/" in p or "helpers/" in p or "utils/" in p:
        return 3
    return 4


def generate_import_statement(target_file, dep_file):
    """対象ファイルから依存ファイルへの参照/インポート文を言語別・規約別で自動生成する"""
    ext = os.path.splitext(target_file)[1].lower()
    dep_ext = os.path.splitext(dep_file)[1].lower()

    # 拡張子が異なる、または同一ファイルの場合はインポート不要
    if ext != dep_ext or target_file == dep_file:
        return None

    class_name = guess_class_name(dep_file)
    if not class_name:
        return None

    target_dir = os.path.dirname(target_file)
    rel_dep_path = os.path.relpath(dep_file, target_dir).replace("\\", "/")

    if ext == '.py':
        # Python: from src.widgets.cpu_widget import CpuWidget
        # パスをドット区切りのモジュールパスに変換
        module_path = os.path.splitext(dep_file)[0].replace("\\", "/").replace("/", ".")
        return f"from {module_path} import {class_name}"

    elif ext in ['.ts', '.tsx', '.js', '.jsx']:
        # TypeScript/JavaScript: import { CpuWidget } from './widgets/cpu_widget';
        if not rel_dep_path.startswith('.'):
            rel_dep_path = "./" + rel_dep_path
        rel_dep_path_no_ext = os.path.splitext(rel_dep_path)[0]
        return f"import {{ {class_name} }} from '{rel_dep_path_no_ext}';"

    elif ext == '.rs':
        # Rust: use crate::widgets::cpu_widget::CpuWidget;
        parts = os.path.splitext(dep_file)[0].replace("\\", "/").split('/')
        if parts and parts[0] == 'src':
            parts[0] = 'crate'
        module_path = "::".join(parts)
        return f"use {module_path}::{class_name};"

    elif ext == '.go':
        # Go: import "project/widgets"
        dep_dir = os.path.dirname(dep_file).replace("\\", "/")
        return f'import "{dep_dir}"'

    return None


def inject_imports_to_placeholder(target_file, all_files):
    """
    プレースホルダーファイルに、他のファイルに対するインポート文を自動で挿入する。
    上位レイヤー（main/app等）には中位・下位（widgets, services等）を、
    中位レイヤー（widgets等）には下位（services等）をインポートする。
    """
    if not os.path.exists(target_file):
        return

    ext = os.path.splitext(target_file)[1].lower()
    if ext not in ['.py', '.ts', '.tsx', '.js', '.jsx', '.rs', '.go']:
        return

    # B3 対応: 内部定義を廃止し、モジュールレベルの _get_layer() を呼び出す
    target_layer = _get_layer(target_file)
    imports_to_add = []
    added_statements = set()

    for dep_file in all_files:
        dep_layer = _get_layer(dep_file)
        # 自分より下位のレイヤーのみをインポート対象とする
        if dep_layer > target_layer:
            stmt = generate_import_statement(target_file, dep_file)
            if stmt and stmt not in added_statements:
                imports_to_add.append(stmt)
                added_statements.add(stmt)

    if not imports_to_add:
        return

    # ファイルの読み込み
    with open(target_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # 重複注入防止
    lines_to_inject = []
    for stmt in imports_to_add:
        if stmt not in content:
            lines_to_inject.append(stmt)

    if not lines_to_inject:
        return

    # C3 対応: シェバン行・エンコーディング宣言行を検出し、その後にインポートを挿入する
    all_lines = content.splitlines(keepends=True)
    protected_lines = []
    rest_start = 0
    for i, line in enumerate(all_lines):
        if line.startswith("#!") or line.startswith("# -*- coding"):
            protected_lines.append(line)
            rest_start = i + 1
        else:
            break

    header       = "".join(protected_lines)
    body         = "".join(all_lines[rest_start:])
    inject_block = "\n".join(lines_to_inject) + "\n\n"
    new_content  = header + inject_block + body

    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"🔌 {os.path.basename(target_file)} に依存モジュールの参照を自動注入しました: {[stmt.split()[-1] for stmt in lines_to_inject]}")


# ============================================================
# セクション 5: Aider 実行・メインフロー
# ============================================================


def run_aider_on_file(file_path, use_map=False):
    """特定のファイルに対してAiderを起動し、仕様コメントと設計書に基づいて自動実装を行う。"""
    print(f"\n🚀 Aiderによる実装を開始します: {file_path}")
    # C1 対応: 環境変数を _get_aider_env() で一元管理
    env = _get_aider_env()

    cmd = [
        "aider",
        "--yes",
        "--edit-format", "diff",
        "--model", "openai/local-model"
    ]
    if not use_map:
        cmd += ["--map-tokens", "0"]

    # 全体設計書 (tasks.md) が存在する場合は読み取り専用としてアタッチする
    if os.path.exists("tasks.md"):
        cmd += ["--read", "tasks.md"]

    cmd += [
        file_path,
        "-m", "ファイル内の仕様コメント（Docstringやブロックコメント）およびプロジェクト全体設計書（tasks.md）をよく読み、その仕様に従って残りの実装コードを具体的に記述してください。他のファイルに分割して実装する予定のクラスやモジュールは、tasks.mdの記述に従って正しくインポート（import）して使用し、このファイル内に直接定義を記述しないでください。"
    ]

    try:
        # 出力をリアルタイム表示しながら非同期でPopen実行
        process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in process.stdout:
            print(line, end="")
        # C1 対応: タイムアウト付きグレースフルシャットダウン
        _graceful_terminate(process, timeout=_AIDER_TIMEOUT_SEC)
        return process.returncode == 0
    except Exception as e:
        print(f"❌ Aiderの実行に失敗しました: {e}")
        return False


def run_final_check(files, use_map=False):
    """全ファイルをアタッチして、全体整合性チェックを実行する（コンテキスト肥大化防止のフィルタ付き）。"""
    if not files:
        return

    # 整合性チェックにアタッチするファイルの選別（コンテキスト節約のため末端UIウィジェット等は除外）
    critical_files = [
        f for f in files
        if any(kw in f.replace("\\", "/").lower() for kw in ("main.py", "app.py", "services/"))
    ]
    files_to_attach = critical_files if critical_files else files

    print(f"\n🔍 全体の整合性チェックを実行します (アタッチ対象: {[os.path.basename(f) for f in files_to_attach]})...")
    # C1 対応: 環境変数を _get_aider_env() で一元管理
    env = _get_aider_env()

    cmd = [
        "aider",
        "--yes",
        "--edit-format", "diff",
        "--model", "openai/local-model"
    ]
    if not use_map:
        cmd += ["--map-tokens", "0"]
    cmd += files_to_attach + [
        "-m", "実装された各ソースファイル間のインターフェース、型定義、関数呼び出し、データ連携に不整合がないか確認し、ズレやバグがあれば微修正してください。"
    ]

    try:
        process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in process.stdout:
            print(line, end="")
        # C1 対応: タイムアウト付きグレースフルシャットダウン
        _graceful_terminate(process, timeout=_AIDER_TIMEOUT_SEC)
        print("\n✅ 全体整合性チェックが完了しました！")
    except Exception as e:
        print(f"❌ 全体整合性チェックの実行に失敗しました: {e}")


def main():
    parser = argparse.ArgumentParser(description='Design Agent - ローカルLLM環境 (AMP) 特化型 自律開発エージェント')
    parser.add_argument('requirement_file', nargs='?', help='要件定義ファイル (例: requirements.md)')
    parser.add_argument('--design-only', action='store_true', help='設計フェーズ（フォルダとプレースホルダー生成）のみを実行')
    parser.add_argument('--implement-only', action='store_true', help='実装フェーズ（Aiderによる順次自動実装）のみを実行')
    parser.add_argument('--legacy-design', action='store_true', help='OpenAI API直叩きによるXML出力方式（レガシー）で設計を実行')
    parser.add_argument('--use-map', action='store_true', help='Aider実行時にリポジトリマップ(repo-map)を有効にする (ローカルLLM環境でのコンテキスト肥大化に注意)')
    parser.add_argument('--use-dsl', action='store_true', help='TUIアプリのUIと結合にDSL翻訳・コンパイルパイプラインを使用する')
    args = parser.parse_args()

    # モード判定とバリデーション
    if not args.implement_only and not args.requirement_file:
        parser.print_help()
        print("\n❌ エラー: 設計を行うには要件定義ファイルが必要です。")
        sys.exit(1)

    # C2 対応: --implement-only 模山時に Aider 設定ファイルの存在を事前確認
    if args.implement_only and not os.path.exists(".aider.conf.yml"):
        print("⚠️ .aider.conf.yml が見つかりません。--design-only を先に実行することを推奨します。")
        print("   Aider はデフォルト設定で動作します。")

    # 1. 設計フェーズ (フォルダとプレースホルダー生成)
    if not args.implement_only:
        file_path = args.requirement_file
        if not os.path.exists(file_path):
            print(f"❌ エラー: ファイル '{file_path}' が見つかりません。")
            sys.exit(1)

        # Aiderの最適設定ファイルの自動生成 (先に作成しておくことでAider設計時にも反映される)
        print("\n⚙️ Aiderの最適設定ファイル（.aider.conf.yml / CONVENTIONS.md）を自動生成しています...")
        aider_conf_content = """model: openai/local-model
auto-commits: false
auto-lint: false
yes-always: true
edit-format: diff
read:
  - CONVENTIONS.md
"""
        conventions_content = """# AI Coding Guidelines

You are running as a local AI model with constrained context size. 
To ensure maximum stability and speed, you MUST adhere to the following rules:

1. DIFF FORMAT: You are operating in `edit-format: diff` mode. Use search/replace blocks for editing.
2. CONTEXT MINIMIZATION: Focus only on the requested files. Keep the edits local and minimal.
"""
        with open('.aider.conf.yml', 'w', encoding='utf-8') as f:
            f.write(aider_conf_content)
        with open('CONVENTIONS.md', 'w', encoding='utf-8') as f:
            f.write(conventions_content)
        print("✅ Aiderの設定ファイルを生成しました！")

        # Gitの初期化 (AiderにはGitリポジトリが必須)
        print("\n📦 Gitリポジトリを初期化しています...")
        try:
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(["git", "add", ".aider.conf.yml", "CONVENTIONS.md"], check=True, capture_output=True)
            if os.path.exists(file_path) and not os.path.isabs(file_path):
                subprocess.run(["git", "add", file_path], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial configuration files by Design Agent"], check=True, capture_output=True)
            print("✅ Gitの初期化と初回コミットが完了しました！")
        except Exception as e:
            print(f"⚠️ Gitの初期化中に警告が発生しました (既存リポジトリ等の可能性あり): {e}")

        # DSLパイプラインの実行 (TUIアプリ of UI自動ビルド)
        if args.use_dsl:
            success = run_dsl_pipeline(file_path)
            if not success:
                print("❌ DSLパイプラインの実行に失敗したため、処理を中断します。")
                sys.exit(1)

        # レガシー設計モード（API直叩き＋XMLパース）
        if args.legacy_design:
            print("\n🤖 [Legacy] XML API直接呼び出しによる設計を開始します...")
            with open(file_path, 'r', encoding='utf-8') as f:
                user_prompt = f.read()

            client = OpenAI(base_url="http://localhost:9090/v1", api_key="dummy", timeout=None)
            
            # システムプロンプト（多言語対応仕様にアップデート）
            system_prompt = """
あなたは世界最高峰のソフトウェアアーキテクトです。
ユーザーの要件（要求定義）を厳密に分析し、プロジェクトに必要なディレクトリ構成と、実装の雛形となる「仕様コメント入りファイル群」およびタスクリストを作成してください。

【出力形式に関する絶対ルール】
1. 出力はすべて以下の指定されたXMLタグ（ <mkdir>, <file> ）のみで構成してください。
2. タグの外側には、説明、雑談、挨拶などの余計なテキストを一切出力しないでください。マークダウンの ```xml 等で囲む必要もありません。
3. すべてのパスは、プロジェクトルートからの相対パスで記述してください。

【ファイル内容に関する絶対ルール】
1. **実装コードの禁止**: ソースファイルの中に、具体的な実装コード（変数・定数の定義、中身が空のクラス定義 `class X: pass`、関数のスタブ `def x(): pass` など）は絶対に記述しないでください。
2. **インポート（import）文の記述（推奨）**: ただし、他の自作モジュールや外部ライブラリに依存することが明白な場合は、**ファイルの先頭（仕様コメントの外側）に必要な `import` 文（例: `from src.widgets.cpu_widget import CpuWidget`）だけは明記して構いません。** これにより、モジュール間の依存関係を明確に定義してください。
3. **要件コメントの義務化**: すべての新規ソースファイルには、必ずその言語に適したコメント形式で、後続の実装エージェント（Aider）が迷わず実装できる極めて詳細な「機能仕様コメント」を日本語で記述してください。
3. **言語ごとのコメント形式**:
   - Python: \"\"\"（トリプルダブルクォート）のマルチライン文字列形式
   - JavaScript / TypeScript / Go / Rust / C++ / Java / CSS: /* ... */（ブロックコメント）形式
   - HTML / XML: <!-- ... --> 形式
   - Shell / YAML / Configuration: すべての行を # で始める単一行コメント形式

【要件コメント（仕様コメント）に記述すべき内容】
各ファイルのコメントには、以下の項目を網羅して詳細に記述してください。
- **機能概要**: このモジュールが担当する責務・機能。
- **外部依存関係**: インポートして使用すべきライブラリ（例: `psutil`, `asyncio`）や、プロジェクト内の他の依存ファイル（例: `src/services/psutil_wrapper.py`）。
- **インターフェース設計**: 
  - 定義すべきクラス名や関数名。
  - 各メソッド/関数の名前、受け取る引数の名前と型、戻り値の型。
  - 非同期処理（`async/await`）が必要かどうかの明示。
- **フレームワーク規約と制約**: 使用するフレームワーク（例: Textual, React等）に固有の命名規則、非同期化ルール、ライフサイクルの注意点などを、簡潔な箇条書きで必ず記述してください（実装完了後に削除できるよう、明示的に分けて記述すること）。
- **データ構造とアルゴリズム**: 内部で保持すべきデータの形式（型）や、履歴バッファなどのアルゴリズム要件。
- **エラー処理方針**: 想定される例外とそのハンドリング。

【XMLタグ仕様】
1. フォルダを作成する場合:
<mkdir>フォルダの相対パス</mkdir>

2. ファイルを作成する場合（中身も記述可能）:
<file path="ファイルの相対パス">
ファイルの要件コメント（先頭のコメント）または設計書ドキュメントの中身
</file>

【出力例】
<mkdir>src/services</mkdir>
<file path="src/services/cpu_service.py">
\"\"\"
【機能概要】
CPU使用率（全体・コア別）およびCPU周波数を監視・保持する非同期サービス。

【依存関係】
- 依存モジュール: `src/services/psutil_wrapper.py`
- 使用ライブラリ: `typing.List`, `typing.Optional`, `typing.Any`

【クラス・関数設計】
- クラス名: `CpuService`
- 初期化 (`__init__(self, history_size: int = 60)`):
  - 引数: `history_size` (履歴バッファのサイズ、デフォルト60)
  - メンバ変数: 
    - `_cpu_percent_total`: 全体CPU使用率 (float)
    - `_cpu_percents_per_core`: コア別使用率のリスト (List[float])
    - `_cpu_history`: 全体使用率の履歴バッファ (List[float])
    - `_cpu_freq`: CPU周波数情報 (Optional[Any])
- 更新処理 (`async def update(self)`):
  - 非同期で `PsutilWrapper.cpu_percent` および `PsutilWrapper.cpu_freq` を呼び出し、メンバ変数を更新。全体使用率は `_cpu_history` に追加し、`history_size` を超えた場合は古いデータを削除する。
- ゲッターメソッド:
  - `def get_cpu_percent(self) -> float`
  - `def get_cpu_percents(self) -> List[float]`
  - `def get_cpu_history(self) -> List[float]`
  - `def get_cpu_freq(self) -> Optional[Any]`
\"\"\"
</file>
<mkdir>src/components</mkdir>
<file path="src/components/CpuPanel.jsx">
/*
【機能概要】
CPU使用率履歴を元に折れ線グラフ（Sparkline）とコア別バーを描画するReactコンポーネント。

【インターフェース設計】
- コンポーネント名: `CpuPanel`
- Props:
  - `cpuData`: CPU使用率の履歴データオブジェクト。全体平均、コア別リスト、周波数を保持していること。
- メソッド/内部処理:
  - CanvasまたはSVGを用いてSparklineを滑らかに描画する関数 `drawSparkline(ctx, data)` を定義。
*/
</file>
<file path="tasks.md">
# タスクリスト
- [ ] CPUサービスの実装
- [ ] CpuPanelコンポーネントの実装
...
</file>
"""

            print("🤖 設計エージェントが思考中です... (この処理には数分かかる場合があります)")
            
            try:
                response = client.chat.completions.create(
                    model="local-model",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    stream=True, 
                )
            except Exception as e:
                print(f"❌ llama-serverとの通信に失敗しました: {e}")
                sys.exit(1)
                
            print("\n================== AIの応答 ==================")
            ai_response = ""
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end="", flush=True)
                    ai_response += content
            print("\n==============================================\n")
            
            print("🚀 プロジェクトの構築を開始します...")
            base_dir = os.getcwd()

            # 1. mkdir の処理
            for dir_path in re.findall(r"<mkdir>(.*?)</mkdir>", ai_response, re.DOTALL):
                dir_path = dir_path.strip()
                try:
                    # A2 対応: LLM応答のパスを必ず _validate_path で検証する
                    safe_dir = _validate_path(dir_path, base_dir)
                    os.makedirs(safe_dir, exist_ok=True)
                    print(f"📁 フォルダを作成しました: {dir_path}")
                except ValueError as e:
                    print(f"⚠️ 不正なパスをスキップしました: {e}")
                    continue

                
            # 2. file の処理の前にファイルリストを収集
            files_to_create_legacy = []
            for match in re.finditer(r'<file\s+path="(.*?)">', ai_response, re.DOTALL):
                raw_path = match.group(1).strip()
                try:
                    safe_path = _validate_path(raw_path, base_dir)
                    files_to_create_legacy.append(safe_path)
                except ValueError as e:
                    print(f"⚠️ ファイルリスト分析中に不正なパスをスキップ: {e}")

            # 2. file の処理
            for match in re.finditer(r'<file\s+path="(.*?)">(.*?)</file>', ai_response, re.DOTALL):
                f_path = match.group(1).strip()
                file_content = match.group(2).strip()
                # A2 対応: _validate_path で検証した安全なパスのみを使用
                try:
                    safe_f_path = _validate_path(f_path, base_dir)
                except ValueError as e:
                    print(f"⚠️ 不正なパスをスキップしました: {e}")
                    continue

                # 親ディレクトリが存在しない場合は作成
                dir_name = os.path.dirname(safe_f_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                with open(safe_f_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                print(f"📄 仕様ファイルを作成しました: {f_path}")

                # インポート文の自動インジェクション
                inject_imports_to_placeholder(safe_f_path, files_to_create_legacy)

        
        else:
            # Aider設計モード（Aiderによる順次自動設計）
            print("\n🤖 Aiderによる自動設計フェーズを開始します...")
            # C1 対応: 環境変数を _get_aider_env() で一元管理
            env = _get_aider_env()

            # ステップ1: tasks.md の自動生成
            print("📝 Aiderを起動して 'tasks.md' (設計書・ファイルリスト) を作成しています...")
            cmd = [
                "aider",
                "--yes",
                "--edit-format", "diff",
                "--model", "openai/local-model",
                file_path,
                "-m", f"要件定義書（{file_path}）を元に、プロジェクトに必要なディレクトリ構成を決定し、作成すべきソースファイル（例: src/services/cpu_service.py）の相対パスのリストを、マークダウンのチェックリスト形式（- [ ] ファイル名）で 'tasks.md' に記述して新規作成してください。実際のソースフォルダやソースファイルの作成はここでは行わず、tasks.mdの作成のみを行ってください。"
            ]
            try:
                process = subprocess.Popen(
                    cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace'
                )
                for line in process.stdout:
                    print(line, end="")
                # C1 対応: タイムアウト付きグレースフルシャットダウン
                _graceful_terminate(process, timeout=_AIDER_TIMEOUT_SEC)
                if process.returncode != 0:
                    print("❌ Aiderによる tasks.md の生成に失敗しました。")
                    sys.exit(1)
            except Exception as e:
                print(f"❌ Aiderの実行に失敗しました: {e}")
                sys.exit(1)

            # ステップ2: tasks.md から新規ファイルパスを抽出
            print("\n🔍 'tasks.md' から作成対象のソースファイルを抽出しています...")
            files_to_create = []
            if os.path.exists("tasks.md"):
                with open("tasks.md", "r", encoding="utf-8") as f:
                    content = f.read()
                matches = re.findall(r'-\s+\[\s*\]\s*`?([^`\s\n\r]+)`?', content)
                ignored_files = ['tasks.md', 'requirements.txt', 'CONVENTIONS.md', '.aider.conf.yml', '.gitignore']
                for m in matches:
                    path = m.strip().strip('`').strip('"').strip("'")
                    # mdファイルや自動生成済みの共通設定ファイルを除き、チェックリストにあるファイルを抽出
                    if path and not path.endswith('.md') and path not in ignored_files:
                        files_to_create.append(path)
            
            if not files_to_create:
                print("⚠️ 作成対象のソースファイルが検出されませんでした。")
            else:
                print(f"📂 以下のファイルを作成します: {files_to_create}")
                
                # ステップ3: 各ファイルを順次プレースホルダー化
                for target_file in files_to_create:
                    # すでに実体コードが記述されている（実装済み）ファイルは、上書き防止のためにスキップ
                    if os.path.exists(target_file) and not is_unimplemented_file(target_file):
                        print(f"⏭️ {target_file} はすでに実装されているため、プレースホルダー生成をスキップします。")
                        continue

                    print(f"\n🚀 {target_file} の設計コメント（プレースホルダー）を生成中...")
                    
                    # 親フォルダを事前に作成
                    dir_name = os.path.dirname(target_file)
                    if dir_name:
                        os.makedirs(dir_name, exist_ok=True)

                    # Aiderを起動してプレースホルダーを作成
                    cmd = [
                        "aider",
                        "--yes",
                        "--edit-format", "diff",
                        "--model", "openai/local-model",
                        target_file,
                        file_path,
                        "tasks.md",
                        "-m", f"要件定義（{file_path}）と設計書（tasks.md）を参考に、対象ファイル {target_file} を新規作成し、その言語に合わせたコメント形式（Pythonならトリプルクォート、JSなら/* */）で、詳細な機能仕様・依存関係・インターフェース設計（クラス名、メソッド名、引数や戻り値の型）・フレームワーク特有の規約や制約（命名規則、非同期ライフサイクル等）・エラー処理方針を日本語で記述（プレースホルダー化）してください。具体的な実装コード（空のクラスや関数のスタブも含む）は絶対に記述せず、コメントのみのファイルを生成してください。"
                    ]
                    try:
                        process = subprocess.Popen(
                            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace'
                        )
                        for line in process.stdout:
                            print(line, end="")
                        # C1 対応: タイムアウト付きグレースフルシャットダウン
                        _graceful_terminate(process, timeout=_AIDER_TIMEOUT_SEC)
                        if process.returncode == 0:
                            # プレースホルダーの生成が成功した場合にインポート自動インジェクション
                            inject_imports_to_placeholder(target_file, files_to_create)
                        else:
                            print(f"⚠️ {target_file} のプレースホルダー生成中にエラーが発生しましたが、続行します。")
                    except Exception as e:
                        print(f"❌ Aiderの実行に失敗しました: {e}")

    # 2. 実装フェーズ (Aiderによる順次自動実装)
    if not args.design_only:
        print("\n🛠️ 自動実装フェーズを開始します...")
        # 未実装ファイルを検索
        unimplemented_files = get_unimplemented_files("src")
        
        if args.use_dsl:
            # DSLパイプライン使用時は、個別のウィジェット実装をスキップ（dsl_widget.py がすべて賄うため）
            unimplemented_files = [f for f in unimplemented_files if not ("widgets/" in f.replace("\\", "/") and "dsl_widget.py" not in f)]
        
        if not unimplemented_files:
            print("✅ 未実装のソースファイルは見つかりませんでした。（すべて実装済みです）")
            sys.exit(0)
            
        # B3 対応: get_priority 内部関数を廃止し、モジュールレベルの _get_layer() でソート
        unimplemented_files = sorted(unimplemented_files, key=_get_layer)
            
        print(f"🔍 未実装ファイルを検出しました (実装順にソート済み): {unimplemented_files}")
        
        success_files = []
        for file in unimplemented_files:
            success = run_aider_on_file(file, use_map=args.use_map)
            if success:
                success_files.append(file)
                
        # 3. 仕上げの全体整合性チェック
        if success_files:
            run_final_check(success_files, use_map=args.use_map)
            
        print("\n🎉 すべての自動実装・整合性チェックプロセスが完了しました！")

if __name__ == "__main__":
    main()
