#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import requests
import shlex

MODELS = {
    "design": "/mnt/data/llama-models/Qwen3.6-27B-MTP-Q4_K_M.gguf",
    "coding": "/mnt/data/llama-models/Qwen3.6-27B-MTP-Q4_K_M.gguf",
    "review": "/mnt/data/llama-models/gemma-4-31B-it-Q3_K_M.gguf",
    "fast": "/mnt/data/llama-models/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"
}

PORT = 9090

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
        print("Usage: .venv/bin/python scripts/switch_llama.py <role> (design|coding|review|fast)")
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
    
    ngl_value = "0"
    ctx_size = "32768"
    ubatch = "512"
    
    if "gemma" not in model_path.lower():
        ngl_value = "33" if "14b" in model_path.lower() else "20"
        
    cmd = [
        "numactl",
        "--physcpubind=0-5",
        "--localalloc",
        "/opt/llama.cpp/build/bin/llama-server",
        "-m", model_path,
        "-c", ctx_size,
        "-np", "1",
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-t", "6",
        "-ngl", ngl_value,
        "--ubatch-size", ubatch,
        "-fa", "1",
        "-ctk", "q8_0",
        "-ctv", "q8_0"
    ]
    
    if "qwen" in model_path.lower():
        cmd.extend(["--chat-template-file", "/home/irom/dev/ollama/scripts/qwen2.5_chat_template.jinja"])
        
    if "27b-mtp" in model_path.lower():
        cmd.extend(["--spec-type", "draft-mtp"])
        cmd[cmd.index("-c")+1] = "65536"
        cmd[cmd.index("--ubatch-size")+1] = "128"
        cmd[cmd.index("-ctk")+1] = "q4_0"
        cmd[cmd.index("-ctv")+1] = "q4_0"
        
    cmd_str = shlex.join(cmd)
    exec_start = f"sg render -c {shlex.quote(cmd_str)}"
    
    service_content = f"""[Unit]
Description=llama.cpp Server for {role} model
After=network.target

[Service]
ExecStart={exec_start}
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
"""
    
    tmp_path = "/tmp/llama-server.service.tmp"
    with open(tmp_path, "w") as f:
        f.write(service_content)
        
    try:
        subprocess.run(["sudo", "cp", tmp_path, "/etc/systemd/system/llama-server.service"], check=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        subprocess.run(["sudo", "systemctl", "restart", "llama-server"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure systemd service: {e}")
        sys.exit(1)
        
    if wait_for_server():
        print(f"Successfully switched to {role} model.")
        with open("/tmp/llama-server-role.txt", "w") as f:
            f.write(role)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
