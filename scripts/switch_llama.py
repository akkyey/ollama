#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import requests
import psutil

MODELS = {
    "design": "/mnt/data/llama-models/Qwen3.6-27B-Q4_K_M.gguf",
    "coding": "/mnt/data/llama-models/Qwen2.5-Coder-32B-Instruct-IQ3_M.gguf",
    "review": "/mnt/data/llama-models/gemma-4-31B-it-Q3_K_M.gguf",
    "fast": "/mnt/data/llama-models/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"
}

LOG_FILE = "/tmp/llama-server.log"
PORT = 9090

def get_llama_server_processes():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'llama-server' in p.info['name'] or (p.info['cmdline'] and 'llama-server' in p.info['cmdline'][0]):
                procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return procs

def kill_processes(procs):
    for p in procs:
        try:
            print(f"Terminating llama-server PID {p.pid}...")
            p.terminate()
        except Exception as e:
            print(f"Failed to terminate PID {p.pid}: {e}")
    
    # Wait for termination
    gone, alive = psutil.wait_procs(procs, timeout=5)
    for p in alive:
        try:
            print(f"Force killing llama-server PID {p.pid}...")
            p.kill()
        except Exception as e:
            print(f"Failed to kill PID {p.pid}: {e}")

def wait_for_server():
    print(f"Waiting for llama-server to initialize on port {PORT}...")
    url = f"http://127.0.0.1:{PORT}/v1/models"
    for i in range(120): # wait up to 120 seconds
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                print("Server is up and running!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    print("Timeout waiting for server to start.")
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: .venv/bin/python scripts/switch_llama.py <role> (design|coding|review)")
        sys.exit(1)
    
    role = sys.argv[1]
    if role not in MODELS:
        print(f"Unknown role: {role}")
        sys.exit(1)
        
    model_path = MODELS[role]
    if not os.path.exists(model_path):
        print(f"Model file not found: {model_path}")
        sys.exit(1)

    print(f"--- Switching to model for role: {role} ---")
    
    # 1. Kill existing servers
    procs = get_llama_server_processes()
    if procs:
        kill_processes(procs)
    else:
        print("No existing llama-server found.")
        
    # 2. Start new server
    # Vulkan最適化: Qwenは20レイヤー、Gemma(31B)は重すぎるためCPU(0)とする
    ngl_value = "0"
    if "gemma" not in model_path.lower():
        ngl_value = "20"
        
    cmd = [
        "numactl",
        "--physcpubind=0-5",
        "--localalloc",
        "/opt/llama.cpp/build/bin/llama-server",
        "-m", model_path,
        "-c", "32768",
        "-np", "1",
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", ngl_value,
        "-fa", "1",
        "-ctk", "q8_0",
        "-ctv", "q8_0"
    ]
    
    # Qwenモデル（coding, design）の場合は専用のツール対応テンプレートを使用
    if "qwen" in model_path.lower():
        cmd.extend(["--chat-template-file", "scripts/qwen2.5_chat_template.jinja"])
    # Gemmaなどの場合はデフォルトの内蔵テンプレートを使用（自動推論）
    
    import shlex
    cmd_str = shlex.join(cmd)
    final_cmd = ["sg", "render", "-c", cmd_str]
    
    print(f"Starting model: {os.path.basename(model_path)}")
    with open(LOG_FILE, "w") as log_out:
        # Popen to run in background (detach from python script)
        subprocess.Popen(final_cmd, stdout=log_out, stderr=subprocess.STDOUT, start_new_session=True)
        
    # 3. Wait for it to become ready
    if wait_for_server():
        print(f"Successfully switched to {role} model.")
        with open("/tmp/llama-server-role.txt", "w") as f:
            f.write(role)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
