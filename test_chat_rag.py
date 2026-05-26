import urllib.request
import json
import time

url = "http://100.99.31.13:3000/api/v1/chat/completions"
headers = {
    "Authorization": "Bearer sk-testapikey1234567890abcdef",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

data = {
    "model": "gemma2:2b",
    "messages": [
        {"role": "user", "content": "明日の静岡県沼津市の天気を教えて下さい"}
    ],
    "features": {
        "web_search": True
    },
    "metadata": {
        "chat_id": "local:test",
        "message_id": "test_msg"
    }
}

req = urllib.request.Request(
    url,
    data=json.dumps(data).encode('utf-8'),
    headers=headers,
    method='POST'
)

print("Sending request to Open WebUI chat API...")
start_time = time.time()
try:
    with urllib.request.urlopen(req) as res:
        response_data = json.loads(res.read().decode('utf-8'))
        elapsed = time.time() - start_time
        print(f"Response received in {elapsed:.2f} seconds:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print("Response details:", e.read().decode('utf-8'))
