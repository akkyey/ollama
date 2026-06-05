import urllib.request
import json
import time
import subprocess
import os

OLLAMA_PS_URL = "http://127.0.0.1:11434/api/ps"
CHECK_INTERVAL = 5

def is_ollama_idle():
    """
    OllamaのAPIを叩いて、現在ロードされているモデルが0個ならアイドル状態とみなす。
    Ollama自体がダウンしている場合も、llama-serverを動かすためにTrueを返す。
    """
    try:
        req = urllib.request.Request(OLLAMA_PS_URL)
        with urllib.request.urlopen(req, timeout=3) as res:
            data = json.loads(res.read().decode('utf-8'))
            return len(data.get('models', [])) == 0
    except Exception as e:
        print(f"Ollama PS check failed: {e}")
        return True 

def set_llama_server_state(idle):
    """
    Ollamaがアイドルの時はllama-serverを起動し、
    Ollamaが動作中（モデルロード中）の時はメモリ競合を防ぐためllama-serverを停止する。
    """
    try:
        status = subprocess.run(["systemctl", "is-active", "llama-server.service"], capture_output=True, text=True)
        is_active = (status.stdout.strip() == "active")
        
        if idle and not is_active:
            print("Ollama is idle. Starting llama-server.service...")
            subprocess.run(["systemctl", "start", "llama-server.service"])
        elif not idle and is_active:
            print("Ollama is active! Stopping llama-server.service to free up memory...")
            subprocess.run(["systemctl", "stop", "llama-server.service"])
    except Exception as e:
        print(f"Error controlling llama-server.service: {e}")

def main():
    print("Starting Ollama Idle Monitor (Exclusive Guard)...")
    while True:
        idle = is_ollama_idle()
        set_llama_server_state(idle)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
