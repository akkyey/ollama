#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import requests

MODEL_PATH = "/mnt/data/llama-models/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"
PORT = 9092

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
    if not os.path.exists(MODEL_PATH):
        print(f"Model file not found: {MODEL_PATH}")
        sys.exit(1)

    print("--- Starting Qwen 2.5 14B model on Port 9092 ---")
    
    cmd = [
        "numactl",
        "--physcpubind=0-5",
        "--localalloc",
        "/opt/llama.cpp/build/bin/llama-server",
        "-m", MODEL_PATH,
        "-c", "65536",
        "-np", "1",
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", "24",
        "--ubatch-size", "128",
        "-fa", "1",
        "-ctk", "q4_0",
        "-ctv", "q4_0",
        "--chat-template-file", "/home/irom/dev/ollama/scripts/qwen2.5_chat_template.jinja"
    ]
    
    import shlex
    cmd_str = shlex.join(cmd)
    
    # We wrap the command in sg render for GPU access
    exec_start = f"sg render -c {shlex.quote(cmd_str)}"
    
    service_content = f"""[Unit]
Description=llama.cpp Server Light (Qwen 2.5 14B)
After=network.target

[Service]
ExecStart={exec_start}
Restart=always
User=root
Group=root

[Install]
WantedBy=multi-user.target
"""
    
    # Write to a temporary file, then sudo cp it to systemd
    tmp_path = "/tmp/llama-server-light.service.tmp"
    with open(tmp_path, "w") as f:
        f.write(service_content)
        
    try:
        print("Updating systemd service file...")
        subprocess.run(["sudo", "cp", tmp_path, "/etc/systemd/system/llama-server-light.service"], check=True)
        print("Reloading systemd daemon...")
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        print("Restarting llama-server-light service...")
        subprocess.run(["sudo", "systemctl", "restart", "llama-server-light"], check=True)
        print("Enabling llama-server-light service...")
        subprocess.run(["sudo", "systemctl", "enable", "llama-server-light"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure or restart systemd service: {e}")
        sys.exit(1)
        
    if wait_for_server():
        print("Successfully started Qwen 2.5 14B model.")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
