import json
import os
import re
import logging
import queue
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, request, Response
import requests

# --- ペイロード観測用ログ設定 ---
# root実行時でも迷子にならないよう、Linuxの標準的な共有ログ領域、または環境変数から取得
PAYLOAD_LOG_DIR = os.getenv("KILO_PROXY_LOG_DIR", "/var/log/kilo_proxy")
os.makedirs(PAYLOAD_LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger("kilo_proxy")

# --- 定数定義 ---
# Kilo Code (Cline) のタイムアウト制約に対処するための強制システム命令。
# LLMに環境の制約を教え込み、長文出力による暴走を防止する。
SYSTEM_DIRECTIVE = (
    "\\n\\n[CRITICAL SYSTEM DIRECTIVE] Kilo Code has a strict 5-minute timeout. "
    "To prevent timeouts, YOU MUST NEVER output more than 40 lines of code at a time. "
    "If the file is longer, output the first part and end your message with "
    "'I will continue in the next message. Please say continue.'"
    "\\n[CRITICAL SYSTEM DIRECTIVE 2] When you complete your tasks, "
    "YOU MUST ALWAYS use the 'todowrite' tool to update the remaining To-Dos to 'done' status. "
    "NEVER end your turn without checking off completed items."
)

# ストリーミング時のHeartbeat送信間隔（秒）
# Kilo Codeの接続タイムアウト（約5分）を防ぐため、定期的に空チャンクを送信する
HEARTBEAT_INTERVAL_SEC = 30

# フェールセーフ切断までの最大待機時間（秒）
# VS Code自体の根深いタイムアウト（約5分）を回避するための安全マージン
FAILSAFE_TIMEOUT_SEC = 270


def dump_payload(data):
    """Kilo Codeからの生リクエストペイロードをJSONファイルにダンプする。
    KVキャッシュ破壊の原因となる動的変数の位置を特定するための観測機能。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(PAYLOAD_LOG_DIR, f"payload_{ts}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # messagesの概要をコンソールにも出力
    messages = data.get("messages", [])
    logger.info(f"[DUMP] model={data.get('model','?')} messages={len(messages)} -> {filepath}")
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "") or ""
        logger.info(f"  [{i}] role={role} len={len(content)} first100={content[:100]!r}")


def truncate_workspace(text):
    """KVキャッシュ保護のため、ワークスペースファイルツリーを固定長ダミーに置換する。

    llama.cppのKVキャッシュはPrefix一致（先頭からの完全一致）でしか再利用できないため、
    会話中にファイルの増減で変化するワークスペースツリーがプロンプト中腹にあると、
    それ以降のキャッシュが全破棄（Full Recompute）される。
    固定文字列に置換することでPrefixの一致条件を維持し、2回目以降のPrefillを消滅させる。"""
    start_marker = "# Current Workspace Directory"
    end_marker1 = "</environment_details>"
    end_marker2 = "You have not created a todo list yet"

    start_idx = text.find(start_marker)
    if start_idx != -1:
        end_idx = text.find(end_marker2, start_idx)
        if end_idx == -1:
            end_idx = text.find(end_marker1, start_idx)

        if end_idx != -1:
            return (
                text[:start_idx]
                + start_marker
                + " (Workspace file list truncated by Agentic Proxy for KV cache protection."
                + " Use `list_files` tool if needed.)\n\n"
                + text[end_idx:]
            )
    return text


def fix_tool_calls(resp_data):
    """ローカルLLMが出力した不正なツールコール形式をOpenAI互換に自動修復する。

    ローカルLLMは時折、正規のtool_callsフォーマットではなく、
    XMLタグ（<tool_name>{...}</tool_name>）や生JSON（{"name":...}）で
    ツールコールを出力してしまう。これをパースし、OpenAI互換の
    tool_callsオブジェクトに変換することで、Kilo Codeが正しく処理できるようにする。"""
    if 'choices' not in resp_data or len(resp_data['choices']) == 0:
        return resp_data

    msg = resp_data['choices'][0].get('message', {})
    content = msg.get('content', '') or ''

    # パターン1: XMLタグ形式 (<tool_name>{JSON}</tool_name>)
    xml_match = re.search(r'<([a-zA-Z0-9_]+)>\s*(\{.*?\})\s*</\1>', content, re.DOTALL)

    if xml_match:
        tool_name = xml_match.group(1)
        tool_args_str = xml_match.group(2)
        try:
            json.loads(tool_args_str)  # JSONとして有効か検証
            msg['content'] = content[:xml_match.start()].strip() or None
            msg['tool_calls'] = [{
                'id': f'call_proxy_{uuid.uuid4().hex[:12]}',
                'type': 'function',
                'function': {
                    'name': tool_name,
                    'arguments': tool_args_str
                }
            }]
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"XMLツールコールのJSONパース失敗: {e}")

    # パターン2: 生JSON形式 ({"name": ..., "arguments": ...})
    elif '{"name"' in content:
        json_start = content.find('{"name"')
        json_str = content[json_start:].strip()

        parsed_tool = None
        while len(json_str) > 10:
            try:
                parsed_tool = json.loads(json_str)
                break
            except (json.JSONDecodeError, ValueError):
                json_str = json_str[:-1]

        if parsed_tool and 'name' in parsed_tool and 'arguments' in parsed_tool:
            msg['content'] = content[:json_start].strip() or None
            msg['tool_calls'] = [{
                'id': f'call_proxy_{uuid.uuid4().hex[:12]}',
                'type': 'function',
                'function': {
                    'name': parsed_tool['name'],
                    'arguments': json.dumps(parsed_tool['arguments'])
                }
            }]

    return resp_data


def remove_unanchored_patterns(obj):
    """JSON Schema内のアンカーなし正規表現パターンを除去する。

    ローカルLLM（特にllama.cpp）は、JSON Schemaのpatternフィールドに含まれる
    アンカーなし正規表現（^...$で囲まれていないもの）を正しく処理できず、
    不正な出力やパースエラーの原因となる。
    アンカー付きパターン（^...$）のみを残すことで、ツールコールの成功率を向上させる。"""
    if isinstance(obj, dict):
        if 'pattern' in obj:
            p = obj['pattern']
            if isinstance(p, str) and not (p.startswith('^') and p.endswith('$')):
                del obj['pattern']
        for k, v in list(obj.items()):
            remove_unanchored_patterns(v)
    elif isinstance(obj, list):
        for item in obj:
            remove_unanchored_patterns(item)


# --- Flaskアプリケーション ---
app = Flask(__name__)


@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    # 余分な空白が混入した場合（%20）に備えて除去
    clean_path = path.replace(' ', '')
    url = f'http://127.0.0.1:9090/{clean_path}'

    if request.method == 'POST' and clean_path.endswith('chat/completions'):
        # --- [B-1] 安全なJSONパース ---
        data = request.get_json(silent=True)
        if data is None:
            return Response(
                '{"error": "Invalid JSON payload"}',
                status=400, mimetype='application/json'
            )

        dump_payload(data)  # 観測: Kilo Codeの生ペイロードをダンプ

        # --- [Context Architecture最適化] ---
        # Kilo Codeが毎ターン送信してくる巨大なファイルツリー（3万トークン）を削減し、
        # llama.cppのKVキャッシュ破壊とプレフィル地獄を防ぐ。
        messages = data.get('messages', [])

        # [C-4] System Directive の注入（定数から参照）
        for msg in messages:
            if msg.get('role') == 'system':
                msg['content'] += SYSTEM_DIRECTIVE

        # [C-2] ワークスペースツリーの切り詰め（KVキャッシュ保護）
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content')
                if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text' and '<environment_details>' in part.get('text', ''):
                            part['text'] = truncate_workspace(part['text'])
                elif isinstance(content, str):
                    if '<environment_details>' in content:
                        msg['content'] = truncate_workspace(content)

        is_stream = data.get('stream', False)

        if 'tools' in data:
            # --- [MCP Memory Tool 削除フィルター] ---
            # ローカルLLMには不要かつ1万トークン以上消費する記憶ツール群を安全に除外
            data['tools'] = [
                t for t in data['tools']
                if not t.get('function', {}).get('name', '').startswith('memory_')
            ]

            # [C-5] アンカーなし正規表現の除去（ローカルLLMの互換性確保）
            remove_unanchored_patterns(data['tools'])

        headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in ['host', 'content-length']}

        if is_stream:
            data['stream'] = True

            def generate():
                # 初回ダミーチャンク: ヘッダーを即座にフラッシュし、
                # Kilo Codeの接続タイムアウト（5秒）を防止する
                dummy = {
                    "id": "chatcmpl-dummy",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "qwen",
                    "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}]
                }
                yield f'data: {json.dumps(dummy)}\n\n'

                # --- [B-2] バックエンドへの接続に例外ハンドリングを追加 ---
                try:
                    resp = requests.post(url, json=data, headers=headers, stream=True, timeout=300)
                except requests.exceptions.RequestException as e:
                    logger.error(f"[STREAM] バックエンド接続エラー: {e}")
                    error_chunk = {
                        "id": "chatcmpl-error",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "qwen",
                        "choices": [{"index": 0, "delta": {"content": f"[Proxy Error] {e}"}, "finish_reason": "stop"}]
                    }
                    yield f'data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n'
                    yield 'data: [DONE]\n\n'
                    return

                q = queue.Queue()

                def reader():
                    try:
                        for chunk in resp.iter_lines():
                            if chunk:
                                q.put(chunk)
                        q.put(None)  # ストリーム終了シグナル
                    except Exception:
                        q.put(None)
                threading.Thread(target=reader, daemon=True).start()

                start_time = time.time()
                first_token_received = False
                last_heartbeat_time = time.time()

                while True:
                    try:
                        chunk = q.get(timeout=1.0)
                        if chunk is None:
                            break
                        first_token_received = True
                        yield chunk.decode('utf-8') + '\n\n'
                    except queue.Empty:
                        elapsed = time.time() - start_time

                        # --- [B-3] 定期Heartbeat送信 ---
                        # llama-serverがPrefill処理中で沈黙している間、
                        # 一定間隔で空のダミーチャンクを送信し、Kilo Codeの
                        # 接続タイムアウトを防止する
                        if not first_token_received:
                            if (time.time() - last_heartbeat_time) >= HEARTBEAT_INTERVAL_SEC:
                                heartbeat = {
                                    "id": "chatcmpl-heartbeat",
                                    "object": "chat.completion.chunk",
                                    "created": 0,
                                    "model": "qwen",
                                    "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}]
                                }
                                yield f'data: {json.dumps(heartbeat)}\n\n'
                                last_heartbeat_time = time.time()
                                logger.info(f"[HEARTBEAT] {elapsed:.0f}秒経過、Heartbeat送信")

                            # --- フェールセーフ切断 ---
                            # VS Code自体の根深いタイムアウト（約5分）を回避するため、
                            # 一定時間経過後に通信を正常終了させる
                            if elapsed > FAILSAFE_TIMEOUT_SEC:
                                failsafe_msg = (
                                    '\n\n[System] コンテキストが巨大なため、読み込みに4分半以上かかっています。'
                                    'VS Codeの強制タイムアウトを防ぐため、一旦通信を正常終了させました。'
                                    '裏側でキャッシュ構築は継続していますので、'
                                    '10〜15分後にもう一度「再送」または「続行」を送信してください。'
                                )
                                chunk_data = {
                                    "id": "chatcmpl-failsafe",
                                    "object": "chat.completion.chunk",
                                    "created": 0,
                                    "model": "qwen",
                                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": failsafe_msg}, "finish_reason": "stop"}]
                                }
                                yield f'data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n'
                                yield 'data: [DONE]\n\n'
                                logger.warning(f"[FAILSAFE] {FAILSAFE_TIMEOUT_SEC}秒超過、フェールセーフ切断")
                                break

            return Response(generate(), mimetype='text/event-stream')

        else:
            # 非ストリーミングモード
            data['stream'] = False
            try:
                resp = requests.post(url, json=data, headers=headers, timeout=300)
            except requests.exceptions.RequestException as e:
                logger.error(f"[NON-STREAM] バックエンド接続エラー: {e}")
                return Response(
                    json.dumps({"error": str(e)}),
                    status=502, mimetype='application/json'
                )
            if resp.status_code == 200:
                resp_data = fix_tool_calls(resp.json())
                return Response(json.dumps(resp_data), mimetype='application/json')
            return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))

    # チャット以外のリクエスト（/v1/models 等）は直接プロキシ
    req_kwargs = {
        'method': request.method,
        'url': url,
        'headers': {k: v for k, v in request.headers.items()
                    if k.lower() not in ['host', 'content-length']},
    }
    if request.is_json:
        req_kwargs['json'] = request.get_json(silent=True)
    elif request.data:
        req_kwargs['data'] = request.data

    resp = requests.request(**req_kwargs)
    return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))


if __name__ == '__main__':
    print("Starting Kilo Code Proxy on port 9091...")
    print("Please set Kilo Code Base URL to: http://localhost:9091/v1")
    # [A-1] ローカルループバックのみにバインド（セキュリティ対策）
    app.run(port=9091, host='127.0.0.1')
