import requests
import json
import time

PROXY_URL = "http://127.0.0.1:9091/v1/chat/completions"

# Kilo CodeのUIモードと、それに対応するAgentic Switchのロール
MODES_TO_TEST = [
    ("ask", "fast (Qwen2.5-14B)"),
    ("architect", "design (Qwen3.6-27B)"),
    ("review", "review (Gemma4-31B)"),
    ("code", "coding (Qwen2.5-Coder-32B)")
]

print("====================================================")
print("🤖 Agentic Switch (自動ルーティング) 完全自動テスト")
print("====================================================")
print("プロキシを経由して、各モードが正しく裏のモデルを切り替えるかテストします。")
print("※各モデルの起動に1〜2分かかるため、完了まで約5〜6分かかります。\n")

for slug, expected_role in MODES_TO_TEST:
    print(f"▶️ テスト開始: モード = [{slug.upper()}] -> 期待されるロール = {expected_role}")
    
    # Kilo Codeが送信するペイロードを模倣
    payload = {
        "model": "qwen2.5-coder-32b-instruct-q4_k_m.gguf", # モデル名は何でもプロキシが上書きまたは無視する
        "messages": [
            {
                "role": "user",
                "content": f"<environment_details>\n# Current Mode\n<slug>{slug}</slug>\n<name>{slug.capitalize()}</name>\n</environment_details>\nこんにちは！あなたは今どのモードですか？"
            }
        ],
        "stream": False,
        "max_tokens": 50
    }
    
    start_time = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            print(f"✅ 成功! ({elapsed:.1f}秒)\nLLMの応答: {content.strip()}")
        else:
            print(f"❌ 失敗 (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ 接続エラー: {e}")
        print("※ kilo_proxy.py がポート9091で起動しているか確認してください。")
        break
    
    print("-" * 50)

print("\n🎉 全てのAgentic Switchルーティングテストが完了しました！")
