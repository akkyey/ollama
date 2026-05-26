import json
import os
import logging
from datetime import datetime
from flask import Flask, request, Response
import requests

# --- ペイロード観測用ログ設定 ---
PAYLOAD_LOG_DIR = "/tmp/kilo_proxy_logs"
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
        
        # --- [Agentic Switch (動的ルーティング)] ---
        import re
        import subprocess
        
        target_role = "coding" # デフォルトは最も強力なモデル
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content')
                text_content = ""
                if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text':
                            text_content += part.get('text', '')
                elif isinstance(content, str):
                    text_content = content
                
                # <slug> を探す
                slug_match = re.search(r'<slug>([^<]+)</slug>', text_content)
                if slug_match:
                    slug = slug_match.group(1).lower()
                    if slug in ['code', 'debug']:
                        target_role = "coding"
                    elif slug in ['architect', 'orchestrator']:
                        target_role = "design"
                    elif slug in ['review']:
                        target_role = "review"
                    elif slug in ['ask']:
                        target_role = "fast"
                    break # 最新のslugを採用
        
        # 現在のロールを確認
        current_role = None
        try:
            with open('/tmp/llama-server-role.txt', 'r') as f:
                current_role = f.read().strip()
        except FileNotFoundError:
            pass
            
        if current_role != target_role:
            logger.info(f"🔄 Agentic Switch: Switching role from {current_role} to {target_role}...")
            try:
                subprocess.run(["/home/irom/dev/ollama/.venv/bin/python", "scripts/switch_llama.py", target_role], check=True)
                logger.info(f"✅ Agentic Switch: Successfully switched to {target_role}.")
            except subprocess.CalledProcessError as e:
                logger.error(f"❌ Agentic Switch failed: {e}")
                # 失敗してもとりあえず既存のモデルに流す
        # -------------------------------------------

        
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
        data['stream'] = False # Force non-streaming to llama-server
        
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}
        
        if is_stream:
            import threading
            import queue
            from datetime import datetime
            
            q = queue.Queue()
            def fetch():
                try:
                    res = requests.post(url, json=data, headers=headers)
                    q.put(('success', res))
                except Exception as e:
                    q.put(('error', str(e)))
            
            t = threading.Thread(target=fetch)
            t.start()
            
            def generate():
                while True:
                    try:
                        status, res = q.get(timeout=5.0)
                        if status == 'success':
                            if res.status_code == 200:
                                resp_data = fix_tool_calls(res.json())
                                msg = resp_data['choices'][0].get('message', {})
                                chunk = {
                                    "id": resp_data.get("id", "chatcmpl-123"),
                                    "object": "chat.completion.chunk",
                                    "created": resp_data.get("created", 0),
                                    "model": resp_data.get("model", ""),
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": msg,
                                            "finish_reason": resp_data['choices'][0].get('finish_reason', 'stop')
                                        }
                                    ]
                                }
                                yield f"data: {json.dumps(chunk)}\n\n"
                                yield "data: [DONE]\n\n"
                            else:
                                yield f"data: {json.dumps({'error': 'Backend error'})}\n\n"
                        break
                    except queue.Empty:
                        heartbeat_chunk = {
                            "id": "chatcmpl-heartbeat",
                            "object": "chat.completion.chunk",
                            "created": int(datetime.now().timestamp()),
                            "model": data.get("model", "qwen"),
                            "choices": [{"index": 0, "delta": {"content": ""}}]
                        }
                        yield f"data: {json.dumps(heartbeat_chunk)}\n\n"

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
