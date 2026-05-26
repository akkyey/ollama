import urllib.request
import json
import time

URL = "http://127.0.0.1:9090/v1/chat/completions"

payload = {
    "model": "qwen",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "3個のランダムな日本の都市名を挙げてください。それぞれの都市について1文で解説も付けてください。"}
    ],
    "stream": True
}

req = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)

print("=====================================================")
print("限界突破サーバ (127.0.0.1:9090) の推論速度を計測します")
print("=====================================================")
start_time = time.time()

try:
    with urllib.request.urlopen(req) as res:
        first_chunk_time = None
        tokens = 0
        
        for line in res:
            line = line.decode('utf-8').strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                        pp_time = first_chunk_time - start_time
                        print(f"✅ 初回プレフィル(pp)完了: {pp_time:.2f} 秒")
                        print("生成中...", end="", flush=True)
                    
                    choices = data.get("choices", [])
                    if choices and "delta" in choices[0] and "content" in choices[0]["delta"]:
                        content = choices[0]["delta"]["content"]
                        if content:
                            tokens += 1
                            if tokens % 10 == 0:
                                print(".", end="", flush=True)
                except Exception as e:
                    pass
        
        last_chunk_time = time.time()
        print("\n\n=== 📊 限界突破ベンチマーク結果 ===")
        
        tg_time = last_chunk_time - first_chunk_time
        
        print(f"Prompt Processing (pp) 待機時間 : {pp_time:.2f} 秒")
        print(f"生成トークン数                    : {tokens} tokens")
        print(f"Text Generation (tg) 所要時間     : {tg_time:.2f} 秒")
        
        if tg_time > 0:
            speed = tokens / tg_time
            print(f"👉 【実測】Text Generation 速度 : {speed:.2f} t/s")
            
            print("\n=== 📈 改善効果の確認 ===")
            print("- 従来の tg 速度 (1.87 t/s) との比較:")
            if speed > 1.87:
                improvement = speed / 1.87
                print(f"  🎉 投機的デコード等により、約 {improvement:.2f} 倍 に高速化しています！")
            else:
                print("  ⚠️ 従来と同等、または遅くなっています。投機的デコードが効いていない可能性があります。")
        
except Exception as e:
    print(f"\nエラーが発生しました。llama-server が起動しているか確認してください。")
    print(f"詳細: {e}")
