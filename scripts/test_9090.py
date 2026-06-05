import urllib.request
import json
import time

URL = "http://127.0.0.1:9090/v1/chat/completions"

payload = {
    "model": "qwen",
    "messages": [
        {"role": "user", "content": "10個のランダムな日本の都市名を挙げてください。"}
    ],
    "stream": False
}

req = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)

print("Starting benchmark against 127.0.0.1:9090 (llama-server)...")
start_time = time.time()

try:
    with urllib.request.urlopen(req) as res:
        response = json.loads(res.read().decode('utf-8'))
    end_time = time.time()
    total_time = end_time - start_time
    
    # llama-serverのusageには補足情報が入る
    usage = response.get('usage', {})
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)
    
    # 簡易計算（厳密なppとtgは分かれないが、全体スループットで測る）
    # またはレスポンスヘッダや詳細なusageが含まれていれば
    print(f"Time: {total_time:.2f}s")
    print(f"Prompt tokens: {prompt_tokens}")
    print(f"Completion tokens: {completion_tokens}")
    
    if total_time > 0:
        print(f"Overall Speed (tokens/sec): {(prompt_tokens + completion_tokens) / total_time:.2f} t/s")
        print(f"Generation Speed (approx): {completion_tokens / total_time:.2f} t/s (includes prompt eval time)")
        
except Exception as e:
    print(f"Error: {e}")
