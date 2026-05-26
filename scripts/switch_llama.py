#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import requests

MODELS = {
    "design": "/mnt/data/llama-models/Qwen3.6-27B-Q4_K_M.gguf",
    "coding": "/mnt/data/llama-models/Qwen2.5-Coder-32B-Instruct-IQ3_M.gguf",
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
        "--ubatch-size", "512",
        "-fa", "1",
        "-ctk", "q8_0",
        "-ctv", "q8_0"
    ]
    
    if "qwen" in model_path.lower():
        cmd.extend(["--chat-template-file", "scripts/qwen2.5_chat_template.jinja"])
        
    import shlex
    cmd_str = shlex.join(cmd)
    
    # We wrap the command in sg render for GPU access
    exec_start = f"sg render -c {shlex.quote(cmd_str)}"
    
    service_content = f"""[Unit]
Description=llama.cpp Server for {role} model
After=network.target

[Service]
# -ngl 20: Stable APU offload
# --ubatch-size 512: Prevent memory bandwidth thrashing on APU UMA
ExecStart={exec_start}
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
"""
    
    # Write to a temporary file, then sudo cp it to systemd
    tmp_path = "/tmp/llama-server.service.tmp"
    with open(tmp_path, "w") as f:
        f.write(service_content)
        
    try:
        print("Updating systemd service file...")
        subprocess.run(["sudo", "cp", tmp_path, "/etc/systemd/system/llama-server.service"], check=True)
        print("Reloading systemd daemon...")
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        print("Restarting llama-server service...")
        subprocess.run(["sudo", "systemctl", "restart", "llama-server"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure or restart systemd service: {e}")
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
