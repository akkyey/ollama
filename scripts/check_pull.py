import urllib.request
import json

def check_status(model_name):
    payload = {"name": model_name, "stream": True}
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/pull",
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"}
    )
    
    print(f"⏳ {model_name} のダウンロード状況を確認中...")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            count = 0
            for line in res:
                if not line:
                    continue
                data = json.loads(line.decode('utf-8'))
                status = data.get("status", "")
                completed = data.get("completed", 0)
                total = data.get("total", 0)
                
                if total > 0:
                    percent = (completed / total) * 100
                    print(f"📊 進捗: {status} ({percent:.2f}%: {completed/1e9:.2f}GB / {total/1e9:.2f}GB)")
                    return
                else:
                    print(f"📊 ステータス: {status}")
                
                count += 1
                if count >= 3:
                    return
    except Exception as e:
        print("エラー:", e)

check_status("hf.co/unsloth/Qwen3.6-27B-GGUF:IQ4_XS")
