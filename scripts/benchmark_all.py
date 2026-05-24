import urllib.request
import json
import time
import datetime
import os

API_BASE = "http://127.0.0.1:11434/api"
REPORT_PATH = "/home/irom/dev/gemini-docs/projects/ollama/benchmark_report.md"

def get_models():
    req = urllib.request.Request(f"{API_BASE}/tags")
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            return [m['name'] for m in data.get('models', [])]
    except Exception as e:
        print(f"Failed to get models: {e}")
        return []

def get_memory_usage():
    req = urllib.request.Request(f"{API_BASE}/ps")
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            models = data.get('models', [])
            if models:
                # 最初のロードされているモデルのVRAM/RAM使用量を返す
                return models[0].get('size_vram', 0)
    except Exception:
        pass
    return 0

def run_bench(model_name):
    prompt = "日本の首都は何ですか？理由も1文で説明してください。"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 50
        }
    }

    req = urllib.request.Request(
        f"{API_BASE}/generate",
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"}
    )

    try:
        print(f"  [{model_name}] ウォームアップ（ロード）中...")
        warmup_start = time.time()
        urllib.request.urlopen(req).read()
        print(f"  [{model_name}] ロード完了 (所要時間: {time.time() - warmup_start:.2f}秒)")
        
        # ロード直後にメモリ使用量を取得
        mem_bytes = get_memory_usage()
        mem_gb = mem_bytes / (1024**3)

        print(f"  [{model_name}] 速度測定実行中...")
        start_time = time.time()
        with urllib.request.urlopen(req) as res:
            response = json.loads(res.read().decode('utf-8'))
        end_time = time.time()
        
        prompt_eval_duration = response.get("prompt_eval_duration", 0) / 1e9
        eval_duration = response.get("eval_duration", 0) / 1e9
        
        prompt_speed = response.get("prompt_eval_count", 0) / prompt_eval_duration if prompt_eval_duration > 0 else 0
        eval_speed = response.get("eval_count", 0) / eval_duration if eval_duration > 0 else 0
        
        return {
            "success": True,
            "prompt_speed": prompt_speed,
            "eval_speed": eval_speed,
            "memory_gb": mem_gb
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main():
    models = get_models()
    if not models:
        print("モデルが見つかりません。Ollamaが起動しているか確認してください。")
        return

    print(f"対象モデル: {models}")
    
    results = []
    for model in models:
        print(f"\n=== ベンチマーク開始: {model} ===")
        res = run_bench(model)
        if res["success"]:
            results.append({
                "model": model,
                "prompt_speed": res["prompt_speed"],
                "eval_speed": res["eval_speed"],
                "memory_gb": res["memory_gb"]
            })
        else:
            print(f"エラー: {res['error']}")
    
    # Generate Markdown Report
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"# Ollama モデル 実測ベンチマークレポート\n\n"
    report += f"**計測日時**: {date_str}\n\n"
    report += "| モデル名 | 実行メモリ (GB) | 生成速度 (t/s) | 入力処理速度 (t/s) |\n"
    report += "| :--- | :---: | :---: | :---: |\n"
    
    # 速度順 (eval_speed降順) にソートして出力
    results.sort(key=lambda x: x["eval_speed"], reverse=True)
    
    for r in results:
        report += f"| **{r['model']}** | {r['memory_gb']:.2f} | **{r['eval_speed']:.2f}** | {r['prompt_speed']:.2f} |\n"
        
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"\n✅ レポートを出力しました: {REPORT_PATH}")

if __name__ == "__main__":
    main()
