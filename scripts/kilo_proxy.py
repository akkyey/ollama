import json
import os
import logging
from datetime import datetime
from flask import Flask, request, Response
import requests

# --- ペイロード観測用ログ設定 ---
# root実行時でも迷子にならないよう、Linuxの標準的な共有ログ領域、または環境変数から取得
PAYLOAD_LOG_DIR = os.getenv("KILO_PROXY_LOG_DIR", "/var/log/kilo_proxy")
os.makedirs(PAYLOAD_LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger("kilo_proxy")

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

app = Flask(__name__)

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    # 余分な空白が混入した場合（%20）に備えて除去
    clean_path = path.replace(' ', '')
    url = f'http://127.0.0.1:9090/{clean_path}'
    
    if request.method == 'POST' and clean_path.endswith('chat/completions'):
        data = request.json
        dump_payload(data)  # 観測: Kilo Codeの生ペイロードをダンプ
        
        # --- [Context Architecture最適化] ---
        # Kilo Codeが毎ターン送信してくる巨大なファイルツリー（3万トークン）を削減し、
        # llama.cppのKVキャッシュ破壊とプレフィル地獄を防ぐ。
        messages = data.get('messages', [])
        
        # Inject system directives
        for msg in messages:
            if msg.get('role') == 'system':
                msg['content'] += "\\n\\n[CRITICAL SYSTEM DIRECTIVE] Kilo Code has a strict 5-minute timeout. To prevent timeouts, YOU MUST NEVER output more than 40 lines of code at a time. If the file is longer, output the first part and end your message with 'I will continue in the next message. Please say continue.'\\n[CRITICAL SYSTEM DIRECTIVE 2] When you complete your tasks, YOU MUST ALWAYS use the 'todowrite' tool to update the remaining To-Dos to 'done' status. NEVER end your turn without checking off completed items."
                
        # --- [Agentic Switch (Removed)] ---
        # User requested to use the 27B model for all roles, so dynamic switching is disabled.
        
        def truncate_workspace(text):
            start_marker = "# Current Workspace Directory"
            end_marker1 = "</environment_details>"
            end_marker2 = "You have not created a todo list yet"
            
            start_idx = text.find(start_marker)
            if start_idx != -1:
                end_idx = text.find(end_marker2, start_idx)
                if end_idx == -1:
                    end_idx = text.find(end_marker1, start_idx)
                
                if end_idx != -1:
                    return text[:start_idx] + start_marker + " (Workspace file list truncated by Agentic Proxy for KV cache protection. Use `list_files` tool if needed.)\n\n" + text[end_idx:]
            return text

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
        # ------------------------------------

        def fix_tool_calls(resp_data):
            if 'choices' in resp_data and len(resp_data['choices']) > 0:
                msg = resp_data['choices'][0].get('message', {})
                content = msg.get('content', '') or ''
                
                import re
                xml_match = re.search(r'<([a-zA-Z0-9_]+)>\s*(\{.*?\})\s*</\1>', content, re.DOTALL)
                
                if xml_match:
                    tool_name = xml_match.group(1)
                    tool_args_str = xml_match.group(2)
                    try:
                        json.loads(tool_args_str)
                        msg['content'] = content[:xml_match.start()].strip() or None
                        msg['tool_calls'] = [{
                            'id': 'call_proxy_123',
                            'type': 'function',
                            'function': {
                                'name': tool_name,
                                'arguments': tool_args_str
                            }
                        }]
                    except Exception as e:
                        print("Failed to parse XML tool call:", e)
                elif '{"name"' in content:
                    json_start = content.find('{"name"')
                    json_str = content[json_start:].strip()
                    
                    parsed_tool = None
                    while len(json_str) > 10:
                        try:
                            parsed_tool = json.loads(json_str)
                            break
                        except Exception:
                            json_str = json_str[:-1]
                            
                    if parsed_tool and 'name' in parsed_tool and 'arguments' in parsed_tool:
                        msg['content'] = content[:json_start].strip() or None
                        msg['tool_calls'] = [{
                            'id': 'call_proxy_123',
                            'type': 'function',
                            'function': {
                                'name': parsed_tool['name'],
                                'arguments': json.dumps(parsed_tool['arguments'])
                            }
                        }]
            return resp_data

        is_stream = data.get('stream', False)
        
        if 'tools' in data:
            # --- [MCP Memory Tool 削除フィルター] ---
            # ローカルLLMには不要かつ1万トークン以上消費する記憶ツール群を安全に除外
            data['tools'] = [
                t for t in data['tools']
                if not t.get('function', {}).get('name', '').startswith('memory_')
            ]
            
            def remove_unanchored_patterns(obj):
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
            remove_unanchored_patterns(data['tools'])

        data['stream'] = False # Force non-streaming to llama-server
        
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}
        
        if is_stream:
            data['stream'] = True
            def generate():
                # Force flush headers immediately to prevent Kilo Code connection timeout (5s)
                dummy = {"id":"chatcmpl-dummy","object":"chat.completion.chunk","created":0,"model":"qwen","choices":[{"index":0,"delta":{"content":""},"finish_reason":None}]}
                yield f'data: {json.dumps(dummy)}\n\n'
                
                resp = requests.post(url, json=data, headers=headers, stream=True)
                import queue, threading, time
                q = queue.Queue()
                def reader():
                    try:
                        for chunk in resp.iter_lines():
                            if chunk:
                                q.put(chunk)
                        q.put(None)
                    except Exception:
                        q.put(None)
                threading.Thread(target=reader, daemon=True).start()
                
                start_time = time.time()
                first_token_received = False
                
                while True:
                    try:
                        chunk = q.get(timeout=1.0)
                        if chunk is None:
                            break
                        first_token_received = True
                        yield chunk.decode('utf-8') + '\n\n'
                    except queue.Empty:
                        if not first_token_received and (time.time() - start_time) > 270:
                            msg = '\\n\\n[System] コンテキストが巨大なため、読み込みに4分半以上かかっています。VS Codeの強制タイムアウトを防ぐため、一旦通信を正常終了させました。裏側でキャッシュ構築は継続していますので、10〜15分後にもう一度「再送」または「続行」を送信してください。'
                            chunk_data = {
                                "id": "chatcmpl-123",
                                "object": "chat.completion.chunk",
                                "created": 123,
                                "model": "qwen",
                                "choices": [{"index": 0, "delta": {"role": "assistant", "content": msg}, "finish_reason": "stop"}]
                            }
                            yield f'data: {json.dumps(chunk_data, ensure_ascii=False)}\\n\\n'
                            yield 'data: [DONE]\\n\\n'
                            break
                        else:
                            pass
            return Response(generate(), mimetype='text/event-stream')

        else:
            resp = requests.post(url, json=data, headers=headers)
            if resp.status_code == 200:
                resp_data = fix_tool_calls(resp.json())
                return Response(json.dumps(resp_data), mimetype='application/json')
            return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))

    # For non-chat requests (like /v1/models), just proxy directly
    req_kwargs = {
        'method': request.method,
        'url': url,
        'headers': {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']},
    }
    if request.is_json:
        req_kwargs['json'] = request.json
    elif request.data:
        req_kwargs['data'] = request.data
        
    resp = requests.request(**req_kwargs)
    return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))

if __name__ == '__main__':
    print("Starting Kilo Code Proxy on port 9091...")
    print("Please set Kilo Code Base URL to: http://localhost:9091/v1")
    app.run(port=9091, host='0.0.0.0')
